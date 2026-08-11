#!/usr/bin/env bash
# Run from an approved VPN client after the operator has independently checked
# the certificate warning/fingerprint before entering any credentials.
#
# This covers repeatable, unauthenticated approved-client checks. It does not
# test independent non-approved-source denial, and it never prints response
# bodies, request IDs, certificate fingerprints, or its redirect query value.

set -euo pipefail

readonly TARGET_HOST="${OPIRAJA_TARGET_HOST:-193.40.157.124}"
readonly CONNECT_TIMEOUT_SECONDS=10
readonly EXPECTED_CERT_FINGERPRINT='73:EA:4F:30:DB:F4:23:41:4A:FA:85:52:E6:B8:5F:48:36:C9:F4:DD:48:A1:81:6C:D9:F6:C3:2A:76:20:CB:21'
readonly PROBE_PATH='/phase-2-external-check'
readonly PROBE_QUERY='phase2_external=approved'

for required_command in curl openssl timeout; do
  if ! command -v "$required_command" >/dev/null 2>&1; then
    printf 'ERROR: %s is required but was not found.\n' "$required_command" >&2
    exit 1
  fi
done

umask 077
work_dir="$(mktemp -d "${TMPDIR:-/tmp}/opiraja-approved-check.XXXXXX")"
cleanup() {
  rm -f -- "$work_dir"/*
  rmdir -- "$work_dir" 2>/dev/null || true
}
trap cleanup EXIT HUP INT TERM

header_count() {
  local header_file="$1"
  local header_name="$2"
  awk -v wanted="$header_name" 'BEGIN { wanted=tolower(wanted) ":" } tolower($0) ~ "^" wanted { count++ } END { print count + 0 }' "$header_file"
}

header_has_value() {
  local header_file="$1"
  local header_name="$2"
  local expected_value="$3"
  awk -v wanted="$header_name" -v expected="$expected_value" 'BEGIN { wanted=tolower(wanted) ":"; expected=tolower(expected) } { line=tolower($0); if (index(line, wanted) == 1) { sub("^[^:]*:[[:space:]]*", "", line); sub("\\r$", "", line); if (line == expected) found=1 } } END { exit(found ? 0 : 1) }' "$header_file"
}

last_http_status() {
  awk '/^HTTP\// { status=$2 } END { print status }' "$1"
}

redirect_headers="$work_dir/redirect.headers"
https_headers="$work_dir/https.headers"
forged_headers="$work_dir/forged.headers"
certificate_info="$work_dir/certificate.info"
utc_started="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

set +e
curl --disable --http1.1 --silent --show-error --connect-timeout "$CONNECT_TIMEOUT_SECONDS" --max-time "$CONNECT_TIMEOUT_SECONDS" --dump-header "$redirect_headers" --output /dev/null "http://${TARGET_HOST}${PROBE_PATH}?${PROBE_QUERY}"
redirect_curl_exit=$?
curl --disable --insecure --http1.1 --silent --show-error --connect-timeout "$CONNECT_TIMEOUT_SECONDS" --max-time "$CONNECT_TIMEOUT_SECONDS" --dump-header "$https_headers" --output /dev/null "https://${TARGET_HOST}/"
https_curl_exit=$?
curl --disable --insecure --http1.1 --silent --show-error --connect-timeout "$CONNECT_TIMEOUT_SECONDS" --max-time "$CONNECT_TIMEOUT_SECONDS" --dump-header "$forged_headers" --output /dev/null --header 'X-Forwarded-For: 198.51.100.7' --header 'X-Forwarded-Proto: http' --header 'X-Real-IP: 198.51.100.7' --header 'X-Request-ID: phase2-forged-request-id' "https://${TARGET_HOST}/"
forged_curl_exit=$?
timeout "${CONNECT_TIMEOUT_SECONDS}s" openssl s_client -connect "${TARGET_HOST}:443" -servername "$TARGET_HOST" </dev/null 2>/dev/null | openssl x509 -noout -subject -ext subjectAltName -fingerprint -sha256 >"$certificate_info" 2>/dev/null
certificate_exit=$?
set -e

redirect_status="$(last_http_status "$redirect_headers")"
https_status="$(last_http_status "$https_headers")"
forged_status="$(last_http_status "$forged_headers")"
expected_location="https://${TARGET_HOST}${PROBE_PATH}?${PROBE_QUERY}"
redirect_location="$(awk 'BEGIN { IGNORECASE=1 } /^Location:/ { sub(/\r$/, ""); sub(/^[^:]*:[[:space:]]*/, ""); value=$0 } END { print value }' "$redirect_headers")"

