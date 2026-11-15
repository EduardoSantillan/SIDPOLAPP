#!/bin/sh
# Respaldo diario: pg_dump (formato custom) + CSV originales, en el volumen «respaldos». Conserva RETENER_DIAS días.
# Variables: PGHOST PGUSER PGPASSWORD PGDATABASE (las usa pg_dump), RETENER_DIAS (14), UNA_VEZ=1 (una sola copia y salir).
# La copia fuera de la VM se hace aparte (scp/rsync del volumen); aquí solo queda dentro del servidor.
set -u
DESTINO=/respaldos
DIAS="${RETENER_DIAS:-14}"

respaldar() {
    marca=$(date -u +%Y%m%d_%H%M%S)
    if pg_dump -Fc -f "$DESTINO/sidpol_$marca.dump.tmp"; then
        mv "$DESTINO/sidpol_$marca.dump.tmp" "$DESTINO/sidpol_$marca.dump"
        tar czf "$DESTINO/csv_$marca.tar.gz" -C /datos/csv . 2>/dev/null
        echo "respaldo $marca: ok ($(du -h "$DESTINO/sidpol_$marca.dump" | cut -f1))"
        find "$DESTINO" -type f \( -name 'sidpol_*.dump' -o -name 'csv_*.tar.gz' \) -mtime +"$DIAS" -delete
        return 0
    fi
    rm -f "$DESTINO/sidpol_$marca.dump.tmp"
    echo "respaldo $marca: FALLÓ" >&2
    return 1
}

while true; do
    if respaldar; then espera=86400; else espera=3600; fi   # si falla, reintenta en una hora
    [ "${UNA_VEZ:-0}" = "1" ] && exit 0
    sleep "$espera"
done
