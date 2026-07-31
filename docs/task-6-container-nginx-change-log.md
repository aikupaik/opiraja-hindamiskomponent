# Task 6 Container-Nginx Change Log

Date started: 2026-07-31

## Project changes

Updated `admin/nginx.conf` so the inner proxy:

- maps only an exact incoming `X-Forwarded-Proto: https` to `https`, and uses
  `http` for direct internal requests;
- preserves the host-generated client IP and forwarded-host metadata;
- appends only the inner proxy hop to the host-provided `X-Forwarded-For`;
- passes the host-generated `X-Request-ID`; and
- applies the same proxy metadata to SSE, normal API, and both health routes.
- allows the Docker edge bridge gateway used by the host-loopback publication
  to run the local `/nginx-health` probe while continuing to deny other peers.

Existing SSE buffering/cache behavior, timeouts, body limit, SPA fallback,
asset caching, blocked routes, and browser headers were retained. The admin
image now runs `nginx -t -c /etc/nginx/nginx.conf` during the image build.

## VM deployment status

The web image was rebuilt on the VM and passed its Dockerfile `nginx -t`
step. The web container was recreated and is healthy. The VM loopback checks
return 200 for both `/nginx-health` and `/health/ready`; the host Nginx public
site still returns 404 for both protected paths.
