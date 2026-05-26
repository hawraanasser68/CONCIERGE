# Owner D — widget container: build with pnpm, serve with nginx.
# Two stages so the final image is small (no node_modules).

# ── Stage 1: build ────────────────────────────────────────────────────────────
FROM node:20-alpine AS build

WORKDIR /app

RUN corepack enable

COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

COPY tsconfig.json vite.config.ts index.html ./
COPY src ./src
COPY public ./public

RUN pnpm build

# ── Stage 2: serve ────────────────────────────────────────────────────────────
FROM nginx:alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 3000

HEALTHCHECK --interval=10s --timeout=5s --retries=10 \
  CMD wget --spider -q http://localhost:3000/widget.js || exit 1
