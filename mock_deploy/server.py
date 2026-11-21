"""Pretend deployment platform for the CI/CD lab.

Runs ONE environment (dev, staging or prod) as an HTTP MCP server, like the lesson's
https://deploy.example.com/mcp/<env>. Every environment offers the same three tools:

  release(version[, ticket])  -> release ID once the "rollout" finishes  (prod also needs a ticket)
  status()                    -> waits, then each endpoint's 5xx rate since the last release
  rollback()                  -> the version that is live again

Each server accepts only its own token (Authorization: Bearer ...). A wrong or missing
token gets HTTP 403 before any tool runs, so a job holding only the staging token cannot
even connect to dev or prod.

Usage:  python mock_deploy/server.py --env staging --port 8702
"""
import argparse
import hashlib
import json
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import uvicorn
from mcp.server.fastmcp import FastMCP
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

ROOT = Path(__file__).resolve().parent.parent
TOKENS_FILE = Path(__file__).resolve().parent / "tokens.json"   # SHA-256 hashes, never the tokens
PROFILE_FILE = ROOT / "app" / "service_profile.json"            # what a release of this commit "does" to errors
STATE_DIR = ROOT / ".deploy-state"
STATUS_WAIT_SECONDS = float(os.environ.get("STATUS_WAIT_SECONDS", "5"))  # lesson: 5 minutes; lab: 5 seconds

args_parser = argparse.ArgumentParser()
args_parser.add_argument("--env", required=True, choices=["dev", "staging", "prod"])
args_parser.add_argument("--port", type=int, required=True)
ARGS = args_parser.parse_args()
ENV = ARGS.env

STATE_DIR.mkdir(exist_ok=True)
STATE_FILE = STATE_DIR / f"{ENV}.json"
AUDIT_FILE = STATE_DIR / f"{ENV}-audit.log"


def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    # A fresh runner has no history. Seed a healthy "previous release" so the very first
    # release in a run still has something to roll back to - like a real platform would.
    return {"history": [{"version": "previous-release", "release_id": f"rel-{ENV}-baseline", "ticket": None,
                         "error_rates": {"/claims": 0.2, "/quotes": 0.1, "/payouts": 0.3}, "released_at": 0}]}


def save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2))


def audit(event: str, **details) -> None:
    line = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "env": ENV, "event": event,
            # actor = the identity that owns this environment's token (the agent's service account);
            # triggered_by = the human whose push or click started the run. Kept separate on purpose.
            "actor": f"svc-deploy-{ENV}" if event != "refused" else "unknown",
            "triggered_by": os.environ.get("GITHUB_ACTOR", os.environ.get("USER", "local")), **details}
    with AUDIT_FILE.open("a") as f:
        f.write(json.dumps(line) + "\n")


mcp = FastMCP(f"deploy-{ENV}", host="127.0.0.1", port=ARGS.port, stateless_http=True, json_response=True)


def _do_release(version: str, ticket: str | None) -> str:
    profile = json.loads(PROFILE_FILE.read_text())
    release_id = f"rel-{ENV}-{uuid.uuid4().hex[:8]}"
    time.sleep(1)  # the "rollout"
    state = load_state()
    state["history"].append({"version": version, "release_id": release_id, "ticket": ticket,
                             "error_rates": profile["error_rate_percent"], "released_at": time.time()})
    save_state(state)
    audit("release", version=version, release_id=release_id, ticket=ticket)
    return f"Release {release_id} finished: version {version} is live in {ENV}."


if ENV == "prod":
    @mcp.tool()
    def release(version: str, ticket: str) -> str:
        """Release a version to PRODUCTION. Requires the change ticket ID (e.g. CHG-1234). Returns the release ID once the rollout finishes."""
        return _do_release(version, ticket)
else:
    @mcp.tool()
    def release(version: str) -> str:
        """Release a version to this environment. Returns the release ID once the rollout finishes."""
        return _do_release(version, None)


@mcp.tool()
def status() -> str:
    """Wait until the observation window after the last release has passed, then return each endpoint's 5xx error rate (%) over that window."""
    state = load_state()
    if not state["history"]:
        return f"Nothing has been released to {ENV} yet."
    live = state["history"][-1]
    wait = live["released_at"] + STATUS_WAIT_SECONDS - time.time()
    if wait > 0:
        time.sleep(wait)
    rates = ", ".join(f"{ep}: {rate}%" for ep, rate in live["error_rates"].items())
    audit("status", version=live["version"])
    return f"{ENV} is running version {live['version']} ({live['release_id']}). 5xx rate per endpoint: {rates}"


@mcp.tool()
def rollback() -> str:
    """Roll back to the previous release. Returns the version that is live again."""
    state = load_state()
    if len(state["history"]) < 2:
        audit("rollback_refused", reason="no previous release")
        return f"Rollback refused: {ENV} has no previous release to return to."
    bad = state["history"].pop()
    state["history"][-1]["released_at"] = time.time()
    save_state(state)
    live = state["history"][-1]["version"]
    audit("rollback", from_version=bad["version"], to_version=live)
    return f"Rolled back {ENV} from {bad['version']} to {live}. Version {live} is live again."


class RequireEnvironmentToken(BaseHTTPMiddleware):
    """Refuse any request that doesn't carry THIS environment's token."""

    def __init__(self, app):
        super().__init__(app)
        self.expected = json.loads(TOKENS_FILE.read_text())[ENV]

    async def dispatch(self, request, call_next):
        header = request.headers.get("authorization", "")
        token = header.removeprefix("Bearer ").strip()
        if hashlib.sha256(token.encode()).hexdigest() != self.expected:
            audit("refused", reason="wrong or missing token", path=request.url.path)
            return JSONResponse({"error": f"403: this token is not valid for {ENV}"}, status_code=403)
        return await call_next(request)


if __name__ == "__main__":
    app = mcp.streamable_http_app()
    app.add_middleware(RequireEnvironmentToken)
    print(f"deploy-{ENV} listening on http://127.0.0.1:{ARGS.port}/mcp")
    uvicorn.run(app, host="127.0.0.1", port=ARGS.port, log_level="warning")
