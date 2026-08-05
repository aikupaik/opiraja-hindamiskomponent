FROM node:24.13.1-alpine3.23 AS build

WORKDIR /build/admin

COPY shared/frontend-api /build/shared/frontend-api
COPY admin/package.json admin/package-lock.json ./
RUN npm ci

COPY admin/ ./
RUN npm run build

FROM nginx:1.28.3-alpine3.23

COPY admin/nginx.conf /etc/nginx/nginx.conf
COPY --from=build --chown=nginx:nginx /build/admin/dist /usr/share/nginx/html

RUN nginx -t -c /etc/nginx/nginx.conf

USER nginx

EXPOSE 8080

STOPSIGNAL SIGQUIT

ENTRYPOINT ["nginx"]
CMD ["-g", "daemon off;"]
