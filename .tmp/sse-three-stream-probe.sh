#!/usr/bin/env bash
# Run from one approved VPN client while the admin UI already has an active
# diagnostics stream for the same experiment.  This script opens the second
# and third streams from that same client IP, then prints sanitized evidence.
#
# It intentionally does not print the JWT, any SSE event payload, response
# bodies, request URLs with query strings, or request IDs.  Its temporary
# files are removed on exit.

set -euo pipefail

readonly BASE_URL="${OPIRAJA_BASE_URL:-https://193.40.157.124}"
readonly STREAM_DURATION_SECONDS="${SSE_STREAM_DURATION_SECONDS:-60}"
readonly HEADER_WAIT_SECONDS=10

if ! command -v curl >/dev/null 2>&1; then
  printf 'ERROR: curl is required but was not found.\n' >&2
  exit 1
fi

if ! [[ "$STREAM_DURATION_SECONDS" =~ ^[1-9][0-9]*$ ]]; then
  printf 'ERROR: SSE_STREAM_DURATION_SECONDS must be a positive integer.\n' >&2
  exit 1
fi

read -r -s -p 'Admin JWT (input hidden): ' admin_jwt
printf '\n'
if [[ -z "$admin_jwt" ]]; then
  printf 'ERROR: an admin JWT is required.\n' >&2
  exit 1
