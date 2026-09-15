#!/usr/bin/env bash
#
# One-command local startup for LangAlpha.
#
#   ./startup.sh            start middleware (if needed) + backend + frontend + channel worker
#   ./startup.sh stop       stop the three app processes (middleware keeps running)
#   ./startup.sh stop --docker   also stop the middleware stack
#   ./startup.sh status     show what is up
#
# Started processes are detached (their own session) so the script can exit and
# they keep running; their pids and logs live in $LANGALPHA_LOG_DIR.
#
# Ports and targets come from the repository's own config:
#   deploy/.env                            middleware ports (5432 / 6379 / 9000)
#   .env                                   backend ports and credentials
#   web/vite.config.js                     proxies /api to http://localhost:8000 by default
#
# The WeChat worker talks to the GinlixFlow bridge, which this script does not
# start: point GINLIXFLOW_BASE_URL at it if it lives elsewhere.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_ROOT"

COMPOSE_FILE="deploy/docker-compose-middleware.yml"
COMPOSE_ENV_FILE="deploy/.env"

BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-5177}"
PG_PORT="${PG_PORT:-5432}"
REDIS_PORT="${REDIS_PORT:-6379}"
MINIO_PORT="${MINIO_PORT:-9000}"
GINLIXFLOW_BASE_URL="${GINLIXFLOW_BASE_URL:-http://127.0.0.1:8010}"

# TMPDIR carries a trailing slash on macOS; normalise before joining.
_scratch="${TMPDIR:-/tmp}"; _scratch="${_scratch%/}"
LOG_DIR="${LANGALPHA_LOG_DIR:-$_scratch/langalpha}"
mkdir -p "$LOG_DIR"

PYTHON="$REPO_ROOT/.venv/bin/python"
NODE="${NODE:-node}"

say() { printf '%s\n' "$*"; }
die() { printf 'error: %s\n' "$*" >&2; exit 1; }

port_busy() { lsof -nP -iTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1; }

last_pid() {
  local pid_file="$LOG_DIR/$1.pid"
  [ -f "$pid_file" ] || return 1
  local pid; pid="$(cat "$pid_file")"
  [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null
}

# Detach through setsid() so the process outlives this shell and any terminal
# that started it; the pid is what `stop` will signal later.
start_detached() {
  local name="$1"; shift
  nohup "$PYTHON" -c 'import os,sys; os.setsid(); os.execvp(sys.argv[1], sys.argv[1:])' \
    "$@" >>"$LOG_DIR/$name.log" 2>&1 &
  echo $! >"$LOG_DIR/$name.pid"
}

wait_for_port() {
  local port="$1" seconds="$2" waited=0
  until port_busy "$port"; do
    waited=$((waited + 1))
    [ "$waited" -ge "$seconds" ] && return 1
    sleep 1
  done
}

wait_for_http() {
  local url="$1" seconds="$2" waited=0 code
  until code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 3 "$url" 2>/dev/null)" \
        && [ "$code" != "000" ]; do
    waited=$((waited + 1))
    [ "$waited" -ge "$seconds" ] && return 1
    sleep 1
  done
}

middleware_running() {
  docker ps --format '{{.Names}}' 2>/dev/null | grep -qx 'deploy-postgres-1' \
    && docker ps --format '{{.Names}}' 2>/dev/null | grep -qx 'deploy-minio-1' \
    && docker ps --format '{{.Names}}' 2>/dev/null | grep -qx 'deploy-redis-1'
}

start_middleware() {
  [ -f "$COMPOSE_ENV_FILE" ] || die "$COMPOSE_ENV_FILE is missing (copy deploy/.env.example and fill it in)"
  if middleware_running; then
    say "middleware: already running (deploy-{postgres,redis,minio}-1)"
    return
  fi
  say "middleware: starting via $COMPOSE_FILE"
  docker compose --env-file "$COMPOSE_ENV_FILE" -f "$COMPOSE_FILE" up -d
  wait_for_port "$PG_PORT" 60 || die "postgres did not come up on $PG_PORT"
  wait_for_port "$REDIS_PORT" 60 || die "redis did not come up on $REDIS_PORT"
  wait_for_port "$MINIO_PORT" 60 || die "minio did not come up on $MINIO_PORT"
  say "middleware: postgres $PG_PORT, redis $REDIS_PORT, minio $MINIO_PORT"
}

