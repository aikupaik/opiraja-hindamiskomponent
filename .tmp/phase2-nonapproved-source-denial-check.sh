#!/usr/bin/env bash
# Run only from an independent non-approved network, with every VPN disabled.
# This script makes no configuration changes and sends no credentials or data.
# It records only curl exit codes and HTTP-status presence, never response bodies.

set -euo pipefail

readonly TARGET_HOST="${OPIRAJA_TARGET_HOST:-193.40.157.124}"
readonly CONNECT_TIMEOUT_SECONDS=5
readonly TOTAL_TIMEOUT_SECONDS=7

if ! command -v curl >/dev/null 2>&1; then
  printf 'ERROR: curl is required but was not found.\n' >&2
  exit 1
fi

cat <<'SAFETY'

Run this only after disconnecting the VPN and confirming that this network is
not in either approved CIDR. Do not change OpenStack, UFW, or host settings to
make a connection succeed. A timeout, refusal, or reset with no HTTP response
is a pass; any HTTP response is a failure for this denial test.
SAFETY
read -r -p 'VPN is disconnected and this is an independent non-approved source? [y/N]: ' source_answer
if ! [[ "$source_answer" =~ ^[Yy]([Ee][Ss])?$ ]]; then
  printf 'ABORTED: non-approved-source status was not confirmed.\n' >&2
  exit 2
fi

probe_port() {
  local port="$1"
  local scheme="$2"
  local status
  local exit_code
  local -a curl_args=(
    curl --disable --silent --show-error --output /dev/null
    --write-out '%{http_code}'
    --connect-timeout "$CONNECT_TIMEOUT_SECONDS"
    --max-time "$TOTAL_TIMEOUT_SECONDS"
  )
  if [[ "$scheme" == https ]]; then
    curl_args+=(--insecure)
  fi
  set +e
  status="$("${curl_args[@]}" "${scheme}://${TARGET_HOST}:${port}/" 2>/dev/null)"
  exit_code=$?
  set -e
  status="${status:-000}"
  if [[ "$status" == 000 ]]; then
    printf 'port_%s: curl_exit=%s; http_status=none; denied=yes\n' "$port" "$exit_code"
    return 0
  fi
  printf 'port_%s: curl_exit=%s; http_status=%s; denied=no\n' "$port" "$exit_code" "$status"
  return 1
}

utc_started="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
result=PASS
port_80_result=pass
port_443_result=pass
port_8080_result=pass
port_8000_result=pass

if ! probe_port 80 http; then port_80_result=fail; result=FAIL; fi
if ! probe_port 443 https; then port_443_result=fail; result=FAIL; fi
if ! probe_port 8080 http; then port_8080_result=fail; result=FAIL; fi
if ! probe_port 8000 http; then port_8000_result=fail; result=FAIL; fi

utc_finished="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
cat <<RESULT

=== Sanitized non-approved-source denial evidence ===
result: ${result}
window_utc: ${utc_started} to ${utc_finished}
source_assertion: vpn_disconnected=yes; independent_non_approved_source=yes
ports: 80=${port_80_result}; 443=${port_443_result}; 8080=${port_8080_result}; 8000=${port_8000_result}
expected: every port has denied=yes and no HTTP response; do not treat an application response as a successful denial.
=== End sanitized evidence ===
RESULT

if [[ "$result" != PASS ]]; then exit 1; fi
