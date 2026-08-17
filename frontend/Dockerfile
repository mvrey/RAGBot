# Multi-stage: deps -> build -> runtime, so the final image carries only the
# standalone server output, not the full node_modules / devDependencies tree.
FROM node:22-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci

FROM node:22-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
# NEXT_PUBLIC_* is baked in here, at build time - see .env.example.
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
RUN npm run build

FROM node:22-alpine AS runner
RUN addgroup --system ragbot && adduser --system --ingroup ragbot ragbot
WORKDIR /app

ENV NODE_ENV=production
COPY --from=builder /app/public ./public
COPY --from=builder --chown=ragbot:ragbot /app/.next/standalone ./
COPY --from=builder --chown=ragbot:ragbot /app/.next/static ./.next/static

USER ragbot
EXPOSE 3000
ENV PORT=3000 HOSTNAME=0.0.0.0

CMD ["node", "server.js"]
