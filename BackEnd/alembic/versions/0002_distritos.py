"""Los 43 distritos de Lima Metropolitana (UBIGEO 1501xx). Datos de referencia, no de usuario."""
from alembic import op

revision = "0002"
down_revision = "0001"

SQL = """
INSERT INTO distrito(ubigeo, nombre) VALUES
  ('150101', 'LIMA'),
  ('150102', 'ANCON'),
  ('150103', 'ATE'),
  ('150104', 'BARRANCO'),
  ('150105', 'BREÑA'),
  ('150106', 'CARABAYLLO'),
  ('150107', 'CHACLACAYO'),
  ('150108', 'CHORRILLOS'),
  ('150109', 'CIENEGUILLA'),
  ('150110', 'COMAS'),
  ('150111', 'EL AGUSTINO'),
  ('150112', 'INDEPENDENCIA'),
  ('150113', 'JESUS MARIA'),
  ('150114', 'LA MOLINA'),
  ('150115', 'LA VICTORIA'),
  ('150116', 'LINCE'),
  ('150117', 'LOS OLIVOS'),
  ('150118', 'LURIGANCHO - CHOSICA'),
  ('150119', 'LURIN'),
  ('150120', 'MAGDALENA DEL MAR'),
  ('150121', 'PUEBLO LIBRE'),
  ('150122', 'MIRAFLORES'),
  ('150123', 'PACHACAMAC'),
  ('150124', 'PUCUSANA'),
  ('150125', 'PUENTE PIEDRA'),
  ('150126', 'PUNTA HERMOSA'),
  ('150127', 'PUNTA NEGRA'),
  ('150128', 'RIMAC'),
  ('150129', 'SAN BARTOLO'),
  ('150130', 'SAN BORJA'),
  ('150131', 'SAN ISIDRO'),
  ('150132', 'SAN JUAN DE LURIGANCHO'),
  ('150133', 'SAN JUAN DE MIRAFLORES'),
  ('150134', 'SAN LUIS'),
  ('150135', 'SAN MARTIN DE PORRES'),
  ('150136', 'SAN MIGUEL'),
  ('150137', 'SANTA ANITA'),
  ('150138', 'SANTA MARIA DEL MAR'),
  ('150139', 'SANTA ROSA'),
  ('150140', 'SANTIAGO DE SURCO'),
  ('150141', 'SURQUILLO'),
  ('150142', 'VILLA EL SALVADOR'),
  ('150143', 'VILLA MARIA DEL TRIUNFO');
"""


def upgrade() -> None:
    op.execute(SQL)


def downgrade() -> None:
    op.execute("DELETE FROM distrito WHERE ubigeo LIKE '1501__'")
