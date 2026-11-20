#!/usr/bin/env bash
# Creates one random token per environment.
#  - stores each token as a GitHub secret (DEPLOY_DEV_TOKEN, DEPLOY_STAGING_TOKEN, DEPLOY_PROD_TOKEN)
#  - stores each token locally in .env (git-ignored) for local testing
#  - writes only their SHA-256 hashes to mock_deploy/tokens.json (safe to commit)
set -euo pipefail
cd "$(dirname "$0")/.."
: > .env && chmod 600 .env
echo "{" > mock_deploy/tokens.json
first=1
for env in dev staging prod; do
  token="$(openssl rand -hex 24)"
  name="DEPLOY_$(echo "$env" | tr a-z A-Z)_TOKEN"
  printf '%s' "$token" | gh secret set "$name"
  echo "export $name=\"$token\"" >> .env
  hash="$(printf '%s' "$token" | sha256sum | cut -d' ' -f1)"
  [ $first -eq 1 ] || echo "," >> mock_deploy/tokens.json
  printf '  "%s": "%s"' "$env" "$hash" >> mock_deploy/tokens.json
  first=0
done
printf '\n}\n' >> mock_deploy/tokens.json
echo "Tokens created. GitHub secrets set, hashes in mock_deploy/tokens.json, local copies in .env"