redirect_preserved=no
if [[ "$redirect_status" == 308 && "$redirect_location" == "$expected_location" ]]; then redirect_preserved=yes; fi
referrer_policy=no
x_content_type_options=no
x_frame_options=no
hsts_absent=no
x_request_id_single=no
if header_has_value "$https_headers" Referrer-Policy no-referrer; then referrer_policy=yes; fi
if header_has_value "$https_headers" X-Content-Type-Options nosniff; then x_content_type_options=yes; fi
if header_has_value "$https_headers" X-Frame-Options DENY; then x_frame_options=yes; fi
if [[ "$(header_count "$https_headers" Strict-Transport-Security)" == 0 ]]; then hsts_absent=yes; fi
if [[ "$(header_count "$https_headers" X-Request-ID)" == 1 ]]; then x_request_id_single=yes; fi
certificate_subject_san_match=no
certificate_fingerprint_match=no
if [[ "$certificate_exit" == 0 ]] && grep -q "CN = ${TARGET_HOST}" "$certificate_info" && grep -q "IP Address:${TARGET_HOST}" "$certificate_info"; then certificate_subject_san_match=yes; fi
if [[ "$certificate_exit" == 0 ]] && grep -q "SHA256 Fingerprint=${EXPECTED_CERT_FINGERPRINT}" "$certificate_info"; then certificate_fingerprint_match=yes; fi
forged_request_id_replaced=no
if [[ "$forged_status" == 200 && "$(header_count "$forged_headers" X-Request-ID)" == 1 ]] && ! grep -qi '^X-Request-ID: phase2-forged-request-id' "$forged_headers"; then forged_request_id_replaced=yes; fi

cat <<'BROWSER_INSTRUCTIONS'

Manual browser check (approved client, clean profile/extensions disabled):
  1. Open the HTTPS root and accept only the expected self-signed warning.
  2. Confirm there is no certificate name-mismatch warning.
  3. In developer tools, confirm no application mixed-content, CORS, asset-load,
     or CSP errors occur while the SPA loads.
BROWSER_INSTRUCTIONS
read -r -p 'Did the clean-browser check pass? [y/N]: ' browser_answer
browser_check=no
if [[ "$browser_answer" =~ ^[Yy]([Ee][Ss])?$ ]]; then browser_check=yes; fi

utc_finished="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
result=PASS
if [[ "$redirect_curl_exit" != 0 || "$https_curl_exit" != 0 || "$forged_curl_exit" != 0 || "$redirect_preserved" != yes || "$https_status" != 200 || "$(header_count "$https_headers" Content-Security-Policy)" != 1 || "$referrer_policy" != yes || "$x_content_type_options" != yes || "$x_frame_options" != yes || "$hsts_absent" != yes || "$x_request_id_single" != yes || "$certificate_subject_san_match" != yes || "$certificate_fingerprint_match" != yes || "$forged_request_id_replaced" != yes || "$browser_check" != yes ]]; then
  result=FAIL
fi

cat <<RESULT

=== Sanitized approved-client external-check evidence ===
result: ${result}
window_utc: ${utc_started} to ${utc_finished}
http_redirect: curl_exit=${redirect_curl_exit}; status=${redirect_status:-none}; exact_path_and_query_preserved=${redirect_preserved}
https_root: curl_exit=${https_curl_exit}; status=${https_status:-none}; csp_headers=$(header_count "$https_headers" Content-Security-Policy); referrer_policy_no_referrer=${referrer_policy}; x_content_type_options_nosniff=${x_content_type_options}; x_frame_options_deny=${x_frame_options}; hsts_absent=${hsts_absent}; x_request_id_headers_exactly_one=${x_request_id_single}
certificate: subject_and_ip_san_match=${certificate_subject_san_match}; recorded_fingerprint_match=${certificate_fingerprint_match}
forged_headers: curl_exit=${forged_curl_exit}; status=${forged_status:-none}; x_request_id_replaced=${forged_request_id_replaced}; vm_log_confirmation_of_forwarded_header_replacement=required
clean_browser: ${browser_check}
remaining_manual_gate: independently repeat the denial test from a non-approved source on ports 80, 443, 8080, and 8000; do not weaken any ingress rule.
=== End sanitized evidence ===
RESULT

if [[ "$result" != PASS ]]; then exit 1; fi
