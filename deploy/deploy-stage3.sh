#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="${COMPOSE_FILE:-$SCRIPT_DIR/docker-compose.yml}"
ENV_FILE="${ENV_FILE:-$SCRIPT_DIR/.env}"
DEFAULT_WORKERS=2
DEFAULT_TIMEOUT_SECONDS=1200

COMMAND="${1:-help}"
if [ "$#" -gt 0 ]; then
  shift
fi

WORKERS="$DEFAULT_WORKERS"
TIMEOUT_SECONDS="$DEFAULT_TIMEOUT_SECONDS"
DRY_RUN=false
AGENT_PAUSED_BY_SCRIPT=false
LOCK_DIRECTORY_ACQUIRED=false

usage() {
  cat <<'EOF'
Usage:
  ./deploy-stage3.sh status
  ./deploy-stage3.sh preflight
  ./deploy-stage3.sh upgrade [--workers N] [--timeout SECONDS] [--dry-run]
  ./deploy-stage3.sh scale --workers N [--timeout SECONDS] [--dry-run]

Safety:
  upgrade updates Backend first, waits for a zero Agent queue, temporarily
  disables Agent, replaces Worker replicas, updates Frontend, and restores the
  original Agent enabled state only after the target capacity is healthy.
  Successful upgrade and scale operations then remove only stopped containers
  labeled with the current Compose project; running containers and volumes are
  never removed.
EOF
}

fail() {
  echo "ERROR: $*" >&2
  exit 1
}

warn() {
  echo "WARNING: $*" >&2
}

is_positive_integer() {
  [[ "$1" =~ ^[0-9]+$ ]] && [ "$1" -gt 0 ]
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --workers)
      [ "$#" -ge 2 ] || fail "--workers requires an integer"
      WORKERS="$2"
      shift 2
      ;;
    --timeout)
      [ "$#" -ge 2 ] || fail "--timeout requires seconds"
      TIMEOUT_SECONDS="$2"
      shift 2
      ;;
    --dry-run)
      DRY_RUN=true
      shift
      ;;
    -h|--help)
      COMMAND=help
      shift
      ;;
    *)
      fail "Unknown argument: $1"
      ;;
  esac
done

case "$COMMAND" in
  help)
    usage
    exit 0
    ;;
  status|preflight|upgrade|scale)
    ;;
  *)
    usage >&2
    fail "Unknown command: $COMMAND"
    ;;
esac

is_positive_integer "$WORKERS" || fail "--workers must be an integer between 1 and 100"
[ "$WORKERS" -le 100 ] || fail "--workers must be an integer between 1 and 100"
is_positive_integer "$TIMEOUT_SECONDS" || fail "--timeout must be an integer between 60 and 3600"
[ "$TIMEOUT_SECONDS" -ge 60 ] && [ "$TIMEOUT_SECONDS" -le 3600 ] \
  || fail "--timeout must be an integer between 60 and 3600"

[ -f "$COMPOSE_FILE" ] || fail "Compose file not found: $COMPOSE_FILE"
[ -f "$ENV_FILE" ] || fail "Environment file not found: $ENV_FILE"
command -v docker >/dev/null 2>&1 || fail "docker command was not found"

compose() {
  docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" "$@"
}

compose config --quiet

