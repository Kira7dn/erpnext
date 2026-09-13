FROM node:24-bookworm-slim

WORKDIR /app

ARG OPENCLAW_VERSION=2026.9.4
RUN npm install --global openclaw@${OPENCLAW_VERSION} \
    && npm cache clean --force

COPY entrypoint.mjs /app/entrypoint.mjs

ENV NODE_ENV=production
ENV OPENCLAW_HOME=/root/.openclaw

ENTRYPOINT ["node", "/app/entrypoint.mjs"]
