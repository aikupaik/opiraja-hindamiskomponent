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
| Preflight date and UTC time range |   |
| Operator | Andreas |
| Maintenance window approved by | Operator |
| No student/admin activity confirmed by | Operator |
| Deployment repository path | `/home/ubuntu/opiraja-hindamiskomponent` |
| Git commit | 96caa92 |
| Worktree state (clean or listed changes) | clean |
| Compose validation (`docker compose config --quiet`) | Done |
| Service/image IDs and restart counts | image_id=sha256:50b632f3355ef8d250c114e31cc64248aaffcd320a2db06f2a1a96c9fccfce13 restart_count=0, image_id=sha256:3de7bf3736f511594a2f360130f3b0d5db9437b0460d0b35ede8cfe450060299 restart_count=0, image_id=sha256:6ca7136c9540ba4f4bbfd4c33d6724714a334ca0927a13fedaf3123259267565 restart_count=0, image_id=sha256:83da605c5ba76235cab140b2b8c8c709a94a26d6edc1b64370058bb67526e466 restart_count=0 |
| Host-Nginx configuration SHA-256 |  |

### VM and ingress

| Field | Value |
| --- | --- |
| VM vCPU | 8 |
| VM RAM | total 16375624 |
| Disk/storage capacity and free space | total 200G, available 135G |
| Network interfaces/routes and known bandwidth |  |
| Public HTTPS base URL | https://192.168.42.72 |
| Current ingress policy (approved CIDR or temporary public access) | temporary public access |
| Generator public IP/CIDR | 193.40.250.119 |
| Docker-published ports | |
| Host listeners on `80`/`443` | |
| No host listener on `8000` confirmed | |
| Certificate SHA-256 fingerprint, subject, and expiry | |
| VM clock synchronization state | |
| Backup location, owner, and last successful backup time | |
| Log/disk headroom | |

### Runtime configuration and health

| Field | Value |
| --- | --- |
| API Uvicorn worker count | |
| R process/replica count | |
| `R_MAX_CONNECTIONS` | |
| R connect/read/write/pool timeouts | |
| Readiness timeout | |
| Supabase request timeout | |
| API `/health/ready` result | |
| R `/health` result | |
| Container health/restart state | |
| Public Nginx rate/connection-limit policy | |

### Supabase and idle baseline

| Field | Value |
| --- | --- |
| Supabase project reference | |
| Tier/plan | |
| Region | |
| Documented CPU/RAM/I/O/connection limits | |
| Dashboard observation UTC range | |
| Idle CPU/RAM/I/O/connections/API latency/database latency/errors | |
| VM idle evidence directory | |
| Idle CPU/memory/disk/network/container summary | |

### Preflight decision

| Decision | Value |
| --- | --- |
| Abort thresholds reviewed and understood | yes / no |
| Ready for static-edge 1-user smoke | yes / no |
| Blockers or follow-up actions | |
