# Task 3 Certificate Change Log

Date started: 2026-07-31

This log records the self-signed certificate generation and verification
commands. The private key is generated and retained on the VM under `/etc`; it
is not copied into this repository or printed into this document.

## Certificate inputs

- Certificate address/SAN: `193.40.157.124`
- Intended lifetime: 90 days
- Certificate path: `/etc/nginx/tls/opiraja/self-signed.crt`
- Private-key path: `/etc/nginx/tls/opiraja/self-signed.key`

## Executed commands

The following commands are being executed with explicit approval:

```bash
sudo install -d -o root -g root -m 0700 /etc/nginx/tls/opiraja
sudo openssl req -x509 -nodes -newkey rsa:3072 -sha256 -days 90 \
  -keyout /etc/nginx/tls/opiraja/self-signed.key \
  -out /etc/nginx/tls/opiraja/self-signed.crt \
  -subj "/CN=193.40.157.124" \
  -addext "subjectAltName=IP:193.40.157.124" \
  -addext "basicConstraints=critical,CA:FALSE" \
  -addext "keyUsage=critical,digitalSignature,keyEncipherment" \
  -addext "extendedKeyUsage=serverAuth"
sudo chown root:root /etc/nginx/tls/opiraja/self-signed.key \
  /etc/nginx/tls/opiraja/self-signed.crt
sudo chmod 0600 /etc/nginx/tls/opiraja/self-signed.key
sudo chmod 0644 /etc/nginx/tls/opiraja/self-signed.crt
```

The verification commands printed certificate metadata and fingerprint, but never the
private key contents:

```bash
sudo openssl x509 -in /etc/nginx/tls/opiraja/self-signed.crt \
  -noout -subject -issuer -serial -fingerprint -sha256 -dates \
  -ext subjectAltName
sudo openssl pkey -in /etc/nginx/tls/opiraja/self-signed.key -check -noout
sudo stat -c '%A %U:%G %n' \
  /etc/nginx/tls/opiraja/self-signed.key \
  /etc/nginx/tls/opiraja/self-signed.crt
```

## Status

The target paths were absent and OpenSSL 3.0.13 was available before
generation. Generation and verification completed successfully.

- Subject and issuer: `CN=193.40.157.124` (self-signed)
- Subject Alternative Name: `IP:193.40.157.124`
- Valid from: `2026-07-31 13:43:59 UTC`
- Valid until: `2026-10-29 13:43:59 UTC`
- SHA-256 fingerprint:
  `73:EA:4F:30:DB:F4:23:41:4A:FA:85:52:E6:B8:5F:48:36:C9:F4:DD:48:A1:81:6C:D9:F6:C3:2A:76:20:CB:21`
- Private-key check: valid
- Key mode/owner: `0600 root:root`
- Certificate mode/owner: `0644 root:root`

The private key remains on the VM at `/etc/nginx/tls/opiraja/self-signed.key`.
