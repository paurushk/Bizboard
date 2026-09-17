# Recreate from SHA (2.3 / 14.4)

CD already pushes `ghcr.io/<org>/bizboard-api:<git-sha>` after CI on `main`.

```
# 1. CI green on SHA
# 2. CD push-images (automatic on main, or workflow_dispatch with confirm_ci_green=yes)
# 3. Pin digests
./scripts/pin_image_digests.sh \
  ghcr.io/<org>/bizboard-api:<sha> \
  ghcr.io/<org>/bizboard-web:<sha> \
  docker-compose.digest.yml
# 4. On the host
export BIZBOARD_API_IMAGE=ghcr.io/<org>/bizboard-api@sha256:...
export BIZBOARD_WEB_IMAGE=ghcr.io/<org>/bizboard-web@sha256:...
docker compose -f docker-compose.yml -f docker-compose.prod.yml \
  --profile migrate run --rm migrate
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

Rollback overlay: `docker-compose.rollback.yml` + previous digest env vars.  
GitHub OIDC to a cloud account is Human (`docs/ops/OIDC.md`).
