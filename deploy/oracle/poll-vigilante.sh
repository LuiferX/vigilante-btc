#!/usr/bin/env bash
#
# poll-vigilante.sh — un ciclo del bot (parte + dashboard).
# Lo dispara systemd cada 5 min (vigilante-bot.timer). También sirve para
# correrlo a mano:  sudo -u vigilante bash /opt/vigilante/deploy/oracle/poll-vigilante.sh
#
# Repo esperado: /opt/vigilante  (override: VIGILANTE_REPO=/otra/ruta)
# Secretos: /etc/vigilante/env  (archivo creado A MANO por el usuario, NO va en git)
#   Contenido esperado:
#     TELEGRAM_BOT_TOKEN=tu_token_aqui
#     TELEGRAM_CHAT_ID=tu_chat_id_aqui
#   Permisos recomendados:  chmod 600 /etc/vigilante/env ; chown root:vigilante
#
set -euo pipefail

REPO="${VIGILANTE_REPO:-/opt/vigilante}"
ENV_FILE="${VIGILANTE_ENV:-/etc/vigilante/env}"

export PYTHONIOENCODING=utf-8

if [ -f "$ENV_FILE" ]; then
  set -a
  # shellcheck disable=SC1090
  . "$ENV_FILE"
  set +a
else
  echo "AVISO: no existe $ENV_FILE; sigo sin secretos (solo lectura publica)." >&2
fi

if [ ! -d "$REPO" ]; then
  echo "ERROR: no existe el repo en $REPO (VIGILANTE_REPO mal puesto?)" >&2
  exit 1
fi

cd "$REPO"

if [ ! -f vigilante_cloud.py ]; then
  echo "ERROR: $REPO/vigilante_cloud.py no encontrado" >&2
  exit 1
fi

echo "[poll] $(date -u +%FT%TZ) repo=$REPO"
python3 vigilante_cloud.py

if [ -f dashboard.py ]; then
  python3 dashboard.py
else
  echo "AVISO: dashboard.py no encontrado, salto el dashboard." >&2
fi

echo "[poll] OK $(date -u +%FT%TZ)"
