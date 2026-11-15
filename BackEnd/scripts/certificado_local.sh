#!/bin/sh
# Genera un certificado AUTOFIRMADO para probar HTTPS en una máquina de desarrollo.
# En la VM real se usa el certificado de la institución o de Let's Encrypt (fullchain.pem y privkey.pem en nginx/certs/).
set -eu
DIR="$(dirname "$0")/../nginx/certs"
mkdir -p "$DIR"
openssl req -x509 -nodes -newkey rsa:2048 -days 365 -subj "/CN=localhost" \
    -addext "subjectAltName=DNS:localhost,IP:127.0.0.1" \
    -keyout "$DIR/privkey.pem" -out "$DIR/fullchain.pem"
chmod 600 "$DIR/privkey.pem"
echo "Certificado de prueba creado en $DIR (no se sube al repositorio)."
