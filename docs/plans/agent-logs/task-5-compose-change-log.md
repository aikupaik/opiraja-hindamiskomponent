# Task 5 Compose Change Log

Date started: 2026-07-31

## Project changes

- Changed the web publication to `127.0.0.1:8080:8080`. No Compose service
  publishes port 80, 443, or either internal port 8000 to the host.
- Set the explicit Docker `edge` subnet to `172.30.0.0/24`.
- Set `FORWARDED_ALLOW_IPS=172.30.0.0/24` for the API. The value is the
  trusted inner-proxy network and is not a wildcard.
- Kept the API/R `compute` network internal and did not add certificate mounts,
  TLS variables, or a 443 publication.

## VM verification and deployment status

Read-only inspection confirmed the existing networks were `172.17.0.0/16`,
`172.18.0.0/16`, and `172.19.0.0/16`; the selected subnet is unused by the
current VM route table and does not overlap the approved `172.20.0.0/16` VPN
range. Before this change the VM still had `0.0.0.0:80` and `[::]:80` mapped
to the web container. After repository validation:

- `docker compose build web api` completed successfully.
- `docker compose up -d --force-recreate --remove-orphans` removed and
  recreated the edge network and all services.
- The web image was rebuilt once more after the task 6 health-probe adjustment
  and the web service was recreated.
- Final `docker compose ps` shows all three services healthy, with only
  `127.0.0.1:8080->8080` published for web and `8000/tcp` shown only as
  container metadata for API/R.
- `http://127.0.0.1:8080/nginx-health` and the loopback API readiness check
  both return 200.
