FROM python:3.14.6-slim-trixie

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt ./
RUN python -m pip install --no-cache-dir --disable-pip-version-check \
    -r requirements.txt

RUN groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app \
        --home-dir /nonexistent --shell /usr/sbin/nologin app

COPY --chown=app:app app ./app

USER app

EXPOSE 8000

STOPSIGNAL SIGTERM

CMD ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
