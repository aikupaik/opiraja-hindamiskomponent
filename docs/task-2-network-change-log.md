# Task 2 Network Change Log

Date started: 2026-07-31

This log records the main read-only checks and host-firewall commands used
while implementing Task 2 of the self-signed HTTPS plan. It intentionally does
not contain credentials, rendered `.env` values, private keys, or full firewall
rule dumps.

## Scope and inputs

- VM fixed address: `192.168.42.72`
- VM Floating IP: `193.40.157.124`
- Approved source ranges confirmed by the operator: `172.20.0.0/16` and
  `193.40.0.0/16`
- The OpenStack security-group changes were made by the operator in ETAIS and
  are not changed by this log's commands.

## Read-only checks

The following checks were run before staging host rules:

```bash
ss -lntup
sudo ufw status verbose
sudo ufw status numbered
sudo nft list ruleset
docker compose ps
ip -brief address
ip route
printf 'SSH_CONNECTION=%s\nSSH_CLIENT=%s\n' "$SSH_CONNECTION" "$SSH_CLIENT"
sudo sed -n '1,220p' /etc/default/ufw
sudo sed -n '1,120p' /etc/ufw/ufw.conf
sudo iptables -S DOCKER-USER
sudo ip6tables -S DOCKER-USER
sudo ufw show raw
```

Important observations:

- The current SSH source is `172.20.12.6`.
- UFW was inactive and had no active rules.
- UFW was configured for IPv6 support with default-drop input and forward
  policies, but was disabled.
- Docker's `DOCKER-USER` chains were empty.
- Compose currently publishes web HTTP on `0.0.0.0:80` and `[::]:80`; API and
  R port 8000 are not host-published. No host port 443 listener exists.

## Host-firewall policy staged before activation

The following commands changed UFW's stored policy configuration while leaving
UFW inactive:

```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing

sudo ufw allow from 172.20.0.0/16 to any port 22 proto tcp comment 'approved SSH VPN'
sudo ufw allow from 193.40.0.0/16 to any port 22 proto tcp comment 'approved SSH public range'
sudo ufw allow from 172.20.0.0/16 to any port 80 proto tcp comment 'approved HTTP VPN'
sudo ufw allow from 193.40.0.0/16 to any port 80 proto tcp comment 'approved HTTP public range'
sudo ufw allow from 172.20.0.0/16 to any port 443 proto tcp comment 'approved HTTPS VPN'
sudo ufw allow from 193.40.0.0/16 to any port 443 proto tcp comment 'approved HTTPS public range'
```

Before activation, `sudo ufw status` reported `inactive`. The staged policy was
reviewed and dry-run before UFW was enabled. Because Docker
currently publishes port 80 directly, Docker's forwarding path must also be
accounted for; the planned Compose loopback-only publication will remove that
direct public container path before host Nginx takes over ports 80 and 443.

## Activation and verification

After reviewing the staged rules, UFW was enabled with:

```bash
sudo ufw --force enable
```

The active result is:

- UFW active and enabled at boot.
- Default inbound policy: deny.
- Default outbound policy: allow.
- Default routed/forwarded policy: deny.
- TCP 22, 80, and 443 allowed only from `172.20.0.0/16` and
  `193.40.0.0/16`.
- IPv6 filtering is active with no IPv6 TCP allow rules.

Post-change checks were run:

```bash
sudo ufw status verbose
sudo ufw status numbered
sudo nft list ruleset
ss -lntup
curl --max-time 5 -sS -o /dev/null -w 'HTTP / status=%{http_code}\n' http://127.0.0.1/
curl --max-time 5 -sS -o /dev/null -w 'API health status=%{http_code}\n' http://127.0.0.1/health/ready
docker compose ps
```

Results: the SSH session remained usable, local HTTP and API health returned
200, and all Compose services remained healthy. The listener and Compose
publication state did not change.

Important limitation: the current Docker-published port 80 is processed by the
Docker forwarding chain before UFW's host-input chain, and `DOCKER-USER` is
empty. UFW therefore does not by itself enforce source restrictions on that
container-forwarding path. The OpenStack security group is the current outer
restriction; the planned loopback-only Compose publication is still required
before host Nginx owns public ports 80 and 443.

## Not performed

- No nftables or `DOCKER-USER` rules were manually added.
- Compose, Docker services, host Nginx, OpenStack security groups, and ETAIS
  resources have not been changed.

## Next verification

Test HTTP/HTTPS access from an approved source and a non-approved source; those
tests cannot be simulated reliably from this VM. Recheck listeners and firewall
rules after the Compose publication and host-Nginx cutover. At that point the
web container must be loopback-only so UFW protects the host-Nginx public path.
