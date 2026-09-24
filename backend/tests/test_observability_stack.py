"""Static acceptance checks for the repository observability stack."""

import json
from pathlib import Path


ROOT = Path(__file__).parents[2]


def test_compose_uses_pinned_private_observability_services() -> None:
    compose = (ROOT / "compose.yaml").read_text(encoding="utf-8")

    for image in (
        "grafana/loki:3.7.8@sha256:1107dd5274e0ada47e42472b7a7e71f3b2a2fe878878108f3e2f9e51528f0193",
        "grafana/alloy:v1.19.2@sha256:b8ec653c44235fbe910879145dac3597d66b0aaecf60bcbbe82580767771a839",
        "grafana/grafana:13.2.2@sha256:ac461fb352abc50da10a51c7d02462e9c05488f11f53f14b3ad79a8145f638a0",
    ):
        assert image in compose

    assert '"127.0.0.1:3000:3000"' in compose
    assert '"3100:3100"' not in compose
    assert '"12345:12345"' not in compose
    assert "  observability:\n    driver: bridge\n    internal: true" in compose
    assert "  grafana-host:\n    driver: bridge" in compose
    assert compose.count("max-size: \"10m\"") == 7
    assert compose.count("max-file: \"5\"") == 7


def test_observability_requires_an_explicit_compose_profile() -> None:
    compose = (ROOT / "compose.yaml").read_text(encoding="utf-8")

    assert compose.count("    profiles:\n      - observability") == 3
    service_boundaries = {
        "loki": ("  loki:\n", "  alloy:\n"),
        "alloy": ("  alloy:\n", "  grafana:\n"),
        "grafana": ("  grafana:\n", "secrets:\n"),
    }
    for start, end in service_boundaries.values():
        service_block = compose[compose.index(start) : compose.index(end)]
        assert "profiles:\n      - observability" in service_block


def test_api_environment_file_has_a_safe_production_default() -> None:
    compose = (ROOT / "compose.yaml").read_text(encoding="utf-8")

    assert "path: ${APP_ENV_FILE:-./.env}" in compose


def test_only_alloy_has_docker_socket_and_only_apps_opt_in() -> None:
    compose = (ROOT / "compose.yaml").read_text(encoding="utf-8")

    assert compose.count("com.opiraja.logs.enabled: \"true\"") == 2
    assert "com.opiraja.logs.service: \"api\"" in compose
    assert "com.opiraja.logs.service: \"r-service\"" in compose
    assert compose.count("/var/run/docker.sock:/var/run/docker.sock:ro") == 1
    assert "/var/lib/docker/containers" not in compose
    assert "co.elastic.logs" not in compose
    assert "filebeat:" not in compose


def test_persistent_paths_and_secret_files_are_configured() -> None:
    compose = (ROOT / "compose.yaml").read_text(encoding="utf-8")
    env_example = (ROOT / ".env.example").read_text(encoding="utf-8")
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")

    for name in (
        "LOKI_DATA_DIR",
        "ALLOY_DATA_DIR",
        "GRAFANA_DATA_DIR",
        "GRAFANA_ADMIN_PASSWORD_FILE",
        "GRAFANA_SECRET_KEY_FILE",
    ):
        assert name in compose
        assert name in env_example
    assert "GF_SECURITY_ADMIN_PASSWORD__FILE" in compose
    assert "GF_SECURITY_SECRET_KEY__FILE" in compose
    assert "target: grafana-admin-password" in compose
    assert "target: grafana-secret-key" in compose
    assert 'GF_PLUGINS_PREINSTALL_DISABLED: "true"' in compose
    assert 'GF_PLUGINS_PLUGIN_ADMIN_ENABLED: "false"' in compose
    assert ".runtime/" in gitignore


def test_loki_has_tsdb_filesystem_and_fourteen_day_retention() -> None:
    config = (ROOT / "observability" / "loki" / "loki.yaml").read_text(
        encoding="utf-8"
    )

    for expected in (
        "auth_enabled: false",
        "path_prefix: /var/lib/loki",
        "replication_factor: 1",
        "store: tsdb",
        "object_store: filesystem",
        "schema: v13",
        "working_directory: /var/lib/loki/compactor",
        "retention_enabled: true",
        "delete_request_store: filesystem",
        "retention_period: 336h",
        "discover_service_name: []",
        "discover_log_levels: false",
    ):
        assert expected in config


def test_alloy_keeps_a_bounded_label_set_and_retains_bad_lines() -> None:
    config = (ROOT / "observability" / "alloy" / "config.alloy").read_text(
        encoding="utf-8"
    )

    assert 'loki.source.docker "opiraja"' in config
    assert "__meta_docker_container_log_stream" in config
    assert "relabel_rules    = discovery.relabel.opiraja_stream.rules" in config
    assert 'event = "parser_error"' in config
    assert 'level = "UNKNOWN"' in config
    assert "drop_malformed = false" in config
    for label in ("service", "level", "event", "stream"):
        assert label in config
    for forbidden_label in (
        "request_id  =",
        "test_id     =",
        "path        =",
        "status      =",
        "duration_ms =",
    ):
        assert forbidden_label not in config


def test_grafana_provisioning_and_dashboard_are_version_controlled() -> None:
    datasource = (
        ROOT
        / "observability"
        / "grafana"
        / "provisioning"
        / "datasources"
        / "loki.yaml"
    ).read_text(encoding="utf-8")
    provider = (
        ROOT
        / "observability"
        / "grafana"
        / "provisioning"
        / "dashboards"
        / "opiraja.yaml"
    ).read_text(encoding="utf-8")
    dashboard_path = (
        ROOT
        / "observability"
        / "grafana"
        / "dashboards"
        / "opiraja-api-r-logs.json"
    )
    dashboard = json.loads(dashboard_path.read_text(encoding="utf-8"))

    assert "uid: opiraja-loki" in datasource
    assert "url: http://loki:3100" in datasource
    assert "isDefault: true" in datasource
    assert "editable: false" in datasource
    assert "allowUiUpdates: false" in provider
    assert dashboard["uid"] == "opiraja-api-r-logs"
    assert dashboard["editable"] is False
    assert {item["name"] for item in dashboard["templating"]["list"]} == {
        "service",
        "level",
        "event",
        "request_id",
    }
    for item in dashboard["templating"]["list"][:3]:
        assert item["allValue"] == ".+"
    panel_titles = {panel["title"] for panel in dashboard["panels"]}
    for title in (
        "Request completions",
        "Warnings",
        "4xx responses",
        "5xx responses",
        "Request completion rate",
        "Status and outcome distribution",
        "Request duration p50 / p95",
        "FastAPI dependency timing p95",
        "Recent failures and warnings",
        "Slow requests (>= 1 s)",
        "Correlated API / R request lookup",
        "Recent failed Supabase operations",
        "Supabase operation duration p50 / p95",
        "Slow Supabase operations (>= 500 ms)",
        "Raw structured logs",
    ):
        assert title in panel_titles

    expressions = "\n".join(
        target["expr"]
        for panel in dashboard["panels"]
        for target in panel.get("targets", [])
    )
    assert 'event="supabase_operation"' in expressions
    assert 'outcome="failed"' in expressions
    assert "by (operation)" in expressions
    assert "duration_ms >= 500" in expressions
    assert 'request_id="$request_id"' in expressions
