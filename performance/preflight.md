# Pilot performance preflight worksheet

Complete this worksheet on the pilot VM before any load scenario beyond a
one-request smoke check. It records the exact environment to which later
results apply. It does not start, stop, rebuild, reload, or reconfigure
anything.

## Safety rules

- Run the commands from the deployed repository root on the VM.
- Do **not** print `.env`, use `docker compose config` without `--quiet`, dump
  container environments, or copy JWTs, service keys, cookies, or player
  tokens into this document or its result files.
- The commands below are read-only, except the idle-baseline collector, which
  writes an evidence file under ignored `performance/results/`.
- Do not run a load test until the maintenance window is active, no students
  or unrelated administration are using the pilot, and every required field
  below is complete.

## 1. VM collection commands

Run this block from the deployment repository root. It validates the Compose
model without rendering configuration (which could expose environment values),
then records deployment identity, health, host capacity, listeners, firewall,
time synchronization, log/disk headroom, and certificate metadata.

```sh
git status --short
git rev-parse HEAD
git log -1 --format='%cI %h %s'

docker compose config --quiet
docker compose ps
docker compose images --format json
docker compose ps api r-service

API_CONTAINER_ID="$(docker compose ps -q api)"
docker inspect --format 'api_command={{json .Config.Cmd}}' "$API_CONTAINER_ID"

for container_id in $(docker compose ps -q); do
  docker inspect --format \
    '{{.Name}} image={{.Config.Image}} image_id={{.Image}} restart_count={{.RestartCount}} pids_limit={{.HostConfig.PidsLimit}} memory_bytes={{.HostConfig.Memory}} nano_cpus={{.HostConfig.NanoCPUs}}' \
    "$container_id"
done

nproc
lscpu
free -w
df -hT / /var/log /var/lib/docker
lsblk -o NAME,SIZE,FSTYPE,MOUNTPOINTS
ip -brief link
ip -brief address
ip route
sudo ss -ltnp
sudo ufw status verbose
sudo ufw status numbered

timedatectl status
systemctl is-active systemd-timesyncd || true
chronyc tracking 2>/dev/null || true

sudo journalctl --disk-usage
docker system df
sudo nginx -t
sudo sha256sum /etc/nginx/sites-enabled/opiraja.conf
sudo grep -E '^[[:space:]]*(limit_req_zone|limit_conn_zone|limit_req |limit_conn |limit_req_dry_run|limit_conn_dry_run)' \
  /etc/nginx/sites-enabled/opiraja.conf
sudo openssl x509 -in /etc/nginx/tls/opiraja/self-signed.crt \
  -noout -fingerprint -sha256 -subject -issuer -dates
```

Expected healthy state includes running/healthy Compose services, host Nginx
listening on `80`/`443`, Docker publishing only `127.0.0.1:8080`, and no host
listener for API or R port `8000`. If the certificate has moved to a trusted
FQDN certificate, replace the final certificate path with its actual public
certificate path; never reference a private-key file.

## 2. Non-secret API settings and dependency health

This command reads only the listed timing, pool, and graph-limit values from
the already-running API container. It deliberately excludes every secret,
credential, URL, issuer, and host setting.

```sh
docker compose exec -T api sh -c '
  env | LC_ALL=C sort | grep -E \
  "^(MAX_GRAPH_NODES|R_MAX_CONNECTIONS|R_CONNECT_TIMEOUT_SECONDS|R_READ_TIMEOUT_SECONDS|R_WRITE_TIMEOUT_SECONDS|R_POOL_TIMEOUT_SECONDS|READINESS_TIMEOUT_SECONDS|SUPABASE_REQUEST_TIMEOUT_SECONDS)=" \
  || true
'

docker compose exec -T api python -c '
import urllib.request
response = urllib.request.urlopen("http://127.0.0.1:8000/health/ready", timeout=5)
print(response.status, response.read().decode())
'

docker compose exec -T r-service Rscript --vanilla -e \
'cat(paste(readLines("http://127.0.0.1:8000/health", warn = FALSE), collapse = ""), "\\n")'
```

