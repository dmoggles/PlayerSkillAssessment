FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
ARG APP_VERSION=local
ENV VITE_APP_VERSION=$APP_VERSION
# The site's address, for canonical links and link previews; only production lets search engines index it.
ARG SITE_URL=http://localhost:8080
ARG SITE_INDEXING=false
ENV SITE_URL=$SITE_URL SITE_INDEXING=$SITE_INDEXING
RUN npm run build

FROM nginx:1.31-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY security-headers.conf /etc/nginx/security-headers.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
