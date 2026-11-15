"""Esquema inicial: 13 tablas del Cap. 6 (Tabla 6.6).

Ajustes respecto al Cap. 6: perfil_usuario.password_hash, estado 'pendiente_activacion', tabla token_activacion.
"""
from alembic import op

revision = "0001"
down_revision = None

SQL_SUBIDA = """
CREATE EXTENSION IF NOT EXISTS citext;

CREATE TABLE perfil_usuario (
  user_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  nombre text NOT NULL,
  correo citext UNIQUE NOT NULL,
  rol text NOT NULL CHECK (rol IN ('usuario','analista','administrador')),
  estado text NOT NULL CHECK (estado IN ('pendiente_activacion','activo','inactivo')),
  password_hash text NULL,
  creado_en timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE token_activacion (
  token_hash text PRIMARY KEY,
  user_id uuid NOT NULL REFERENCES perfil_usuario ON DELETE RESTRICT,
  vence_en timestamptz NOT NULL,
  usado_en timestamptz
);

CREATE TABLE distrito (
  ubigeo char(6) PRIMARY KEY CHECK (ubigeo ~ '^1501[0-9]{2}$'),
  nombre text NOT NULL
);

CREATE TABLE version_datos (
  version_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  nombre_archivo text NOT NULL,
  periodo_corte date NOT NULL,
  version text NOT NULL,
  sha256 char(64) NOT NULL UNIQUE,
  ruta_archivo text NOT NULL,
  estado text NOT NULL CHECK (estado IN ('registrada','integra','con_pendientes','invalida')),
  registrada_por uuid NOT NULL REFERENCES perfil_usuario ON DELETE RESTRICT,
  registrada_en timestamptz NOT NULL DEFAULT now(),
  UNIQUE (nombre_archivo, periodo_corte)
);

CREATE TABLE validacion_version (
  validacion_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  version_id uuid NOT NULL REFERENCES version_datos ON DELETE RESTRICT,
  control text NOT NULL,
  aprobado boolean NOT NULL,
  detalle text,
  verificada_en timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE registro_pendiente (
  pendiente_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  version_id uuid NOT NULL REFERENCES version_datos ON DELETE RESTRICT,
  codigo_original text NOT NULL,
  n_filas int NOT NULL CHECK (n_filas > 0),
  estado text NOT NULL CHECK (estado IN ('abierto','resuelto')) DEFAULT 'abierto',
  UNIQUE (version_id, codigo_original)
);
CREATE INDEX ix_pendiente_version_estado ON registro_pendiente (version_id, estado);

CREATE TABLE equivalencia_distrito (
  pendiente_id uuid PRIMARY KEY REFERENCES registro_pendiente ON DELETE RESTRICT,
  ubigeo char(6) NOT NULL REFERENCES distrito ON DELETE RESTRICT,
  resuelta_por uuid NOT NULL REFERENCES perfil_usuario ON DELETE RESTRICT,
  resuelta_en timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE observacion_mensual (
  version_id uuid NOT NULL REFERENCES version_datos ON DELETE RESTRICT,
  ubigeo char(6) NOT NULL REFERENCES distrito ON DELETE RESTRICT,
  target text NOT NULL CHECK (target IN ('ROBO','HURTO')),
  fecha date NOT NULL CHECK (EXTRACT(DAY FROM fecha) = 1),
  y int NOT NULL CHECK (y >= 0),
  regimen text NOT NULL CHECK (regimen IN ('pre_break','post_break')),
  value_origin text NOT NULL CHECK (value_origin IN ('observed','reconstructed_zero_no_rows','reconstructed_zero_target_absent')),
  PRIMARY KEY (version_id, ubigeo, target, fecha)
);
CREATE INDEX ix_obs_version_target_ubigeo ON observacion_mensual (version_id, target, ubigeo);

CREATE TABLE configuracion_experimento (
  config_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  nombre text NOT NULL,
  version text NOT NULL,
  contenido jsonb NOT NULL,
  sha256 char(64) NOT NULL UNIQUE,
  aprobada_en date
);

CREATE TABLE ejecucion (
  ejecucion_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  version_id uuid NOT NULL REFERENCES version_datos ON DELETE RESTRICT,
  config_id uuid NOT NULL REFERENCES configuracion_experimento ON DELETE RESTRICT,
  target text NOT NULL CHECK (target IN ('ROBO','HURTO')),
  estado text NOT NULL CHECK (estado IN ('en_curso','completada','fallida')) DEFAULT 'en_curso',
  motivo_fallo text,
  iniciada_por uuid NOT NULL REFERENCES perfil_usuario ON DELETE RESTRICT,
  inicio timestamptz NOT NULL DEFAULT now(),
  fin timestamptz
);
CREATE INDEX ix_ejecucion_version_estado ON ejecucion (version_id, estado);
CREATE UNIQUE INDEX ux_una_en_curso_por_target ON ejecucion (target) WHERE estado = 'en_curso';

CREATE TABLE resultado_pronostico (
  ejecucion_id uuid NOT NULL REFERENCES ejecucion ON DELETE RESTRICT,
  ubigeo char(6) NOT NULL REFERENCES distrito ON DELETE RESTRICT,
  estrategia text NOT NULL CHECK (estrategia IN ('local','global','naive1','naive_estacional')),
  variante text NOT NULL CHECK (variante IN ('E1','E1b','base')),
  fecha_origen date NOT NULL,
  fecha_objetivo date NOT NULL,
  estimado double precision NOT NULL CHECK (estimado >= 0),
  observado int CHECK (observado >= 0),
  PRIMARY KEY (ejecucion_id, ubigeo, estrategia, variante, fecha_origen, fecha_objetivo)
);
CREATE INDEX ix_resultado_consulta ON resultado_pronostico (ejecucion_id, ubigeo, estrategia, fecha_objetivo);

CREATE TABLE metrica_desempeno (
  ejecucion_id uuid NOT NULL REFERENCES ejecucion ON DELETE RESTRICT,
  ubigeo char(6) NOT NULL REFERENCES distrito ON DELETE RESTRICT,
  estrategia text NOT NULL CHECK (estrategia IN ('local','global','naive1','naive_estacional')),
  variante text NOT NULL CHECK (variante IN ('E1','E1b','base')),
  periodo text NOT NULL CHECK (periodo IN ('general','pre_break','post_break')),
  metrica text NOT NULL CHECK (metrica IN ('MASE','MAE','RMSE')),
  valor double precision,
  motivo_nulo text,
  PRIMARY KEY (ejecucion_id, ubigeo, estrategia, variante, periodo, metrica),
  CHECK (valor IS NOT NULL OR motivo_nulo IS NOT NULL)
);
CREATE INDEX ix_metrica_consulta ON metrica_desempeno (ejecucion_id, periodo, metrica);

CREATE TABLE ficha_informativa (
  ficha_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  config_id uuid NOT NULL REFERENCES configuracion_experimento ON DELETE RESTRICT,
  secciones jsonb NOT NULL,
  version text NOT NULL
);

CREATE TABLE evento_auditoria (
  evento_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  actor_id uuid REFERENCES perfil_usuario ON DELETE RESTRICT,
  accion text NOT NULL,
  objeto_tipo text NOT NULL,
  objeto_id text,
  ocurrido_en timestamptz NOT NULL DEFAULT now(),
  detalle jsonb
);

-- Inmutabilidad (RF-06, ADR-04): sin UPDATE/DELETE sobre datos y resultados; version_datos solo cambia 'estado'.
CREATE FUNCTION rechazar_modificacion() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'La tabla % es inmutable: registra una versión nueva en lugar de modificarla.', TG_TABLE_NAME
    USING ERRCODE = 'integrity_constraint_violation';
END $$;

CREATE TRIGGER inmutable_observacion BEFORE UPDATE OR DELETE ON observacion_mensual
  FOR EACH ROW EXECUTE FUNCTION rechazar_modificacion();
CREATE TRIGGER inmutable_validacion BEFORE UPDATE OR DELETE ON validacion_version
  FOR EACH ROW EXECUTE FUNCTION rechazar_modificacion();
CREATE TRIGGER inmutable_resultado BEFORE UPDATE OR DELETE ON resultado_pronostico
  FOR EACH ROW EXECUTE FUNCTION rechazar_modificacion();
CREATE TRIGGER inmutable_metrica BEFORE UPDATE OR DELETE ON metrica_desempeno
  FOR EACH ROW EXECUTE FUNCTION rechazar_modificacion();
CREATE TRIGGER inmutable_auditoria BEFORE UPDATE OR DELETE ON evento_auditoria
  FOR EACH ROW EXECUTE FUNCTION rechazar_modificacion();

CREATE FUNCTION proteger_version_datos() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'Las versiones de datos no se borran.' USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF (NEW.version_id, NEW.nombre_archivo, NEW.periodo_corte, NEW.version, NEW.sha256, NEW.ruta_archivo, NEW.registrada_por, NEW.registrada_en)
     IS DISTINCT FROM
     (OLD.version_id, OLD.nombre_archivo, OLD.periodo_corte, OLD.version, OLD.sha256, OLD.ruta_archivo, OLD.registrada_por, OLD.registrada_en) THEN
    RAISE EXCEPTION 'Una versión de datos no se edita: solo cambia su estado.' USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER inmutable_version BEFORE UPDATE OR DELETE ON version_datos
  FOR EACH ROW EXECUTE FUNCTION proteger_version_datos();

-- Los 43 distritos se cargan en la migración 0002.
"""

TABLAS = [
    "evento_auditoria", "ficha_informativa", "metrica_desempeno", "resultado_pronostico", "ejecucion",
    "configuracion_experimento", "observacion_mensual", "equivalencia_distrito", "registro_pendiente",
    "validacion_version", "version_datos", "distrito", "token_activacion", "perfil_usuario",
]


def upgrade() -> None:
    op.execute(SQL_SUBIDA)


def downgrade() -> None:
    for t in ("proteger_version_datos", "rechazar_modificacion"):
        op.execute(f"DROP FUNCTION IF EXISTS {t}() CASCADE")
    for t in TABLAS:
        op.execute(f"DROP TABLE IF EXISTS {t} CASCADE")