If a listed setting is absent, the application default applies; record that
default and mark it as `default`, rather than changing the VM environment.
The expected health responses are successful and contain only readiness state.

## 3. Five-minute idle baseline capture

Leave the pilot otherwise idle. The following captures 60 samples at five
second intervals, including host load/memory/disk, cumulative network
counters, and per-container CPU/memory/network/block-I/O/PIDs. It does not
stream application logs and does not print container environment values.

```sh
RUN_ID="preflight-$(date -u +%Y%m%dT%H%M%SZ)"
RESULT_DIR="performance/results/$RUN_ID/vm"
mkdir -p "$RESULT_DIR"

for sample in $(seq 1 60); do
  {
    echo "--- sample=$sample time=$(date -Is) ---"
    uptime
    free -w
    df -P / /var/log /var/lib/docker
    cat /proc/net/dev
    docker stats --no-stream \
      --format 'container={{.Name}} cpu={{.CPUPerc}} memory={{.MemUsage}} memory_pct={{.MemPerc}} net={{.NetIO}} block_io={{.BlockIO}} pids={{.PIDs}}'
  } >> "$RESULT_DIR/idle-baseline.txt"
  sleep 5
done

docker compose ps > "$RESULT_DIR/compose-ps-after-idle.txt"
```

Record the result directory below. Retain it as raw evidence; do not commit
it. The counters in `/proc/net/dev` are cumulative, so use differences between
samples to assess idle network activity.

## 4. Supabase console collection

In the pilot Supabase dashboard, record the project reference, selected plan or
tier, region, documented CPU/RAM/connection/database limits, and the dashboard
time range used for the idle observation. During the same five-minute VM idle
window, capture CPU, RAM, I/O, connections, API/database latency, and error
counts. Do not copy database passwords, service-role keys, API keys, or query
result contents into this worksheet.

## 5. Completion record

Fill every field before proceeding to the static-edge scenario.

### Window and deployment identity

| Field | Value |
| --- | --- |
| Preflight date and UTC time range | 2026-08-21; VM checks 06:28 UTC, idle baseline 06:28:33–06:35:36 UTC |
| Operator | Andreas |
| Maintenance window approved by | Operator |
| No student/admin activity confirmed by | Operator |
| Deployment repository path | `/home/ubuntu/opiraja-hindamiskomponent` |
| Git commit | `c2c9155f27d35fced20a9c76a3cd0affee588d08` (`c2c9155`) |
| Worktree state (clean or listed changes) | clean at collection time; this worksheet update is subsequent |
| Compose validation (`docker compose config --quiet`) | Done |
| Service/image IDs and restart counts | `api=sha256:50b632f3355ef8d250c114e31cc64248aaffcd320a2db06f2a1a96c9fccfce13`; `player=sha256:3de7bf3736f511594a2f360130f3b0d5db9437b0460d0b35ede8cfe450060299`; `r-service=sha256:6ca7136c9540ba4f4bbfd4c33d6724714a334ca0927a13fedaf3123259267565`; `web=sha256:83da605c5ba76235cab140b2b8c8c709a94a26d6edc1b64370058bb67526e466`; all `restart_count=0`, running/healthy |
| Host-Nginx configuration SHA-256 | `cb10f4c7d316e3c707432d9892f071755945728d94220811bab58f516b14264c` |

### VM and ingress

