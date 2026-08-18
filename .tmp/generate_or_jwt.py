#!/usr/bin/env python3
"""Print a test OR-service JWT using the repository's .env settings."""

from __future__ import annotations

import time
from pathlib import Path

import jwt


def _dotenv_value(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    if " #" in value:
        return value.split(" #", maxsplit=1)[0].rstrip()
    return value


def _load_dotenv(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line_number, raw_line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        name, separator, raw_value = line.partition("=")
        if not separator or not name.strip():
            raise SystemExit(f"Invalid .env entry on line {line_number}.")
        values[name.strip()] = _dotenv_value(raw_value)
    return values


def main() -> None:
    dotenv_path = Path(__file__).resolve().parents[1] / ".env"
    if not dotenv_path.is_file():
        raise SystemExit(f"Missing environment file: {dotenv_path}")

    values = _load_dotenv(dotenv_path)
    secret = values.get("OR_JWT_SECRET", "")
    issuer = values.get("OR_JWT_ISSUER", "")
    if len(secret) < 32:
        raise SystemExit("OR_JWT_SECRET must contain at least 32 characters.")
    if not issuer.strip():
        raise SystemExit("OR_JWT_ISSUER is required.")

    lifetime_text = values.get("OR_JWT_MAX_LIFETIME_SECONDS", "300")
    try:
        lifetime = int(lifetime_text)
    except ValueError as error:
        raise SystemExit("OR_JWT_MAX_LIFETIME_SECONDS must be an integer.") from error
    if lifetime <= 0:
        raise SystemExit("OR_JWT_MAX_LIFETIME_SECONDS must be positive.")

    issued_at = int(time.time())
    token = jwt.encode(
        {
            "iss": issuer,
            "aud": "assessment-api",
            "sub": "or-service-example",
            "scope": "tests:create tests:read tests:launch",
            "iat": issued_at,
            "exp": issued_at + lifetime,
        },
        secret,
        algorithm="HS256",
    )
    print(token)


if __name__ == "__main__":
    main()
