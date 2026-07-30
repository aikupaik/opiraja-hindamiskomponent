FROM node:24.13.1-alpine3.23 AS build

WORKDIR /build

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build

FROM nginx:1.28.3-alpine3.23

COPY nginx.conf /etc/nginx/nginx.conf
COPY --from=build --chown=nginx:nginx /build/dist /usr/share/nginx/html

USER nginx

EXPOSE 8080

STOPSIGNAL SIGQUIT

ENTRYPOINT ["nginx"]
CMD ["-g", "daemon off;"]
