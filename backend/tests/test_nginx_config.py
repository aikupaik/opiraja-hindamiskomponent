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


def test_rate_limits_remain_dry_run_until_deployed_review() -> None:
    config = (
        Path(__file__).parents[2] / "deploy" / "nginx" / "opiraja.conf"
    ).read_text(encoding="utf-8")
    assert "limit_req_dry_run on;" in config
    assert "limit_conn_dry_run on;" in config
