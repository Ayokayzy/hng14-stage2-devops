# syntax=docker/dockerfile:1
FROM node:20-bookworm-slim AS deps

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --omit=dev \
    && npm cache clean --force

FROM node:20-bookworm-slim AS runtime

WORKDIR /app
ENV NODE_ENV=production \
    PORT=3000 \
    HOST=0.0.0.0

RUN useradd --create-home --shell /usr/sbin/nologin appuser

COPY --from=deps /app/node_modules ./node_modules
COPY --chown=appuser:appuser package.json app.js ./
COPY --chown=appuser:appuser views ./views

USER appuser

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD node -e "const p=process.env.PORT||3000;require('http').get('http://127.0.0.1:'+p,(r)=>{process.exit(r.statusCode===200?0:1)}).on('error',()=>process.exit(1))"

CMD ["node", "app.js"]
