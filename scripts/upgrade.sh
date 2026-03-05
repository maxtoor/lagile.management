#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="${PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
BRANCH="${BRANCH:-main}"
BACKUP_DIR="${BACKUP_DIR:-$PROJECT_DIR/backups}"
DRY_RUN="${DRY_RUN:-0}"
SKIP_FETCH="${SKIP_FETCH:-0}"
SKIP_BACKUP="${SKIP_BACKUP:-0}"
SKIP_MIGRATE="${SKIP_MIGRATE:-0}"
ALLOW_DIRTY="${ALLOW_DIRTY:-0}"

print_help() {
  cat <<'EOF'
Uso:
  bash scripts/upgrade.sh [opzioni]

Opzioni:
  --project-dir PATH   Directory progetto (default: directory repo corrente)
  --branch NAME        Branch remoto da aggiornare (default: main)
  --backup-dir PATH    Directory backup (default: <project>/backups)
  --skip-fetch         Salta git fetch
  --skip-backup        Salta backup pre-upgrade
  --skip-migrate       Salta migrate e check post-upgrade
  --allow-dirty        Consenti upgrade anche con working tree non pulita
  --dry-run            Mostra azioni senza eseguirle
  -h, --help           Mostra aiuto
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --project-dir) PROJECT_DIR="$2"; shift 2 ;;
    --branch) BRANCH="$2"; shift 2 ;;
    --backup-dir) BACKUP_DIR="$2"; shift 2 ;;
    --skip-fetch) SKIP_FETCH=1; shift ;;
    --skip-backup) SKIP_BACKUP=1; shift ;;
    --skip-migrate) SKIP_MIGRATE=1; shift ;;
    --allow-dirty) ALLOW_DIRTY=1; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) print_help; exit 0 ;;
    *) echo "Opzione non riconosciuta: $1" >&2; exit 1 ;;
  esac
done

log() { printf '[upgrade] %s\n' "$*"; }
err() { printf '[upgrade][errore] %s\n' "$*" >&2; }

run() {
  if [[ "$DRY_RUN" == "1" ]]; then
    printf '[upgrade][dry-run] %s\n' "$*"
  else
    "$@"
  fi
}

run_bash() {
  if [[ "$DRY_RUN" == "1" ]]; then
    printf '[upgrade][dry-run] bash -lc %q\n' "$*"
  else
    bash -lc "$*"
  fi
}

require_cmd() {
  local cmd="$1"
  if ! command -v "$cmd" >/dev/null 2>&1; then
    err "Comando richiesto non trovato: $cmd"
    exit 1
  fi
}

compose_cmd() {
  docker compose -f "$PROJECT_DIR/docker-compose.yml" --project-directory "$PROJECT_DIR" "$@"
}

ensure_project() {
  if [[ ! -d "$PROJECT_DIR/.git" ]]; then
    err "Directory progetto non valida (repo git assente): $PROJECT_DIR"
    exit 1
  fi
  if [[ ! -f "$PROJECT_DIR/docker-compose.yml" ]]; then
    err "docker-compose.yml non trovato in $PROJECT_DIR"
    exit 1
  fi
}

ensure_clean_if_required() {
  if [[ "$ALLOW_DIRTY" == "1" ]]; then
    return
  fi
  local dirty
  dirty="$(git -C "$PROJECT_DIR" status --porcelain)"
  if [[ -n "$dirty" ]]; then
    err "Working tree non pulita. Usa --allow-dirty se vuoi continuare."
    exit 1
  fi
}

backup_pre_upgrade() {
  if [[ "$SKIP_BACKUP" == "1" ]]; then
    log "Backup pre-upgrade disattivato (--skip-backup)."
    return
  fi

  local ts backup_path sql_file
  ts="$(date +%Y%m%d-%H%M%S)"
  backup_path="$BACKUP_DIR/$ts"
  sql_file="$backup_path/db.sql"

  log "Creo backup pre-upgrade in: $backup_path"
  run mkdir -p "$backup_path"

  if [[ -f "$PROJECT_DIR/.env" ]]; then
    run cp "$PROJECT_DIR/.env" "$backup_path/.env.backup"
  else
    log "File .env non trovato, continuo senza copia env."
  fi

  if [[ "$DRY_RUN" == "1" ]]; then
    printf '[upgrade][dry-run] docker compose exec -T db pg_dump > %s\n' "$sql_file"
  else
    compose_cmd exec -T db sh -lc 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB"' > "$sql_file"
  fi
}

git_update() {
  if [[ "$SKIP_FETCH" == "0" ]]; then
    log "Fetch branch remoto: $BRANCH"
    run git -C "$PROJECT_DIR" fetch origin "$BRANCH"
  else
    log "Fetch remoto saltato (--skip-fetch)."
  fi

  log "Aggiorno branch locale con fast-forward"
  run git -C "$PROJECT_DIR" checkout "$BRANCH"
  run git -C "$PROJECT_DIR" pull --ff-only origin "$BRANCH"
}

upgrade_stack() {
  log "Build immagini aggiornate"
  run compose_cmd build web scheduler
  log "Riavvio servizi applicativi"
  run compose_cmd up -d web scheduler
}

post_checks() {
  if [[ "$SKIP_MIGRATE" == "1" ]]; then
    log "Post-check migrate/check saltato (--skip-migrate)."
    return
  fi
  log "Eseguo migrate"
  run compose_cmd exec -T web python manage.py migrate
  log "Eseguo Django check"
  run compose_cmd exec -T web python manage.py check
}

summary() {
  local commit
  commit="$(git -C "$PROJECT_DIR" rev-parse --short HEAD)"
  log "Upgrade completato. Commit corrente: $commit"
  run compose_cmd ps
}

main() {
  require_cmd git
  require_cmd docker
  ensure_project
  ensure_clean_if_required
  backup_pre_upgrade
  git_update
  upgrade_stack
  post_checks
  summary
}

main "$@"