fi
if ! [[ "$admin_jwt" =~ ^[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$ ]]; then
  printf 'ERROR: expected an unquoted three-part JWT.\n' >&2
  exit 1
fi

read -r -p 'Experiment UUID shown by the admin UI (not the assessment/test ID): ' experiment_id
if ! [[ "$experiment_id" =~ ^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$ ]]; then
  printf 'ERROR: expected a UUID experiment identifier.\n' >&2
  exit 1
fi

cat <<'INSTRUCTIONS'

Preparation:
  1. In the admin UI, start the selected simulation and keep its live
     diagnostics panel open. That browser connection is stream 1.
  2. Start/advance the simulation while this script is running so the UI and
     the accepted curl stream receive diagnostic events.

This script will now open curl streams 2 and 3 from this same VPN client.
Expected with enforcement enabled: stream 2 is HTTP 200; stream 3 is HTTP 429.
INSTRUCTIONS
read -r -p 'Press Enter only after the browser diagnostics stream is active... '

umask 077
work_dir="$(mktemp -d "${TMPDIR:-/tmp}/opiraja-sse-probe.XXXXXX")"
stream_one_pid=''
stream_two_pid=''

cleanup() {
  [[ -n "$stream_one_pid" ]] && kill "$stream_one_pid" 2>/dev/null || true
  [[ -n "$stream_two_pid" ]] && kill "$stream_two_pid" 2>/dev/null || true
  rm -f -- "$work_dir"/*
  rmdir -- "$work_dir" 2>/dev/null || true
}
trap cleanup EXIT HUP INT TERM

# Put the bearer token in a mode-0600 curl configuration file rather than in
# curl's command line, where local process inspection could reveal it.
curl_config="$work_dir/curl.conf"
printf '%s\n' \
  "insecure" \
  "http1.1" \
  "no-buffer" \
  'header = "Accept: text/event-stream"' \
  "header = \"Authorization: Bearer ${admin_jwt}\"" \
  >"$curl_config"
unset admin_jwt

endpoint_path="/api/v1/admin/experiments/${experiment_id}/events"
endpoint_url="${BASE_URL%/}${endpoint_path}?after=0"

run_stream() {
  local label="$1"
  curl --disable --config "$curl_config" \
    --max-time "$STREAM_DURATION_SECONDS" \
    --dump-header "$work_dir/${label}.headers" \
    --output "$work_dir/${label}.body" \
    --write-out '%{http_code}\n' \
    "$endpoint_url" >"$work_dir/${label}.status" 2>"$work_dir/${label}.stderr"
}

sse_frame_count() {
  local body_file="$work_dir/$1.body"
  if [[ ! -f "$body_file" ]]; then
    printf '0\n'
    return
  fi
  grep -c '^data: ' "$body_file" 2>/dev/null || true
}

wait_for_response_headers() {
  local header_file="$1"
  local elapsed=0
  while (( elapsed < HEADER_WAIT_SECONDS )); do
    if [[ -s "$header_file" ]] && grep -q '^HTTP/' "$header_file"; then
      return 0
    fi
    sleep 1
    ((elapsed += 1))
  done
  return 1
}

utc_started="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
printf '\nProbe started at %s UTC. Opening curl stream 2...\n' "$utc_started"
run_stream stream_2 &
stream_one_pid=$!

if ! wait_for_response_headers "$work_dir/stream_2.headers"; then
  printf 'WARNING: stream 2 did not produce response headers within %ss. Continuing.\n' "$HEADER_WAIT_SECONDS" >&2
fi

printf 'Opening curl stream 3...\n'
run_stream stream_3 &
stream_two_pid=$!

if ! wait_for_response_headers "$work_dir/stream_3.headers"; then
  printf 'WARNING: stream 3 did not produce response headers within %ss. Continuing.\n' "$HEADER_WAIT_SECONDS" >&2
fi

stream_2_frames_before_action="$(sse_frame_count stream_2)"
printf '\nBoth curl streams have now been attempted. In the browser, advance the simulation at least once and confirm that its diagnostics terminal receives a new event.\n'
read -r -p 'After that browser event appears, press Enter here... '
sleep 3
stream_2_frames_after_action="$(sse_frame_count stream_2)"
browser_stream_incremental=no
read -r -p 'Did the browser diagnostics terminal receive a new event during the overlap? [y/N]: ' browser_answer
if [[ "$browser_answer" =~ ^[Yy]([Ee][Ss])?$ ]]; then
  browser_stream_incremental=yes
fi

set +e
wait "$stream_one_pid"
stream_2_exit=$?
wait "$stream_two_pid"
stream_3_exit=$?
set -e
stream_one_pid=''
stream_two_pid=''
utc_finished="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

http_status() {
  tr -d '\r\n' <"$work_dir/$1.status" 2>/dev/null || true
}

header_count() {
  awk -v wanted="$2" 'BEGIN { IGNORECASE = 1 } $0 ~ "^" wanted ":" { count++ } END { print count + 0 }' "$work_dir/$1.headers" 2>/dev/null
}

body_matches_rate_limited() {
  [[ "$(tr -d '\r\n[:space:]' <"$work_dir/$1.body" 2>/dev/null)" == '{"code":"rate_limited"}' ]]
}

stream_2_status="$(http_status stream_2)"
stream_3_status="$(http_status stream_3)"
stream_2_frames="$(sse_frame_count stream_2)"
stream_3_frames="$(sse_frame_count stream_3)"
stream_3_rate_limited=no
if body_matches_rate_limited stream_3; then
  stream_3_rate_limited=yes
fi

result=PASS
if [[ "$browser_stream_incremental" != yes || "$stream_2_status" != 200 || "$stream_2_frames" -le "$stream_2_frames_before_action" || "$stream_3_status" != 429 || "$stream_3_rate_limited" != yes || "$(header_count stream_3 X-Request-ID)" != 1 ]]; then
  result=FAIL
fi

cat <<RESULT

=== Sanitized three-SSE-stream enforcement evidence ===
result: ${result}
window_utc: ${utc_started} to ${utc_finished}
endpoint_path: ${endpoint_path}
browser_stream_1_incremental: ${browser_stream_incremental}
curl_stream_2: http_status=${stream_2_status:-none}; curl_exit=${stream_2_exit}; sse_data_frames_before_action=${stream_2_frames_before_action}; sse_data_frames_after_action=${stream_2_frames_after_action}; sse_data_frames_final=${stream_2_frames}
curl_stream_3: http_status=${stream_3_status:-none}; curl_exit=${stream_3_exit}; sse_data_frames=${stream_3_frames}; rate_limited_envelope=${stream_3_rate_limited}; x_request_id_headers=$(header_count stream_3 X-Request-ID)
expected: browser_stream_1_incremental=yes; curl_stream_2 HTTP 200 with data frames increasing after the UI action; curl_stream_3 HTTP 429 with rate_limited_envelope=yes and exactly one X-Request-ID header
host_log_follow_up: during this UTC window, record sanitized counts for HTTP 429, limit_conn_status=PASSED, limit_conn_status=REJECTED, matching connection-limit warnings, and unexpected error-level entries.
=== End sanitized evidence ===
RESULT

if [[ "$result" != PASS ]]; then
  exit 1
fi
