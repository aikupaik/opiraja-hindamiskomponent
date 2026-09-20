"""Static acceptance checks for JWT-sensitive edge policy."""

from pathlib import Path


def test_endpoint_limits_timeouts_and_cache_policy_are_present() -> None:
    config = (
        Path(__file__).parents[2] / "deploy" / "nginx" / "opiraja.conf"
    ).read_text(encoding="utf-8")

    for directive in (
        "zone=opiraja_admin_login_rate:1m rate=5r/m",
        "zone=opiraja_issuance_rate:1m rate=2r/s",
        "zone=opiraja_player_rate:1m rate=50r/s",
        "limit_req zone=opiraja_admin_login_rate burst=5 nodelay",
        "limit_req zone=opiraja_issuance_rate burst=10 nodelay",
        "limit_req zone=opiraja_player_rate burst=100 nodelay",
        "limit_conn opiraja_admin_sse_connections 2",
        "client_header_timeout 10s",
        "client_body_timeout 30s",
        'add_header Cache-Control "no-store" always',
    ):
        assert directive in config

    assert "location = /api/v1/admin/login" in config
    assert "location = /api/v1/tests" in config
    assert "/player-token$" in config
    assert "/(start|answers)$" in config
    assert '"$request_method $uri $server_protocol"' in config
    assert "$http_authorization" not in config


def test_rate_limits_are_enforced_after_deployment_review() -> None:
    config = (
        Path(__file__).parents[2] / "deploy" / "nginx" / "opiraja.conf"
    ).read_text(encoding="utf-8")
    assert "limit_req_dry_run off;" in config
    assert "limit_conn_dry_run off;" in config
    assert "limit_req_dry_run on;" not in config
    assert "limit_conn_dry_run on;" not in config


def test_grafana_proxy_is_loopback_restricted_and_subpath_aware() -> None:
    config = (
        Path(__file__).parents[2] / "deploy" / "nginx" / "opiraja.conf"
    ).read_text(encoding="utf-8")

    assert "location = /grafana {" in config
    assert "return 308 /grafana/;" in config
    assert "location = /grafana/login {" in config
    assert "location ^~ /grafana/ {" in config
    assert config.count("proxy_pass http://127.0.0.1:3000;") == 2
    assert config.count("allow 172.20.0.0/16;") == 3
    assert config.count("allow 193.40.0.0/16;") == 3
    assert config.count("deny all;") == 3
    assert "geo $opiraja_grafana_source_allowed" in config
    assert "if ($opiraja_grafana_source_allowed = 0) { return 403; }" in config


def test_grafana_proxy_trusts_only_host_nginx_forwarding_metadata() -> None:
    config = (
        Path(__file__).parents[2] / "deploy" / "nginx" / "opiraja.conf"
    ).read_text(encoding="utf-8")

    assert "map $http_upgrade $opiraja_connection_upgrade" in config
    assert config.count("proxy_set_header Upgrade $http_upgrade;") == 2
    assert (
        config.count(
            "proxy_set_header Connection $opiraja_connection_upgrade;"
        )
        == 2
    )
    assert config.count("proxy_set_header X-Forwarded-For $remote_addr;") >= 2
    assert "proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;" not in config


def test_grafana_login_limit_and_csp_separation_are_present() -> None:
    config = (
        Path(__file__).parents[2] / "deploy" / "nginx" / "opiraja.conf"
    ).read_text(encoding="utf-8")

    assert "zone=opiraja_grafana_login_rate:1m rate=5r/m" in config
    assert "limit_req zone=opiraja_grafana_login_rate burst=5 nodelay" in config

    grafana_start = config.index("    location = /grafana/login {")
    grafana_end = config.index("\n    }", grafana_start)
    grafana_login = config[grafana_start:grafana_end]
    assert "add_header Content-Security-Policy" not in grafana_login
    assert "proxy_hide_header Content-Security-Policy" not in grafana_login
    assert 'add_header Cache-Control "no-store" always;' in grafana_login

    assert '"$request_method $uri $server_protocol"' in config
    assert "$request_uri" not in config.split("log_format opiraja", maxsplit=1)[1].split(
        ";", maxsplit=1
    )[0]
