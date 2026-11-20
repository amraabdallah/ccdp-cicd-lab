# CCD-P CI/CD lab

Hands-on version of the lesson "CI/CD integration and deployment".

| Stage | What it shows | Status |
|---|---|---|
| 1 | Read-only judgment step: Claude triages a failed build (`ci.yml`) | done |
| 2 | Write step behind the gate: `@claude` fixes a bug via a PR; ruleset protects `main` (`claude.yml`) | done |
| 3 | Pretend deploy servers (dev / staging / prod) exposed through MCP, one token each | in progress |
| 4 | Staging job: `dontAsk` + `--allowedTools` + only the staging token | |
| 5 | PreToolUse hook as the production gate (fails closed) | |
| 6 | Rollback drill | |
| 7 | Bonus: replace the stored API key with identity federation | |

## Pretend deployment platform (`mock_deploy/`)

| Server | Port | Token secret |
|---|---|---|
| deploy-dev | 8701 | `DEPLOY_DEV_TOKEN` |
| deploy-staging | 8702 | `DEPLOY_STAGING_TOKEN` |
| deploy-prod | 8703 | `DEPLOY_PROD_TOKEN` |

Each offers `release`, `status`, `rollback`. A wrong or missing token gets HTTP 403.
`app/service_profile.json` sets the 5xx rate a release "produces" — raise one above 1% to simulate a bad release.
Every action is written to `.deploy-state/<env>-audit.log`.
