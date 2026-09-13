FROM node:22-bookworm-slim

WORKDIR /app
COPY package.json ./
RUN npm install --omit=dev
COPY src ./src

USER node
EXPOSE 3010
CMD ["node", "src/index.mjs"]
