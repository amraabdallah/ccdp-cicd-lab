#!/usr/bin/env bash
# Starts the pretend deployment platform: one server per environment.
# The platform always runs; what a job can reach depends only on the token it holds.
cd "$(dirname "$0")/.."
mkdir -p .deploy-state
python mock_deploy/server.py --env dev     --port 8701 > .deploy-state/dev-server.log     2>&1 &
python mock_deploy/server.py --env staging --port 8702 > .deploy-state/staging-server.log 2>&1 &
python mock_deploy/server.py --env prod    --port 8703 > .deploy-state/prod-server.log    2>&1 &
sleep 3
echo "deploy-dev :8701  deploy-staging :8702  deploy-prod :8703"
