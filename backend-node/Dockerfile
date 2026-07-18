# ── Stage 1: install deps + build ────────────────────────────────────────────
FROM node:22-slim AS build

WORKDIR /app

COPY package.json package-lock.json* .npmrc* ./
RUN npm install --legacy-peer-deps

COPY tsconfig.json ./
COPY src ./src
RUN npx tsc -p tsconfig.json

# ── Stage 2: production deps only ────────────────────────────────────────────
FROM node:22-slim AS deps

WORKDIR /app
COPY package.json package-lock.json* .npmrc* ./
RUN npm install --omit=dev --legacy-peer-deps

# ── Stage 3: runtime ──────────────────────────────────────────────────────────
FROM node:22-slim AS runtime

WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY --from=build /app/dist ./dist
COPY package.json ./

RUN useradd -r -u 1001 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

CMD ["node", "dist/index.js"]
