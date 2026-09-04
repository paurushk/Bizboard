# M1-030: digest-pinned; Dependabot's docker ecosystem bumps this as the tag moves.
FROM node:22-alpine@sha256:c610fcdfb1d5b4740dd70c284ed3cb16bb857e0f7166196e36a5501df7a3aa32 AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .

# BB-000344: bake Vite flags at build time (accounting off by default).
ARG VITE_ENABLE_ACCOUNTING=false
ARG VITE_ENABLE_AI=false
ARG VITE_ENABLE_TALLY=false
ARG VITE_ENABLE_GSTR=false
ARG VITE_ENABLE_EINVOICE_SUBMIT=false
ARG VITE_ENABLE_POS=false
ARG VITE_ENABLE_MANUFACTURING=false
ARG VITE_ENABLE_PAYROLL=false
ARG VITE_ENABLE_CRM=false
ARG VITE_SENTRY_DSN=
ARG VITE_API_BASE=
ARG VITE_API_BASE_URL=
ENV VITE_ENABLE_ACCOUNTING=$VITE_ENABLE_ACCOUNTING \
    VITE_ENABLE_AI=$VITE_ENABLE_AI \
    VITE_ENABLE_TALLY=$VITE_ENABLE_TALLY \
    VITE_ENABLE_GSTR=$VITE_ENABLE_GSTR \
    VITE_ENABLE_EINVOICE_SUBMIT=$VITE_ENABLE_EINVOICE_SUBMIT \
    VITE_ENABLE_POS=$VITE_ENABLE_POS \
    VITE_ENABLE_MANUFACTURING=$VITE_ENABLE_MANUFACTURING \
    VITE_ENABLE_PAYROLL=$VITE_ENABLE_PAYROLL \
    VITE_ENABLE_CRM=$VITE_ENABLE_CRM \
    VITE_SENTRY_DSN=$VITE_SENTRY_DSN \
    VITE_API_BASE=$VITE_API_BASE \
    VITE_API_BASE_URL=$VITE_API_BASE_URL

RUN if [ -z "$VITE_API_BASE_URL" ] && [ -n "$VITE_API_BASE" ]; then export VITE_API_BASE_URL="$VITE_API_BASE"; fi && npm run build

# M1-030: digest-pinned; Dependabot's docker ecosystem bumps this as the tag moves.
FROM nginx:1.27-alpine@sha256:65645c7bb6a0661892a8b03b89d0743208a18dd2f3f17a54ef4b76fb8e2f2a10
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
