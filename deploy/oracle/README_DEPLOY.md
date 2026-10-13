# Despliegue Vigilante en Oracle Cloud Always Free (Ashburn) — backend vivo

Pack **sin aprovisionar nada real**: no hay credenciales aquí, todo lo ejecutas tú
en tu cuenta OCI. Costo esperado: **$0/mes** (límites Always Free).

> Fallback si Oracle te bota la instancia (reclamos de capacidad en Ashburn):
> **Contabo VPS S (~$5.50/mes)**. Los mismos scripts/systemd sirven tal cual,
> solo cambia la IP.

Sin secretos en este repo. Donde veas `<TU_IP>` / `<TU_USUARIO>` sustituye
con tus datos. Nunca pegues tokens en issues ni commits.

---

## 0. Qué instala esto

| Pieza | Qué hace | Cada cuánto |
|---|---|---|
| `poll-vigilante.sh` + `vigilante-bot.service/.timer` | `vigilante_cloud.py` (parte) + `dashboard.py` (docs/index.html) | 5 min |
| `vigilante-oyente.service/.timer` | `comandos.py` si existe; si no, repite el poll | 1 min |
| `serve-estado.py` | HTTP solo-localhost `:8000` con `docs/` + `estado.json` | siempre (systemd) |
| `verify.sh` | cheques post-deploy | manual |

El bot **solo lee API pública** (sin API keys, sin trading). Los secretos de
Telegram viven SOLO en el servidor en `/etc/vigilante/env` (archivo que creas
tú, **NO** incluido en el repo), con `chmod 600`.

---

## 1. Crear cuenta OCI (Ashburn)

1. Regístrate en Oracle Cloud (capa Always Free) y entra a la consola.
2. Fija la región en **US East (Ashburn)** — ahí están los Ampere Always Free.
3. Crea un compartimento (ej. `vigilante`) para no mezclar con nada más.

## 2. Crear la instancia (Ampere, o AMD si no hay capacidad)

1. Compute → Instances → Create instance.
2. Imagen: **Ubuntu 22.04** (o Canonical Ubuntu 24.04).
3. Shape: primero **`VM.Standard.A1.Flex` (Ampere, ARM)** con **4 OCPU / 24 GB**
   (máximo Always Free). Si Ashburn dice "out of capacity", prueba
   `VM.Standard.E2.1.Micro` (AMD, 1 OCPU / 1 GB) — también Always Free.
4. Clave SSH: **genera una nueva y descarga el `.key`** (o sube tu `~/.ssh/id_*.pub`).
5. VCN: crea una nueva con subred pública, IP pública efímera.
6. Anota la IP pública: `<TU_IP>`.

> Si Ashburn te rechaza el Ampere varios días seguidos: cambia de zona de
> disponibilidad (AD-1/AD-2/AD-3) o usa el fallback **Contabo VPS S $5.50/mes**.

## 3. Reglas de red: SSH + puerto 8000 SOLO localhost

1. SSH (22) desde tu IP: en el Security List permite `0.0.0.0/0:22` solo durante
   la instalación, o mejor tu IP (`<TU_IP_OFICINA>/32:22`) si es fija.
2. **El puerto 8000 NO se abre en OCI.** `serve-estado.py` escucha SOLO en
   `127.0.0.1:8000`. Verifícalo con `verify.sh` (falla si escucha en `0.0.0.0`).
3. La Page pública (`docs/index.html` en GitHub Pages) puede leer `estado.json`
   por `fetch` **solo si tú lo expones**. Por defecto va por `git push` de
   `docs/`, **NO** por conexión directa al servidor.
4. ⚠️ **NO expongas `:8000` a internet sin auth** (sin reverse proxy + usuario/
   clave o túnel SSH). Tal cual viene, es localhost a propósito.

## 4. Conectar por SSH y preparar el servidor

Desde tu PC (sustituye `<TU_USUARIO>` = `ubuntu`, `<TU_IP>` = IP de la instancia):

