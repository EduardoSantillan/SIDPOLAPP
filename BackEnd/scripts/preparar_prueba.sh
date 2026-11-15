#!/bin/sh
# Levanta un entorno APARTE (proyecto «sidpol_prueba», con su propia base) y lo deja listo para la prueba con personas:
# cuentas de prueba, datos reales de SIDPOL y los cálculos de robo y hurto. No toca el entorno principal.
# Uso:  sh BackEnd/scripts/preparar_prueba.sh        (después:  cd FrontEnd && npm run dev  →  http://localhost:5173)
# Para borrar todo al terminar:  sh BackEnd/scripts/preparar_prueba.sh borrar
set -eu
cd "$(dirname "$0")/.."
C="docker compose -p sidpol_prueba -f docker-compose.yml -f docker-compose.dev.yml"
if [ "${1:-}" = "borrar" ]; then $C down -v; echo "Entorno de prueba borrado."; exit 0; fi
[ -f .env ] || { echo "Falta BackEnd/.env (copia .env.example y pon claves aleatorias)." >&2; exit 1; }
$C up -d --build db migrar api ingesta modelado
echo "Esperando a la API…"
until $C exec -T api python -c "import urllib.request;urllib.request.urlopen('http://localhost:8000/health')" 2>/dev/null; do sleep 2; done
$C exec -T api python -m common.preparar_prueba
echo
echo "Listo. Ahora abre otra terminal:  cd FrontEnd && npm install && npm run dev   y entra a http://localhost:5173"
