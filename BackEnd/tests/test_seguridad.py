"""Paso 8: endurecimiento (RNF-02, RNF-04, RNF-09, RNF-11). Revisa la configuración de despliegue y lo que el código promete."""
import re
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

RAIZ = Path(__file__).resolve().parents[1]
PROYECTO = RAIZ.parent
NGINX = (RAIZ / "nginx" / "default.conf").read_text(encoding="utf-8")
COMPOSE = yaml.safe_load((RAIZ / "docker-compose.yml").read_text(encoding="utf-8"))
SERVICIOS = COMPOSE["services"]


# ---------- RNF-02: todo por HTTPS, TLS >= 1.2 ----------
def test_nginx_solo_acepta_tls_1_2_o_mayor_y_redirige_el_80():
    protocolos = re.findall(r"ssl_protocols\s+([^;]+);", NGINX)
    assert protocolos == ["TLSv1.2 TLSv1.3"]
    assert re.search(r"listen 80;.*?return 301 https://\$host\$request_uri;", NGINX, re.S)
    assert "server_tokens off;" in NGINX


def test_nginx_envia_las_cabeceras_de_seguridad_y_oculta_la_documentacion():
    for cab in ("Strict-Transport-Security", "X-Content-Type-Options", "X-Frame-Options", "Referrer-Policy", "Content-Security-Policy"):
        assert f"add_header {cab}" in NGINX, cab
    assert "frame-ancestors 'none'" in NGINX
    assert re.search(r"/api/\(docs\|redoc\|openapi", NGINX)  # /api/docs y /api/openapi.json → 404


def test_nginx_limita_el_inicio_de_sesion_y_el_tamano_de_los_cuerpos():
    assert "limit_req_zone $binary_remote_addr zone=acceso:10m rate=10r/m;" in NGINX
    assert re.search(r"location = /api/auth/login \{[^}]*limit_req zone=acceso[^}]*client_max_body_size 4k;", NGINX, re.S)
    assert re.search(r"location = /api/versiones \{[^}]*client_max_body_size 45m;", NGINX, re.S)  # el CSV nacional pesa ~27 MB
    assert "X-Forwarded-For $remote_addr;" in (RAIZ / "nginx" / "proxy.inc").read_text(encoding="utf-8")  # reemplaza: no se puede falsear la IP


# ---------- RNF-11 y despliegue: solo Nginx publica puertos ----------
def test_solo_nginx_publica_puertos_y_la_base_no_es_alcanzable_desde_fuera():
    publicos = {n: s["ports"] for n, s in SERVICIOS.items() if "ports" in s}
    assert list(publicos) == ["nginx"] and publicos["nginx"] == ["80:80", "443:443"]
    assert "expose" in SERVICIOS["api"] and all("ports" not in SERVICIOS[n] for n in ("db", "api", "ingesta", "modelado", "respaldo"))


def test_el_compose_no_trae_secretos_y_endurece_los_contenedores():
    assert "${POSTGRES_PASSWORD" in str(SERVICIOS["db"]["environment"]["POSTGRES_PASSWORD"])
    for n in ("api", "ingesta", "modelado", "nginx"):
        s = SERVICIOS[n]
        assert s["restart"] == "unless-stopped" and "no-new-privileges:true" in s["security_opt"] and s["cap_drop"] == ["ALL"], n
    for n in ("api", "ingesta", "modelado"):
        assert "healthcheck" in SERVICIOS[n], n
    assert "FORWARDED_ALLOW_IPS" in SERVICIOS["api"]["environment"]
    assert "respaldo" in SERVICIOS and "RETENER_DIAS" in SERVICIOS["respaldo"]["environment"]  # respaldo diario
    dev = yaml.safe_load((RAIZ / "docker-compose.dev.yml").read_text(encoding="utf-8"))
    assert dev["services"]["api"]["ports"] == ["8000:8000"] and dev["services"]["api"]["environment"]["ENTORNO"] == "desarrollo"


# ---------- RNF-04: sin secretos en el repositorio ----------
def test_el_gitignore_protege_las_claves_y_el_ejemplo_es_inofensivo():
    ignorado = (PROYECTO / ".gitignore").read_text(encoding="utf-8").split()
    assert {".env", "*.pem", "BackEnd/nginx/certs/", ".venv/"} <= set(ignorado)
    ejemplo = (RAIZ / ".env.example").read_text(encoding="utf-8")
    for clave in ("JWT_SECRET", "CLAVE_SERVICIO"):
        assert re.search(rf"^{clave}=reemplazar", ejemplo, re.M)
    from pydantic import ValidationError

    from common.config import Settings
    with pytest.raises(ValidationError):  # copiar el ejemplo tal cual no deja arrancar la app
        Settings(database_url="postgresql+psycopg://x", jwt_secret="reemplazar-con-48-caracteres-aleatorios-minimo-32", clave_servicio="s" * 40)


PATRONES = [re.compile(r"-----BEGIN (RSA |EC |OPENSSH |)PRIVATE KEY-----"),
            re.compile(r"(?i)(secret|password|passwd|token|api_?key)\w*\s*[:=]\s*['\"][A-Za-z0-9+/_\-]{24,}['\"]"),
            re.compile(r"AKIA[0-9A-Z]{16}")]


def test_ningun_archivo_versionable_trae_claves_ni_contrasenas_literales():
    omitir = {".env", "certs", "__pycache__", ".pytest_cache", ".venv", "venv", "fixtures"}
    hallazgos = []
    for ruta in RAIZ.rglob("*"):
        if not ruta.is_file() or omitir & set(ruta.relative_to(RAIZ).parts) or ruta.suffix not in {".py", ".yml", ".yaml", ".conf", ".inc", ".json", ".md", ".sh", ".toml", ".ini", ".txt", ".html"}:
            continue
        if ruta.name == "test_seguridad.py":
            continue
        texto = ruta.read_text(encoding="utf-8", errors="ignore")
        hallazgos += [f"{ruta.relative_to(RAIZ)}: {m.group(0)[:40]}" for p in PATRONES for m in p.finditer(texto)]
    assert not hallazgos, hallazgos


# ---------- API: documentación oculta y request_id saneado ----------
@pytest.fixture(scope="module")
def cliente():
    from api_plataforma.main import app
    return TestClient(app, raise_server_exceptions=False)


def test_en_produccion_no_se_publica_la_documentacion_interactiva(cliente):
    for ruta in ("/docs", "/redoc", "/openapi.json"):
        assert cliente.get(ruta).status_code == 404, ruta


def test_el_request_id_que_llega_de_fuera_solo_se_copia_si_es_inofensivo(cliente):
    ok = cliente.get("/health", headers={"x-request-id": "abc-123-DEF-456"})
    assert ok.headers["x-request-id"] == "abc-123-DEF-456"
    for malo in ("x", 'a"}{"servicio":"falso', "a" * 200, "con espacios y ñ"):
        try:
            r = cliente.get("/health", headers={"x-request-id": malo})
        except Exception:  # algunos valores ni siquiera pueden viajar como cabecera
            continue
        assert r.headers["x-request-id"] != malo and re.fullmatch(r"[0-9a-f]{12}", r.headers["x-request-id"])
