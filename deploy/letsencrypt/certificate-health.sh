#!/bin/bash
set -euo pipefail

usage() {
    echo "usage: $0 EXPECTED_HOST CERTIFICATE_PATH [CERTBOT_TIMER]" >&2
    exit 64
}

[[ $# -ge 2 && $# -le 3 ]] || usage

expected_host=$1
certificate_path=$2
certbot_timer=${3:-snap.certbot.renew.timer}
minimum_seconds=$((72 * 60 * 60))
temporary_directory=$(mktemp -d)
trap 'rm -rf -- "$temporary_directory"' EXIT

fail() {
    echo "certificate health check failed: $*" >&2
    exit 1
}

[[ -r "$certificate_path" ]] || fail "certificate is not readable: $certificate_path"
/usr/bin/openssl x509 -in "$certificate_path" -noout -checkend "$minimum_seconds" \
    >/dev/null || fail "certificate has less than 72 hours validity remaining"
/usr/bin/openssl x509 -in "$certificate_path" -noout -checkip "$expected_host" \
    >/dev/null || fail "certificate does not contain IP SAN $expected_host"

/usr/bin/systemctl is-active --quiet nginx || fail "nginx is not active"
/usr/sbin/nginx -t >/dev/null 2>&1 || fail "nginx configuration is invalid"
/usr/bin/systemctl is-enabled --quiet "$certbot_timer" \
    || fail "$certbot_timer is not enabled"
/usr/bin/systemctl is-active --quiet "$certbot_timer" \
    || fail "$certbot_timer is not active"

served_pem="$temporary_directory/served.pem"
handshake_log="$temporary_directory/handshake.log"
if ! /usr/bin/openssl s_client \
    -connect "${expected_host}:443" \
    -servername "$expected_host" \
    -verify_ip "$expected_host" \
    -verify_return_error \
    -CApath /etc/ssl/certs \
    -showcerts </dev/null >"$served_pem" 2>"$handshake_log"; then
    fail "served certificate failed system trust or IP verification"
fi

lineage_fingerprint=$(
    /usr/bin/openssl x509 -in "$certificate_path" -noout -fingerprint -sha256
) || fail "could not fingerprint active lineage"
served_fingerprint=$(
    /usr/bin/openssl x509 -in "$served_pem" -noout -fingerprint -sha256
) || fail "could not read served certificate"
[[ "$served_fingerprint" == "$lineage_fingerprint" ]] \
    || fail "served certificate differs from active lineage"

expiry=$(/usr/bin/openssl x509 -in "$certificate_path" -noout -enddate)
echo "certificate health check passed: host=$expected_host $expiry fingerprint=${lineage_fingerprint#*=}"
