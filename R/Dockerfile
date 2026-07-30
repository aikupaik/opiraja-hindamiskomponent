FROM rocker/r-ver:4.6.1

ENV DEBIAN_FRONTEND=noninteractive \
    RENV_CONFIG_AUTOLOADER_ENABLED=false \
    RENV_PATHS_CACHE=/opt/renv/cache \
    RENV_PATHS_LIBRARY=/opt/renv/library

RUN apt-get update \
    && apt-get install --yes --no-install-recommends \
        build-essential \
        libcurl4-openssl-dev \
        libglpk-dev \
        libicu-dev \
        librsvg2-dev \
        libsodium-dev \
        libssl-dev \
        libuv1-dev \
        libxml2-dev \
        zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN R --vanilla -e \
    "install.packages('https://cloud.r-project.org/src/contrib/renv_1.2.3.tar.gz', repos = NULL, type = 'source')"

COPY renv.lock DESCRIPTION ./
COPY renv ./renv

RUN R --vanilla -e "renv::restore(project = '/app', prompt = FALSE)"

COPY plumber.R ./
COPY config ./config
COPY src ./src

RUN groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app \
        --home-dir /nonexistent --shell /usr/sbin/nologin app \
    && chown -R app:app /app /opt/renv

USER app

EXPOSE 8000

STOPSIGNAL SIGTERM

CMD ["Rscript", "--vanilla", "-e", "source('renv/activate.R'); router <- source('plumber.R')$value; plumber::pr_run(router, host = '0.0.0.0', port = 8000, quiet = TRUE)"]