start_backend() {
  if port_busy "$BACKEND_PORT"; then
    say "backend:  port $BACKEND_PORT already in use — leaving it alone"
    return
  fi
  say "backend:  starting on $BACKEND_PORT (log: $LOG_DIR/backend.log)"
  start_detached backend "$PYTHON" server.py --host 0.0.0.0 --port "$BACKEND_PORT"
  wait_for_http "http://127.0.0.1:$BACKEND_PORT/api/v1/auth/me" 90 \
    || die "backend did not answer on $BACKEND_PORT; see $LOG_DIR/backend.log"
}

start_frontend() {
  if port_busy "$FRONTEND_PORT"; then
    say "frontend: port $FRONTEND_PORT already in use — leaving it alone"
    return
  fi
  [ -d "$REPO_ROOT/web/node_modules" ] || die "web/node_modules is missing — run: cd web && pnpm install"
  say "frontend: starting on $FRONTEND_PORT (log: $LOG_DIR/frontend.log)"
  # Started from inside web/: vite resolves its root (and the proxy in
  # vite.config.js) from the working directory, and Tailwind resolves its
  # config the same way — running from the repo root made Tailwind fall back to
  # its default theme and every `@apply border-border` failed to compile.
  (
    cd "$REPO_ROOT/web" &&
      start_detached frontend "$NODE" "$REPO_ROOT/web/node_modules/vite/bin/vite.js" \
        --host 0.0.0.0 --port "$FRONTEND_PORT"
  )
  wait_for_http "http://127.0.0.1:$FRONTEND_PORT/" 60 \
    || die "frontend did not answer on $FRONTEND_PORT; see $LOG_DIR/frontend.log"
}

start_worker() {
  if last_pid worker; then
    say "worker:   already running (pid $(cat "$LOG_DIR/worker.pid"))"
    return
  fi
  say "worker:   starting channel worker (log: $LOG_DIR/worker.log)"
  GINLIXFLOW_BASE_URL="$GINLIXFLOW_BASE_URL" \
    start_detached worker "$PYTHON" -m src.server.services.channels.worker
  sleep 3
  last_pid worker || die "channel worker exited; see $LOG_DIR/worker.log"
}

stop_apps() {
  local name pid
  for name in worker frontend backend; do
    if last_pid "$name"; then
      pid="$(cat "$LOG_DIR/$name.pid")"
      kill "$pid" 2>/dev/null || true
      say "stopped $name (pid $pid)"
    else
      say "$name: not running"
    fi
    rm -f "$LOG_DIR/$name.pid"
  done
}

status() {
  printf '%-10s %-8s %s\n' "component" "port" "state"
  for spec in "backend:$BACKEND_PORT" "frontend:$FRONTEND_PORT" "postgres:$PG_PORT" "redis:$REDIS_PORT" "minio:$MINIO_PORT"; do
    name="${spec%%:*}"; port="${spec##*:}"
    if port_busy "$port"; then state="listening"; else state="down"; fi
    printf '%-10s %-8s %s\n' "$name" "$port" "$state"
  done
  if last_pid worker; then
    printf '%-10s %-8s %s\n' "worker" "-" "running (pid $(cat "$LOG_DIR/worker.pid"))"
  else
    printf '%-10s %-8s %s\n' "worker" "-" "down"
  fi
}

main() {
  [ -x "$PYTHON" ] || die "$PYTHON is missing — run: uv sync"

  case "${1:-start}" in
    start)
      start_middleware
      start_backend
      start_frontend
      start_worker
      say ""
      say "ready:"
      say "  app      http://localhost:$FRONTEND_PORT"
      say "  api      http://localhost:$BACKEND_PORT"
      say "  minio    http://localhost:9001 (console)"
      say "  logs     $LOG_DIR"
      say "  worker   ginlixflow bridge expected at $GINLIXFLOW_BASE_URL"
      ;;
    stop)
      stop_apps
      if [ "${2:-}" = "--docker" ]; then
        docker compose --env-file "$COMPOSE_ENV_FILE" -f "$COMPOSE_FILE" stop
        say "middleware stopped"
      fi
      ;;
    status)
      status
      ;;
    *)
      die "usage: $0 [start|stop [--docker]|status]"
      ;;
  esac
}

main "$@"
