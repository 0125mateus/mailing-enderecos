#!/usr/bin/env bash
# Instala Docker e sobe o Enriquecimento NIO em Ubuntu 22.04/24.04 (Hetzner, DigitalOcean, etc.)
set -o errexit

if [ "$(id -u)" -ne 0 ]; then
  echo "Execute como root: sudo bash deploy/setup-vps.sh"
  exit 1
fi

echo "==> Instalando Docker..."
if ! command -v docker >/dev/null 2>&1; then
  apt-get update
  apt-get install -y ca-certificates curl git
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc
  echo \
    "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu \
    $(. /etc/os-release && echo "${VERSION_CODENAME}") stable" \
    > /etc/apt/sources.list.d/docker.list
  apt-get update
  apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
fi

APP_DIR="${APP_DIR:-/opt/mailing-enderecos}"
REPO_URL="${REPO_URL:-https://github.com/0125mateus/mailing-enderecos.git}"

echo "==> Clonando/atualizando repositório em ${APP_DIR}..."
if [ ! -d "${APP_DIR}/.git" ]; then
  git clone "${REPO_URL}" "${APP_DIR}"
else
  git -C "${APP_DIR}" pull --ff-only
fi

cd "${APP_DIR}"

if [ ! -f .env ]; then
  cp deploy/env.vps.example .env
  mkdir -p playwright
  echo
  echo "Arquivo .env criado. Edite antes de continuar:"
  echo "  nano ${APP_DIR}/.env"
  echo
  echo "Campos obrigatórios: DOMAIN, SECRET_KEY, POSTGRES_PASSWORD, DATABASE_URL (mesma senha)"
  echo "Depois rode novamente: sudo bash deploy/setup-vps.sh"
  exit 0
fi

echo "==> Build e start (Docker Compose)..."
docker compose up -d --build

echo
echo "Deploy iniciado."
echo "Ver logs: docker compose -f ${APP_DIR}/docker-compose.yml logs -f web"
echo "Site: https://$(grep '^DOMAIN=' .env | cut -d= -f2)"
echo
echo "Próximo passo: enviar sessão Google (google-auth.json) — veja deploy/DEPLOY.md"
