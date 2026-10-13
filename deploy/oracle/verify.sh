#!/usr/bin/env bash
#
# verify.sh — cheques post-deploy del backend vivo.
# Uso:  sudo bash /opt/vigilante/deploy/oracle/verify.sh
# Falla (exit != 0) si algo esta mal. No imprime secretos.
#
set -euo pipefail

REPO="${VIGILANTE_REPO:-/opt/vigilante}"
ESTADO="$REPO/estado.json"
FALLOS=0

ok()   { echo "OK   $*"; }
fail() { echo "FALLO $*"; FALLOS=$((FALLOS + 1)); }

echo "== 1) timers y servicios systemd =="
for u in vigilante-bot.timer vigilante-oyente.timer; do
  if systemctl is-active --quiet "$u"; then ok "$u activo"; else fail "$u NO activo (systemctl enable --now $u)"; fi
  if systemctl is-enabled --quiet "$u" 2>/dev/null; then ok "$u habilitado"; else fail "$u NO habilitado"; fi
done
for u in vigilante-bot.service vigilante-oyente.service; do
  res=$(systemctl show -p Result --value "$u" 2>/dev/null || echo "?")
  if [ "$res" = "success" ] || [ "$res" = "" ] || [ "$res" = "?" ]; then ok "$u ultima ejecucion: ${res:-sin datos}"; else fail "$u ultima ejecucion fallo: $res (journalctl -u $u -n 50)"; fi
done

echo "== 2) estado.json fresco (<10 min) =="
if [ -f "$ESTADO" ]; then
  ahora=$(date +%s)
  mt=$(stat -c %Y "$ESTADO" 2>/dev/null || stat -f %m "$ESTADO" 2>/dev/null || echo 0)
  edad=$((ahora - mt))
  if [ "$edad" -lt 600 ]; then ok "estado.json edad ${edad}s"; else fail "estado.json viejo: ${edad}s (>600s). Mira journalctl -u vigilante-bot.service"; fi
  if python3 -c "import json;json.load(open('$ESTADO',encoding='utf-8'))" 2>/dev/null; then ok "estado.json es JSON valido"; else fail "estado.json NO es JSON valido"; fi
else
  fail "$ESTADO no existe (el bot aun no corrio: systemctl start vigilante-bot.service)"
fi

echo "== 3) puerto 8000 SOLO localhost =="
if command -v ss >/dev/null 2>&1; then
  escuchas=$(ss -ltn 2>/dev/null | awk '$4 ~ /:8000$/ {print $4}' || true)
  if [ -z "$escuchas" ]; then
    echo "AVISO serve-estado.py no parece estar escuchando en :8000 (arrancalo si lo necesitas)."
  else
    echo "$escuchas" | while read -r l; do
      case "$l" in
        127.0.0.1:8000|\[::1\]:8000) echo "OK    escucha local: $l" ;;
        *) echo "FALLO expuesto a red: $l (debe ser 127.0.0.1:8000)"; exit 1 ;;
      esac
    done || FALLOS=$((FALLOS + 1))
  fi
else
  echo "AVISO ss no instalado; no puedo comprobar el puerto (apt install iproute2)."
fi

echo "== 4) secretos (sin mostrar valores) =="
if [ -f /etc/vigilante/env ]; then
  perms=$(stat -c %a /etc/vigilante/env 2>/dev/null || stat -f %Lp /etc/vigilante/env 2>/dev/null || echo "?")
  if [ "$perms" = "600" ]; then ok "/etc/vigilante/env existe con 600"; else fail "/etc/vigilante/env con permisos $perms (haz chmod 600)"; fi
else
  fail "/etc/vigilante/env no existe (crealo segun README_DEPLOY.md paso 6)"
fi

echo "----------------------------------------"
if [ "$FALLOS" -eq 0 ]; then echo "TODO OK"; else echo "$FALLOS chequeo(s) en FALLO"; exit 1; fi
