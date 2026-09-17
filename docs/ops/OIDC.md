# GitHub OIDC (14.3)

CD today logs into GHCR with `GITHUB_TOKEN` (packages: write). Cloud deploys (AWS/GCP/Azure) should use **OIDC**, not long-lived keys in GitHub secrets.

Skeleton (Human creates the cloud role):

```yaml
permissions:
  id-token: write
  contents: read
steps:
  - uses: aws-actions/configure-aws-credentials@v4
    with:
      role-to-assume: arn:aws:iam::...:role/bizboard-cd
      aws-region: ap-south-1
```

Do not put `AWS_SECRET_ACCESS_KEY` in the repo. Example env files stay placeholders (`*example*` allowlisted in gitleaks).
