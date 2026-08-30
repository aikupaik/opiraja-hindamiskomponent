#!/usr/bin/env sh
# Capture VM evidence for one performance run. Run from the deployed repo root
# before starting k6; stop with Ctrl-C after k6 has finished.

set -eu

if [ "$#" -lt 1 ] || [ "$#" -gt 2 ]; then
  echo "usage: bash performance/bin/monitor-vm.sh <run-id> [root|api-only]" >&2
  exit 64
fi

RUN_ID=$1
MONITOR_MODE=${2:-root}
case "$RUN_ID" in
  *[!A-Za-z0-9._-]* | "")
    echo "run ID may contain only letters, digits, dot, underscore, and hyphen" >&2
    exit 64
    ;;
esac
case "$MONITOR_MODE" in
  root | api-only) ;;
  *)
    echo "monitor mode must be root or api-only" >&2
    exit 64
    ;;
esac

run_compose() {
  if [ "$MONITOR_MODE" = "api-only" ]; then
    PERF_RUN_ID=$RUN_ID docker compose \
      -f compose.yaml -f performance/compose.loopback.yaml \
      --profile api-only "$@"
  else
    docker compose "$@"
  fi
}

REPOSITORY_ROOT=$(git rev-parse --show-toplevel)
cd "$REPOSITORY_ROOT"
EVIDENCE_DIR="performance/results/$RUN_ID/vm"
mkdir -p "$EVIDENCE_DIR"

sudo -v

run_compose ps > "$EVIDENCE_DIR/compose-ps-before.txt"

run_compose logs --tail 0 --follow --timestamps --no-color \
  > "$EVIDENCE_DIR/compose-live.log" 2>&1 &
COMPOSE_LOG_PID=$!

docker events --filter type=container \
  --format '{{.TimeNano}} action={{.Action}} container={{.Actor.Attributes.name}} exit_code={{.Actor.Attributes.exitCode}}' \
  > "$EVIDENCE_DIR/docker-events.log" 2>&1 &
DOCKER_EVENTS_PID=$!

sudo tail -n 0 -F /var/log/nginx/opiraja_access.log /var/log/nginx/opiraja_error.log \
  > "$EVIDENCE_DIR/host-nginx-live.log" 2>&1 &
NGINX_LOG_PID=$!

stop_process() {
  kill "$1" 2>/dev/null || true
  wait "$1" 2>/dev/null || true
}

cleanup() {
  exit_status=$?
  trap - EXIT INT TERM HUP
  stop_process "$COMPOSE_LOG_PID"
  stop_process "$DOCKER_EVENTS_PID"
  stop_process "$NGINX_LOG_PID"
  run_compose ps > "$EVIDENCE_DIR/compose-ps-after.txt" 2>&1 || true
  printf 'stopped_utc=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    >> "$EVIDENCE_DIR/monitor-metadata.txt"
  exit "$exit_status"
}

trap cleanup EXIT INT TERM HUP

{
  printf 'run_id=%s\n' "$RUN_ID"
  printf 'started_utc=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  printf 'sample_interval_seconds=5\n'
  printf 'monitor_mode=%s\n' "$MONITOR_MODE"
  printf 'host_nginx_logs=/var/log/nginx/opiraja_access.log,/var/log/nginx/opiraja_error.log\n'
} > "$EVIDENCE_DIR/monitor-metadata.txt"

echo "Monitoring $RUN_ID. Start k6 now; press Ctrl-C here only after it finishes."

while :; do
  {
    printf '%s\n' "--- sample_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ) ---"
    uptime
    free -w
    df -P / /var/log /var/lib/docker
    if command -v mpstat >/dev/null 2>&1; then
      mpstat 1 1
    else
      head -n 1 /proc/stat
    fi
    cat /proc/net/dev
    cat /proc/diskstats
    docker stats --no-stream \
      --format 'container={{.Name}} cpu={{.CPUPerc}} memory={{.MemUsage}} memory_pct={{.MemPerc}} net={{.NetIO}} block_io={{.BlockIO}} pids={{.PIDs}}'
    for container_id in $(run_compose ps -q); do
      docker inspect --format \
        '{{.Name}} restart_count={{.RestartCount}} oom_killed={{.State.OOMKilled}} status={{.State.Status}}' \
        "$container_id"
    done
  } >> "$EVIDENCE_DIR/host-samples.log" 2>&1
  sleep 5
done