cleanup_stopped_project_containers() {
  local backend_id
  local project_name
  local state
  local ids
  local container_id
  local container_name
  local -a stopped_ids=()

  if ! backend_id="$(compose ps -q backend 2>/dev/null)"; then
    warn "Could not resolve the current Compose project; stopped container cleanup was skipped."
    return 0
  fi
  backend_id="${backend_id%%$'\n'*}"
  if [ -z "$backend_id" ]; then
    warn "No running Backend container was found; stopped container cleanup was skipped."
    return 0
  fi

  if ! project_name="$(
    docker inspect \
      --format '{{ index .Config.Labels "com.docker.compose.project" }}' \
      "$backend_id" 2>/dev/null
  )"; then
    warn "Could not read the current Compose project label; stopped container cleanup was skipped."
    return 0
  fi
  if ! [[ "$project_name" =~ ^[a-zA-Z0-9][a-zA-Z0-9_.-]*$ ]]; then
    warn "The current Compose project label is invalid; stopped container cleanup was skipped."
    return 0
  fi

  for state in created exited dead; do
    if ! ids="$(
      docker ps -aq \
        --filter "label=com.docker.compose.project=$project_name" \
        --filter "status=$state"
    )"; then
      warn "Could not list stopped containers for Compose project '$project_name'; cleanup was skipped."
      return 0
    fi
    while IFS= read -r container_id; do
      if [ -n "$container_id" ]; then
        stopped_ids+=("$container_id")
      fi
    done <<<"$ids"
  done

  if [ "${#stopped_ids[@]}" -eq 0 ]; then
    echo "No stopped containers to remove for Compose project '$project_name'."
    return 0
  fi

  echo "Removing stopped containers for Compose project '$project_name'..."
  for container_id in "${stopped_ids[@]}"; do
    container_name="$(
      docker inspect --format '{{.Name}}' "$container_id" 2>/dev/null \
        || printf '%s' "$container_id"
    )"
    container_name="${container_name#/}"
    if docker rm "$container_id" >/dev/null 2>&1; then
      echo "Removed stopped container: $container_name"
    else
      warn "Skipped container '$container_name'; it may have restarted or changed state."
    fi
  done
}

acquire_change_lock() {
  if command -v flock >/dev/null 2>&1; then
    exec 9>"$SCRIPT_DIR/.deploy-stage3.lock"
    flock -n 9 || fail "Another Stage 3 deployment change is already running"
    return
  fi

  local lock_directory="$SCRIPT_DIR/.deploy-stage3.lock.d"
  mkdir "$lock_directory" 2>/dev/null \
    || fail "Another Stage 3 deployment change is already running"
  LOCK_DIRECTORY_ACQUIRED=true
}

on_exit() {
  local exit_code="$1"
  if [ "$LOCK_DIRECTORY_ACQUIRED" = true ]; then
    rmdir "$SCRIPT_DIR/.deploy-stage3.lock.d" 2>/dev/null || true
  fi
  if [ "$exit_code" -ne 0 ] && [ "$AGENT_PAUSED_BY_SCRIPT" = true ]; then
    echo "Agent remains disabled because deployment did not reach healthy target capacity." >&2
    echo "Fix the failed step, run './deploy-stage3.sh status', then restore Agent from the settings page." >&2
  fi
}
trap 'on_exit $?' EXIT

agent_snapshot() {
  compose exec -T backend python -c '
import json
import os
import urllib.request

port = os.environ.get("SERVER_PORT", "8090")
url = f"http://127.0.0.1:{port}/api/code-quality-reviews/agent-settings"
with urllib.request.urlopen(url, timeout=5) as response:
    envelope = json.loads(response.read().decode("utf-8"))
data = envelope.get("data") if isinstance(envelope, dict) else None
if not isinstance(data, dict):
    raise SystemExit(2)
queue = data.get("queueMetrics")
pool = data.get("workerPool")
metrics_ready = isinstance(queue, dict)
if not isinstance(queue, dict):
    queue = {}
if not isinstance(pool, dict):
    pool = {}

def number(value):
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0

values = [
    "true" if metrics_ready else "false",
    "true" if data.get("enabled") is True else "false",
    str(number(queue.get("queued"))),
    str(number(queue.get("running"))),
    str(number(queue.get("expiredLease"))),
    str(number(queue.get("oldestQueuedSeconds"))),
    str(number(queue.get("onlineCapacity"))),
    str(number(queue.get("busyCapacity"))),
    str(number(queue.get("utilizationPercent"))),
    str(number(queue.get("drainingWorkers"))),
    str(data.get("workerStatus") or pool.get("status") or "OFFLINE"),
]
print("|".join(values))
'
}

