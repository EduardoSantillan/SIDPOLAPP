#!/bin/sh
# Restaura un respaldo en la base indicada por PGDATABASE (por defecto, la de la plataforma).
# Uso (con la plataforma detenida salvo db):
#   docker compose run --rm --entrypoint /bin/sh respaldo /respaldo/restaurar.sh /respaldos/sidpol_AAAAMMDD_HHMMSS.dump
set -eu
[ $# -eq 1 ] || { echo "Uso: restaurar.sh /respaldos/sidpol_AAAAMMDD_HHMMSS.dump" >&2; exit 2; }
pg_restore --clean --if-exists --no-owner -d "${PGDATABASE:-sidpol}" "$1"
echo "restaurado: $1"
