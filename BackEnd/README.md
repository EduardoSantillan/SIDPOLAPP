# SIDPOL: backend

La API y los servicios de ingesta y modelado, todo en una sola máquina con Docker Compose. Python 3.11 para la API y la ingesta, Python 3.13 para el modelado (por XGBoost), FastAPI, PostgreSQL 16 y Nginx.

## Primera instalación

1. **Claves.** Copia `.env.example` como `.env` (nunca se sube al repositorio) y cambia los valores por claves aleatorias. Para generarlas: `python -c "import secrets; print(secrets.token_urlsafe(48))"`. Si una clave es corta o sigue siendo la de ejemplo, la API no arranca.
2. **Certificado HTTPS.** Deja `fullchain.pem` y `privkey.pem` en `nginx/certs/`, ya sea el de la institución o uno de Let's Encrypt. Para probar en una máquina de desarrollo sirve uno autofirmado: `sh scripts/certificado_local.sh`.
3. **Pantallas.** Nginx sirve la aplicación ya compilada desde `FRONT_DIST` (por defecto `nginx/html`, que solo trae una página provisional). Para usar la real, compila `FrontEnd` con `npm run build` y apunta `FRONT_DIST` a su carpeta `dist`.
4. **Levantar todo.** `docker compose up -d --build`. Las migraciones de la base corren solas antes de iniciar la API.
5. **Primera cuenta de administrador.** `docker compose exec api python -m common.crear_admin "Nombre" correo@ejemplo.pe` imprime un enlace para que esa persona elija su contraseña.
6. **Configuración del experimento.** `docker compose exec api python -m common.registrar_config` la registra sin aprobarla. Aprobarla (con `--aprobar`) es decisión del equipo y del asesor, y hasta entonces la plataforma no calcula nada.

## Qué queda expuesto

Solo Nginx: el puerto 80, que redirige al 443, y el 443 con TLS 1.2 o superior. Las pantallas se sirven en `/` y la API en `/api/`. La base de datos, la API, la ingesta y el modelado solo se ven dentro de la red de Docker. La documentación interactiva de la API (`/api/docs`) no se publica.

## Día a día

- **Actualizar:** `git pull` y `docker compose up -d --build`.
- **Ver cómo está todo:** `docker compose ps` (cada servicio tiene su chequeo de salud). Los registros se leen con `docker compose logs -f nginx api modelado`, y cada petición lleva su `request_id`.
- **Respaldos:** el servicio `respaldo` guarda cada 24 horas un `pg_dump` y una copia de los CSV originales en el volumen `respaldos`, y conserva 14 días. Falta copiarlos fuera de la máquina, por ejemplo con `docker run --rm -v sidpolapp_respaldos:/r -v $PWD:/o alpine tar czf /o/respaldos.tgz -C /r .` y después `scp`.
- **Restaurar:** `docker compose run --rm --entrypoint /bin/sh respaldo /respaldo/restaurar.sh /respaldos/sidpol_AAAAMMDD_HHMMSS.dump`.
- **Buscar secretos antes de entregar:** `sh scripts/escanear_secretos.sh` (corre gitleaks dentro de Docker con la configuración de `../.gitleaks.toml`).

## Para desarrollar

`docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build` publica la API en http://localhost:8000, con `/docs` y `/openapi.json`. De ahí el frontend saca sus tipos.

Las pruebas necesitan una PostgreSQL aparte y, las de modelado, Python 3.12 o más con XGBoost 3.4.1:

```
docker run -d --rm --name pg-test -e POSTGRES_PASSWORD=t -e POSTGRES_DB=t -p 55432:5432 postgres:16
TEST_DATABASE_URL=postgresql+psycopg://postgres:t@localhost:55432/t pytest              # todo, unos 5 minutos
TEST_DATABASE_URL=postgresql+psycopg://postgres:t@localhost:55432/t pytest -m "not lento"   # sin entrenar sobre el panel real, unos 2 minutos
```