parse_snapshot() {
  local snapshot="$1"
  IFS='|' read -r \
    METRICS_READY \
    AGENT_ENABLED \
    QUEUED \
    RUNNING \
    EXPIRED_LEASE \
    OLDEST_QUEUED_SECONDS \
    ONLINE_CAPACITY \
    BUSY_CAPACITY \
    UTILIZATION_PERCENT \
    DRAINING_WORKERS \
    WORKER_STATUS <<<"$snapshot"

  [[ "$METRICS_READY" =~ ^(true|false)$ ]] || return 1
  [[ "$AGENT_ENABLED" =~ ^(true|false)$ ]] || return 1
  for value in \
    "$QUEUED" \
    "$RUNNING" \
    "$EXPIRED_LEASE" \
    "$OLDEST_QUEUED_SECONDS" \
    "$ONLINE_CAPACITY" \
    "$BUSY_CAPACITY" \
    "$UTILIZATION_PERCENT" \
    "$DRAINING_WORKERS"; do
    [[ "$value" =~ ^[0-9]+$ ]] || return 1
  done
  [[ "$WORKER_STATUS" =~ ^(ONLINE|OFFLINE)$ ]] || return 1
}

load_snapshot() {
  local snapshot
  snapshot="$(agent_snapshot)" || return 1
  parse_snapshot "$snapshot"
}

print_snapshot() {
  echo "Agent metricsReady=$METRICS_READY; enabled=$AGENT_ENABLED; workerStatus=$WORKER_STATUS; queued=$QUEUED; running=$RUNNING; expiredLease=$EXPIRED_LEASE; oldestQueuedSeconds=$OLDEST_QUEUED_SECONDS; onlineCapacity=$ONLINE_CAPACITY; busyCapacity=$BUSY_CAPACITY; utilizationPercent=$UTILIZATION_PERCENT; drainingWorkers=$DRAINING_WORKERS"
}

set_agent_enabled() {
  local desired="$1"
  compose exec -T backend python -c '
import json
import os
import sys
import urllib.request

desired = sys.argv[1] == "true"
port = os.environ.get("SERVER_PORT", "8090")
url = f"http://127.0.0.1:{port}/api/code-quality-reviews/agent-settings"
request = urllib.request.Request(
    url,
    data=json.dumps({"enabled": desired}).encode("utf-8"),
    headers={"Content-Type": "application/json"},
    method="PUT",
)
with urllib.request.urlopen(request, timeout=10) as response:
    envelope = json.loads(response.read().decode("utf-8"))
data = envelope.get("data") if isinstance(envelope, dict) else None
if not isinstance(data, dict) or (data.get("enabled") is True) != desired:
    raise SystemExit(2)
' "$desired"
}

wait_for_backend_metrics() {
  local deadline=$((SECONDS + TIMEOUT_SECONDS))
  echo "Waiting for Backend Agent Settings and Stage 3 metrics..."
  while [ "$SECONDS" -lt "$deadline" ]; do
    if load_snapshot 2>/dev/null && [ "$METRICS_READY" = true ]; then
      print_snapshot
      return 0
    fi
    sleep 3
  done
  fail "Backend did not expose Stage 3 queue metrics within ${TIMEOUT_SECONDS}s"
}

pause_agent_at_zero_queue() {
  local original_enabled="$1"
  local deadline=$((SECONDS + TIMEOUT_SECONDS))

  if [ "$original_enabled" = false ]; then
    load_snapshot || fail "Could not read Agent queue metrics"
    print_snapshot
    [ "$QUEUED" -eq 0 ] && [ "$RUNNING" -eq 0 ] && [ "$EXPIRED_LEASE" -eq 0 ] \
      || fail "Agent is already disabled but active jobs remain; recover them before upgrading"
    return
  fi

  echo "Waiting for a zero Agent queue before sealing new Agent admissions..."
  while [ "$SECONDS" -lt "$deadline" ]; do
    if load_snapshot; then
      print_snapshot
      if [ "$QUEUED" -eq 0 ] && [ "$RUNNING" -eq 0 ] && [ "$EXPIRED_LEASE" -eq 0 ]; then
        set_agent_enabled false
        AGENT_PAUSED_BY_SCRIPT=true
        sleep 1
        load_snapshot || fail "Could not verify Agent pause"
        if [ "$AGENT_ENABLED" = false ] \
          && [ "$QUEUED" -eq 0 ] \
          && [ "$RUNNING" -eq 0 ] \
          && [ "$EXPIRED_LEASE" -eq 0 ]; then
          echo "Agent admissions paused at a zero queue."
          return
        fi

        echo "A task entered during the pause boundary; restoring Agent and retrying."
        set_agent_enabled true
        AGENT_PAUSED_BY_SCRIPT=false
      fi
    fi
    sleep 3
  done
  fail "Agent queue did not reach a stable zero state within ${TIMEOUT_SECONDS}s"
}

