"""Production Uvicorn entry point with structured logging."""

import os

import uvicorn

from app.logging_config import build_logging_config


def main() -> None:
    """Run the API with the same process settings as the container command."""

    log_level = os.environ.get("APP_LOG_LEVEL", "INFO").upper()
    uvicorn.run(
        "app.main:create_app",
        factory=True,
        host="0.0.0.0",
        port=8000,
        workers=1,
        proxy_headers=True,
        access_log=False,
        log_config=build_logging_config(log_level),
    )


if __name__ == "__main__":
    main()
