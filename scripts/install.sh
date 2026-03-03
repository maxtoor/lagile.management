#!/usr/bin/env bash
set -euo pipefail

# LAgile.Management zero-to-run installer for Linux hosts.
# It can install Docker (apt/dnf), clone/update the app, prepare .env, and start containers.

INSTALL_DIR="${INSTALL_DIR:-/opt/lagile-management}"
REPO_URL="${REPO_URL:-https://github.com/maxtoor/lagile.managemet.git}"
BRANCH="${BRANCH:-main}"
APP_USER="${APP_USER:-${SUDO_USER:-$USER}}"
APP_PORT="${APP_PORT:-8001}"
SKIP_DOCKER_INSTALL="${SKIP_DOCKER_INSTALL:-0}"
DRY_RUN="${DRY_RUN:-0}"

print_help() {
  cat <<'EOF'
Uso:
  bash scripts/install.sh [opzioni]

Opzioni:
  --install-dir PATH       Directory installazione (default: /opt/lagile-management)
  --repo-url URL           Repository git (default: repo ufficiale)
  --branch NAME            Branch/tag da usare (default: main)
  --app-user USER          Utente proprietario dei file (default: utente corrente/sudo)
  --port PORT              Porta pubblica web (default: 8001)
  --skip-docker-install    Non tenta l'installazione Docker
  --dry-run                Mostra le azioni senza applicare modifiche
  -h, --help               Mostra aiuto

Variabili ambiente equivalenti:
  INSTALL_DIR, REPO_URL, BRANCH, APP_USER, APP_PORT, SKIP_DOCKER_INSTALL, DRY_RUN
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --install-dir) INSTALL_DIR="$2"; shift 2 ;;
    --repo-url) REPO_URL="$2"; shift 2 ;;
    --branch) BRANCH="$2"; shift 2 ;;
    --app-user) APP_USER="$2"; shift 2 ;;
    --port) APP_PORT="$2"; shift 2 ;;
    --skip-docker-install) SKIP_DOCKER_INSTALL=1; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) print_help; exit 0 ;;
    *) echo "Opzione non riconosciuta: $1" >&2; exit 1 ;;
  esac
done

log() { printf '[install] %s\n' "$*"; }
err() { printf '[install][errore] %s\n' "$*" >&2; }
run_or_print() {
  if [[ "$DRY_RUN" == "1" ]]; then
    printf '[install][dry-run] %s\n' "$*"
  else
    "$@"
  fi
}

run_privileged() {
  if [[ "$(id -u)" -eq 0 ]]; then
    run_or_print "$@"
  else
    run_or_print sudo "$@"
  fi
}

run_as_app_user() {
  if [[ "$(id -u)" -eq 0 && "$APP_USER" != "root" ]]; then
    run_or_print sudo -u "$APP_USER" "$@"
  else
    run_or_print "$@"
  fi
}

docker_cmd() {
  if [[ "$DRY_RUN" == "1" ]]; then
    printf '[install][dry-run] docker %s\n' "$*"
    return 0
  fi
  if docker info >/dev/null 2>&1; then
    docker "$@"
  else
    run_privileged docker "$@"
  fi
}

require_linux() {
  if [[ "$(uname -s)" != "Linux" ]]; then
    err "Script supportato solo su Linux."
    exit 1
  fi
}

require_cmd() {
  local cmd="$1"
  if ! command -v "$cmd" >/dev/null 2>&1; then
    err "Comando richiesto non trovato: $cmd"
    exit 1
  fi
}

install_docker_apt() {
  log "Installazione Docker con apt..."
  run_privileged apt-get update -y
  run_privileged apt-get install -y ca-certificates curl gnupg lsb-release
  run_privileged install -m 0755 -d /etc/apt/keyrings
  if [[ ! -f /etc/apt/keyrings/docker.gpg ]]; then
    curl -fsSL https://download.docker.com/linux/"$(. /etc/os-release && echo "$ID")"/gpg \
      | run_privileged gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    run_privileged chmod a+r /etc/apt/keyrings/docker.gpg
  fi
  local codename arch
  codename="$(. /etc/os-release && echo "${VERSION_CODENAME:-}")"
  arch="$(dpkg --print-architecture)"
  if [[ -z "$codename" ]]; then
    codename="$(lsb_release -cs)"
  fi
  echo \
    "deb [arch=${arch} signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/$(. /etc/os-release && echo "$ID") ${codename} stable" \
    | run_privileged tee /etc/apt/sources.list.d/docker.list >/dev/null
  run_privileged apt-get update -y
  run_privileged apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
}

install_docker_dnf() {
  log "Installazione Docker con dnf..."
  run_privileged dnf -y install dnf-plugins-core
  run_privileged dnf config-manager --add-repo https://download.docker.com/linux/fedora/docker-ce.repo
  run_privileged dnf -y install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
}