| Field | Value |
| --- | --- |
| VM vCPU | 8 |
| VM RAM | 16,375,624 KiB (~15.62 GiB); idle available 15,135,440–15,192,516 KiB; no swap |
| Disk/storage capacity and free space | 200G disk; `/` ext4 193G, 59G used, 135G available (31%) |
| Network interfaces/routes and known bandwidth | `ens3` 192.168.42.72/24; default via 192.168.42.1; Docker bridges `172.18.0.0/16` and `172.30.0.0/24`; link detected, negotiated bandwidth unavailable (`ethtool` reports unknown) |
| Public HTTPS base URL | https://193.40.157.124/ |
| Current ingress policy (approved CIDR or temporary public access) | UFW active: SSH/HTTP/HTTPS from 172.20.0.0/16 and 193.40.0.0/16; temporary public HTTP and HTTPS from Anywhere |
| Generator public IP/CIDR | 193.40.250.119 |
| Docker-published ports | `127.0.0.1:8080->web:8080/tcp`; no host publish for API, R, or player |
| Host listeners on `80`/`443` | Nginx on `0.0.0.0:80` and `0.0.0.0:443` |
| No host listener on `8000` confirmed | yes; `ss -ltnp` showed no host listener on 8000 |
| Certificate SHA-256 fingerprint, subject, and expiry | SHA-256 `73:EA:4F:30:DB:F4:23:41:4A:FA:85:52:E6:B8:5F:48:36:C9:F4:DD:48:A1:81:6C:D9:F6:C3:2A:76:20:CB:21`; subject/issuer `CN=193.40.157.124`; expires 2026-10-29 13:43:59 UTC |
| VM clock synchronization state | synchronized; NTP active; Europe/Tallinn (EEST, UTC+03:00) |
| Backup location, owner, and last successful backup time | data.sql, roles.sql, schema.sql, 2026-08-24T19:08:53Z, owner: Andreas, verification done, SHA-256 recorded |
| Log/disk headroom | Journald 115.8M; `/` 135G available (31% used); Docker images 15.48G and build cache 38.26G (20.59G reclaimable) |

### Runtime configuration and health

| Field | Value |
| --- | --- |
| API Uvicorn worker count | 1 (`--workers 1`) |
| R process/replica count | 1 `r-service` container/process |
| `R_MAX_CONNECTIONS` | 4 |
| R connect/read/write/pool timeouts | connect 2s; read 30s; write 5s; pool 1s |
| Readiness timeout | 1s |
| Supabase request timeout | 10s |
| API `/health/ready` result | HTTP 200: `{"status":"ready","dependencies":{"supabase":"ready","r":"ready"}}` |
| R `/health` result | `{"status":"ok"}` |
| Container health/restart state | API, player, r-service, and web running/healthy; restart count 0 for all |
| Public Nginx rate/connection-limit policy | Enforcement active (`limit_req_dry_run off`, `limit_conn_dry_run off`): player 50r/s burst 100; API 10r/s burst 20; admin login 5r/m burst 5; issuance 2r/s burst 10; admin SSE connection limit 2 |

### Supabase and idle baseline

| Field | Value |
| --- | --- |
| Supabase project reference | kwwxpsrojgtziluguqkm |
| Tier/plan | Nano (Free plan) |
| Region | eu-west-3 |
| Documented CPU/RAM/I/O/connection limits | Shared CPU, 0.5GB memory, IOPS 3000, Throughput 125MB/s, 60 connections max, storage 2GB|
| Dashboard observation UTC range | 2026-08-21T06:45:25Z |
| Idle CPU/RAM/I/O/connections/API latency/database latency/errors | **Supabase Idle: CPU 2%, Disk 14%, RAM 51%, 9/60 conns. VM: 60 samples, 06:28:33–06:35:36 UTC; 1-minute load 0.05–0.48; RAM used 1.13–1.18 GiB, available 14.43–14.49 GiB; no swap; no observed Docker block-I/O change; API/R latency and error counts not collected by this baseline** |
| VM idle evidence directory | `performance/results/preflight-20260821T062833Z/vm/` |
| Idle CPU/memory/disk/network/container summary | Host CPU utilization was not directly measured; load average 0.05–0.48. `/` remained 31% used with ~135G available. `ens3` counters increased ~2.38 MB RX / ~3.53 MB TX; 0 errors/drops. Container CPU ranges: API 0.30–42.60%, web 0.00–6.51%, player 0.00–5.89%, R 0.00–119.13%; memory remained ~77.4 MiB, 8.6 MiB, 5.9 MiB, and 122.7 MiB respectively. |

### Preflight decision

| Decision | Value |
| --- | --- |
| Abort thresholds reviewed and understood | **Confirmed** |
| Ready for static-edge 1-user smoke | **Ready** |
| Blockers or follow-up actions | No blockers |
