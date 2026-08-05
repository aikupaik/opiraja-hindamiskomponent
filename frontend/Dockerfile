FROM node:24.13.1-alpine3.23 AS build

WORKDIR /build/frontend

COPY shared/frontend-api /build/shared/frontend-api
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build

FROM nginx:1.28.3-alpine3.23

COPY frontend/nginx.conf /etc/nginx/nginx.conf
COPY --from=build --chown=nginx:nginx /build/frontend/dist /usr/share/nginx/html

RUN nginx -t -c /etc/nginx/nginx.conf

USER nginx

EXPOSE 8080

STOPSIGNAL SIGQUIT

ENTRYPOINT ["nginx"]
CMD ["-g", "daemon off;"]