ensure_docker() {
  if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
    log "Docker e Docker Compose già presenti."
    return
  fi

  if [[ "$SKIP_DOCKER_INSTALL" == "1" ]]; then
    err "Docker non trovato e --skip-docker-install attivo."
    exit 1
  fi

  if command -v apt-get >/dev/null 2>&1; then
    install_docker_apt
  elif command -v dnf >/dev/null 2>&1; then
    install_docker_dnf
  else
    err "Package manager non supportato automaticamente (apt/dnf). Installa Docker manualmente."
    exit 1
  fi

  run_privileged systemctl enable docker
  run_privileged systemctl start docker
}

ensure_docker_group_membership() {
  if id -nG "$APP_USER" | tr ' ' '\n' | grep -qx docker; then
    return
  fi
  log "Aggiungo l'utente '$APP_USER' al gruppo docker."
  run_privileged usermod -aG docker "$APP_USER"
  log "Nota: per usare docker senza sudo potrebbe servire logout/login dell'utente '$APP_USER'."
}

ensure_install_dir() {
  log "Preparo directory: $INSTALL_DIR"
  run_privileged mkdir -p "$INSTALL_DIR"
  run_privileged chown -R "$APP_USER":"$APP_USER" "$INSTALL_DIR"
}

clone_or_update_repo() {
  if [[ -d "$INSTALL_DIR/.git" ]]; then
    log "Repository già presente, aggiorno..."
    run_as_app_user git -C "$INSTALL_DIR" fetch --all --tags
    run_as_app_user git -C "$INSTALL_DIR" checkout "$BRANCH"
    run_as_app_user git -C "$INSTALL_DIR" pull --ff-only origin "$BRANCH"
  else
    log "Clono repository: $REPO_URL"
    run_as_app_user git clone --branch "$BRANCH" "$REPO_URL" "$INSTALL_DIR"
  fi
  run_privileged chown -R "$APP_USER":"$APP_USER" "$INSTALL_DIR"
}

setup_env() {
  local env_file="$INSTALL_DIR/.env"
  local env_example="$INSTALL_DIR/.env.example"

  if [[ ! -f "$env_example" ]]; then
    err "File non trovato: $env_example"
    exit 1
  fi

  if [[ ! -f "$env_file" ]]; then
    log "Creo .env da .env.example"
    run_as_app_user cp "$env_example" "$env_file"
  else
    log ".env già presente, non lo sovrascrivo."
  fi

  if ! grep -q '^DJANGO_SECRET_KEY=' "$env_file" || grep -q '^DJANGO_SECRET_KEY=change-me' "$env_file"; then
    local secret
    if command -v openssl >/dev/null 2>&1; then
      secret="$(openssl rand -hex 32)"
    else
      secret="$(date +%s)-$(od -An -N8 -tx1 /dev/urandom | tr -d ' \n')"
    fi
    if grep -q '^DJANGO_SECRET_KEY=' "$env_file"; then
      run_as_app_user sed -i.bak -E "s|^DJANGO_SECRET_KEY=.*|DJANGO_SECRET_KEY=${secret}|" "$env_file"
      run_as_app_user rm -f "$env_file.bak"
    else
      if [[ "$DRY_RUN" == "1" ]]; then
        printf '[install][dry-run] append DJANGO_SECRET_KEY to %s\n' "$env_file"
      else
        printf '\nDJANGO_SECRET_KEY=%s\n' "$secret" >> "$env_file"
      fi
    fi
  fi
}

ensure_logs_dir() {
  run_as_app_user mkdir -p "$INSTALL_DIR/logs"
  run_privileged chown -R "$APP_USER":"$APP_USER" "$INSTALL_DIR/logs"
}

set_compose_port() {
  local compose_file="$INSTALL_DIR/docker-compose.yml"
  if [[ ! -f "$compose_file" ]]; then
    err "File non trovato: $compose_file"
    exit 1
  fi
  # Patch only the web published port in a stable way.
  run_as_app_user sed -i.bak -E "s|\"[0-9]+:8000\"|\"${APP_PORT}:8000\"|" "$compose_file"
  run_as_app_user rm -f "$compose_file.bak"
}

start_stack() {
  log "Avvio stack Docker..."
  docker_cmd compose -f "$INSTALL_DIR/docker-compose.yml" --project-directory "$INSTALL_DIR" up -d --build
}

final_checks() {
  log "Stato container:"
  docker_cmd compose -f "$INSTALL_DIR/docker-compose.yml" --project-directory "$INSTALL_DIR" ps
  log "Installazione completata."
  log "URL applicazione: http://localhost:${APP_PORT}"
  log "Per vedere i log: docker compose -f $INSTALL_DIR/docker-compose.yml --project-directory $INSTALL_DIR logs -f"
}

main() {
  if [[ "$DRY_RUN" == "1" ]]; then
    log "Modalita dry-run attiva: nessuna modifica verra applicata."
  fi
  require_linux
  require_cmd git
  require_cmd sed
  ensure_docker
  ensure_docker_group_membership
  ensure_install_dir
  clone_or_update_repo
  setup_env
  ensure_logs_dir
  set_compose_port
  start_stack
  final_checks
}

main "$@"
