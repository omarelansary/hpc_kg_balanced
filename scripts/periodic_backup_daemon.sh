#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="/data/horse/ws/omel305g-omel305g-new/hpc_kg_balanced"
SYNC_SCRIPT="$ROOT_DIR/sync_backup.sh"
LOG_DIR="$ROOT_DIR/logs"
PID_FILE="$LOG_DIR/periodic_backup.pid"
LOG_FILE="$LOG_DIR/periodic_backup.log"
INTERVAL_SEC="${INTERVAL_SEC:-900}"

mkdir -p "$LOG_DIR"

is_running() {
  if [[ -f "$PID_FILE" ]]; then
    local pid
    pid="$(cat "$PID_FILE" 2>/dev/null || true)"
    [[ -n "${pid}" ]] && kill -0 "$pid" 2>/dev/null
  else
    return 1
  fi
}

run_loop() {
  echo "[$(date '+%F %T')] periodic backup started (interval=${INTERVAL_SEC}s)"
  while true; do
    echo "[$(date '+%F %T')] sync start"
    if bash "$SYNC_SCRIPT"; then
      echo "[$(date '+%F %T')] sync ok"
    else
      echo "[$(date '+%F %T')] sync failed"
    fi
    sleep "$INTERVAL_SEC"
  done
}

start_daemon() {
  if is_running; then
    echo "Periodic backup already running (pid=$(cat "$PID_FILE"))."
    exit 0
  fi

  nohup bash "$0" _run >> "$LOG_FILE" 2>&1 &
  local pid=$!
  echo "$pid" > "$PID_FILE"
  sleep 0.3
  if is_running; then
    echo "Periodic backup started (pid=$(cat "$PID_FILE"))."
    echo "Log file: $LOG_FILE"
  else
    echo "Failed to start periodic backup."
    exit 1
  fi
}

stop_daemon() {
  if ! is_running; then
    echo "Periodic backup is not running."
    rm -f "$PID_FILE"
    exit 0
  fi
  local pid
  pid="$(cat "$PID_FILE")"
  kill "$pid" 2>/dev/null || true
  sleep 0.5
  if kill -0 "$pid" 2>/dev/null; then
    kill -9 "$pid" 2>/dev/null || true
  fi
  rm -f "$PID_FILE"
  echo "Periodic backup stopped."
}

status_daemon() {
  if is_running; then
    echo "Periodic backup is running (pid=$(cat "$PID_FILE"), interval=${INTERVAL_SEC}s)."
    echo "Log file: $LOG_FILE"
  else
    echo "Periodic backup is not running."
  fi
}

usage() {
  cat <<'EOF'
Usage:
  bash scripts/periodic_backup_daemon.sh start
  bash scripts/periodic_backup_daemon.sh stop
  bash scripts/periodic_backup_daemon.sh status

Optional env var:
  INTERVAL_SEC=900   # default 15 minutes
EOF
}

cmd="${1:-}"
case "$cmd" in
  _run) run_loop ;;
  start) start_daemon ;;
  stop) stop_daemon ;;
  status) status_daemon ;;
  *) usage; exit 1 ;;
esac
