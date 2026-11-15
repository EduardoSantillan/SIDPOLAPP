#!/bin/sh
# RNF-04: busca secretos en el repositorio con gitleaks (en Docker; no hay que instalar nada). Falla si encuentra alguno.
# Uso, desde la carpeta del proyecto:  sh BackEnd/scripts/escanear_secretos.sh
set -eu
RAIZ="$(cd "$(dirname "$0")/../.." && pwd)"
docker run --rm -v "$RAIZ:/repo:ro" zricethezav/gitleaks:latest dir /repo --config /repo/.gitleaks.toml --redact --no-banner --exit-code 1
