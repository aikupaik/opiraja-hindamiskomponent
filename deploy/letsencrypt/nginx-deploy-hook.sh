#!/bin/sh
set -eu

# Certbot runs deploy hooks as root after a successful renewal. Never replace
# a working Nginx process with configuration that has not passed validation.
# Nginx writes successful validation messages to stderr, so capture them and
# emit output only when validation actually fails.
if ! validation_output=$(/usr/sbin/nginx -t 2>&1); then
    printf '%s\n' "$validation_output" >&2
    exit 1
fi
/usr/bin/systemctl reload nginx