```bash
ssh -i ~/.ssh/tu_llave.key <TU_USUARIO>@<TU_IP>
sudo apt update && sudo apt install -y python3 git
sudo useradd -r -m -s /usr/sbin/nologin vigilante || true
sudo mkdir -p /opt/vigilante /etc/vigilante
sudo chown vigilante:vigilante /opt/vigilante
sudo chmod 700 /etc/vigilante
```

## 5. Copiar el repo

```bash
# Como <TU_USUARIO>, clona o copia el repo a /opt/vigilante
sudo -u vigilante git clone <URL_DE_TU_REPO> /opt/vigilante
# (o: scp -r . <TU_USUARIO>@<TU_IP>:/tmp/repo && sudo -u vigilante cp -r /tmp/repo/* /opt/vigilante/)
ls /opt/vigilante/vigilante_cloud.py /opt/vigilante/dashboard.py
```

## 6. Secretos en /etc/vigilante/env (SOLO en el servidor, chmod 600)

Crea el archivo a mano en el servidor (NO está en el repo, NO lo commitees):

```bash
sudo tee /etc/vigilante/env >/dev/null <<'EOF'
TELEGRAM_BOT_TOKEN=tu_token_aqui
TELEGRAM_CHAT_ID=tu_chat_id_aqui
EOF
sudo chmod 600 /etc/vigilante/env
sudo chown root:vigilante /etc/vigilante/env
```

`poll-vigilante.sh` lo carga con `set -a; . /etc/vigilante/env; set +a`.
Comprueba nombres exactos: `TELEGRAM_BOT_TOKEN` y `TELEGRAM_CHAT_ID`
(ver `vigilante_cloud.py`: los lee de entorno).

## 7. Instalar systemd (bot cada 5 min + oyente cada 1 min + HTTP local)

```bash
cd /opt/vigilante/deploy/oracle
sudo cp vigilante-bot.service vigilante-oyente.service /etc/systemd/system/
sudo cp vigilante-bot.timer vigilante-oyente.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now vigilante-bot.timer vigilante-oyente.timer
```

**Servir estado en local (opcional):** `serve-estado.py` escucha solo en
`127.0.0.1:8000` con `docs/` + `estado.json` y `Cache-Control: no-store`:

```bash
# Sesión persistente mínima (localhost:8000, docs/ + estado.json, no-store):
sudo -u vigilante nohup python3 /opt/vigilante/deploy/oracle/serve-estado.py >/var/log/serve-estado.log 2>&1 &
ss -ltnp | grep 8000   # debe decir 127.0.0.1:8000, NUNCA 0.0.0.0:8000
```

## 8. Verificar

```bash
sudo bash /opt/vigilante/deploy/oracle/verify.sh
```

Debe decir OK en: timers activos, `estado.json` con edad < 10 min,
puerto 8000 solo en localhost. Si `estado.json` es viejo, mira logs:

```bash
sudo journalctl -u vigilante-bot.service -n 50 --no-pager
sudo journalctl -u vigilante-oyente.service -n 50 --no-pager
cat /etc/vigilante/env  # NO pegues su contenido en ningún lado
ls -l /opt/vigilante/estado.json /opt/vigilante/docs/index.html
```

## 9. GitHub Pages (opcional, sin exponer el servidor)

El servidor genera `docs/index.html` localmente. Para publicarlo haz `git push`
de `docs/` desde tu PC o añade un job que sincronice — nunca abras `:8000`.
La Page puede hacer `fetch('estado.json')` relativo (mismo origen Pages),
no contra tu OCI.

---

## Costos

- Oracle Always Free (Ampere 4 OCPU/24 GB o Micro AMD): **$0/mes** mientras
  respetes los límites. Vigila "Billing → Cost Analysis" por si aprovisionaste
  algo de pago por error.
- Fallback **Contabo VPS S: ~$5.50/mes** si Oracle reclama/recicla tu instancia
  (pasa en Ashburn). Mismos pasos desde el punto 4.

## Seguridad (resumen)

- Secretos solo en `/etc/vigilante/env`, `chmod 600`, nunca en git.
- SSH con llave, sin password. Desactiva password-auth si puedes.
- `:8000` en `127.0.0.1` únicamente. **NO abrir en Security List / iptables.**
- `Cache-Control: no-store` en `serve-estado.py` para no cachear estado.