wait_for_worker_capacity() {
  local target="$1"
  local deadline=$((SECONDS + TIMEOUT_SECONDS))
  echo "Waiting for onlineCapacity >= $target and drainingWorkers=0..."
  while [ "$SECONDS" -lt "$deadline" ]; do
    if load_snapshot; then
      print_snapshot
      if [ "$METRICS_READY" = true ] \
        && [ "$ONLINE_CAPACITY" -ge "$target" ] \
        && [ "$DRAINING_WORKERS" -eq 0 ] \
        && [ "$WORKER_STATUS" = "ONLINE" ]; then
        return 0
      fi
    fi
    sleep 3
  done
  fail "Worker Pool did not reach target capacity $target within ${TIMEOUT_SECONDS}s"
}

show_dry_run_upgrade() {
  echo "DRY RUN: docker compose up -d --no-deps backend"
  echo "DRY RUN: wait for Stage 3 metrics and a zero Agent queue"
  echo "DRY RUN: preserve enabled state and PUT only enabled=false when needed"
  echo "DRY RUN: docker compose up -d agent-egress-proxy"
  echo "DRY RUN: docker compose up -d --no-deps --scale agent-worker=$WORKERS agent-worker"
  echo "DRY RUN: wait for onlineCapacity >= $WORKERS and drainingWorkers=0"
  echo "DRY RUN: docker compose up -d --no-deps frontend"
  echo "DRY RUN: restore the original enabled state only after healthy capacity"
  echo "DRY RUN: remove only created/exited/dead containers from the current Compose project"
}

case "$COMMAND" in
  status)
    load_snapshot || fail "Backend Agent Settings are unavailable or malformed"
    print_snapshot
    ;;
  preflight)
    load_snapshot || fail "Backend Agent Settings are unavailable or malformed"
    print_snapshot
    [ "$METRICS_READY" = true ] || fail "Backend does not expose Stage 3 queue metrics"
    [ "$QUEUED" -eq 0 ] && [ "$RUNNING" -eq 0 ] && [ "$EXPIRED_LEASE" -eq 0 ] \
      || fail "Agent queue is not ready for deployment"
    [ "$ONLINE_CAPACITY" -gt 0 ] || fail "No accepting Agent Worker capacity is online"
    ;;
  upgrade)
    if [ "$DRY_RUN" = true ]; then
      show_dry_run_upgrade
      exit 0
    fi
    acquire_change_lock
    compose up -d --no-deps backend
    wait_for_backend_metrics
    ORIGINAL_AGENT_ENABLED="$AGENT_ENABLED"
    pause_agent_at_zero_queue "$ORIGINAL_AGENT_ENABLED"

    compose up -d agent-egress-proxy
    compose up -d --no-deps --scale "agent-worker=$WORKERS" agent-worker
    wait_for_worker_capacity "$WORKERS"
    compose up -d --no-deps frontend

    if [ "$ORIGINAL_AGENT_ENABLED" = true ]; then
      set_agent_enabled true
      AGENT_PAUSED_BY_SCRIPT=false
      load_snapshot || fail "Could not verify restored Agent settings"
      [ "$AGENT_ENABLED" = true ] || fail "Agent enabled state was not restored"
    fi
    load_snapshot || fail "Could not read final Agent status"
    print_snapshot
    cleanup_stopped_project_containers
    echo "Stage 3 deployment completed."
    ;;
  scale)
    if [ "$DRY_RUN" = true ]; then
      echo "DRY RUN: docker compose up -d --no-deps --scale agent-worker=$WORKERS agent-worker"
      echo "DRY RUN: wait for onlineCapacity >= $WORKERS and drainingWorkers=0"
      echo "DRY RUN: remove only created/exited/dead containers from the current Compose project"
      exit 0
    fi
    acquire_change_lock
    compose up -d --no-deps --scale "agent-worker=$WORKERS" agent-worker
    wait_for_worker_capacity "$WORKERS"
    load_snapshot || fail "Could not read final Agent status"
    print_snapshot
    cleanup_stopped_project_containers
    echo "Worker scale operation completed."
    ;;
esac
