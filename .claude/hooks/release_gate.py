#!/usr/bin/env python3
"""PreToolUse hook: the per-environment gate on every deploy `release` tool.

Claude Code runs this BEFORE any call matching mcp__deploy-*__release, passes the call
as JSON on stdin, and reads our decision from stdout:

  dev      -> allow
  staging  -> allow from the pipeline on main, otherwise ask
  prod     -> allow ONLY if the change ticket (CHG-<issue number>) is an open issue that a
              named release manager labelled `approved-change`; otherwise deny

Fails closed: if this script crashes, Claude Code treats it as a non-blocking error and
falls back to normal permissions. In production `release` is NOT on the allowlist and the
job runs with --permission-mode dontAsk, so the fallback is a denial.
"""
import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

LOG = Path(os.environ.get("CLAUDE_PROJECT_DIR", ".")) / ".deploy-state" / "gate.log"
APPROVAL_LABEL = "approved-change"


def decide(decision: str, reason: str, env: str, tool_input: dict) -> None:
    LOG.parent.mkdir(exist_ok=True)
    with LOG.open("a") as f:
        f.write(json.dumps({"at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                            "env": env, "decision": decision, "reason": reason, "input": tool_input}) + "\n")
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                             "permissionDecision": decision,
                                             "permissionDecisionReason": reason}}))
    sys.exit(0)


def github(path: str):
    req = urllib.request.Request(f"https://api.github.com/repos/{os.environ['GITHUB_REPOSITORY']}{path}",
                                 headers={"Authorization": f"Bearer {os.environ['GH_TOKEN']}",
                                          "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.load(r)


call = json.load(sys.stdin)
tool_input = call.get("tool_input", {})
env = call["tool_name"].split("__")[1].removeprefix("deploy-")   # mcp__deploy-prod__release -> prod

if os.environ.get("SIMULATE_GATE_CRASH") == "1":
    raise RuntimeError("simulated hook crash")                     # lab switch: prove it fails closed

if env == "dev":
    decide("allow", "dev: agent deploys freely", env, tool_input)

if env == "staging":
    if os.environ.get("GITHUB_ACTIONS") == "true" and os.environ.get("GITHUB_REF") == "refs/heads/main":
        decide("allow", "staging: pipeline run on main (the approved merge)", env, tool_input)
    decide("ask", "staging: outside the pipeline on main, an engineer must confirm", env, tool_input)

if env == "prod":
    ticket = str(tool_input.get("ticket", ""))
    m = re.fullmatch(r"CHG-(\d+)", ticket)
    if not m:
        decide("deny", f"prod: '{ticket}' is not a change ticket (expected CHG-<issue number>)", env, tool_input)
    number = m.group(1)
    managers = {u.strip() for u in os.environ.get("RELEASE_MANAGERS", "").split(",") if u.strip()}
    if not managers:
        decide("deny", "prod: no release managers configured", env, tool_input)
    issue = github(f"/issues/{number}")
    if issue["state"] != "open":
        decide("deny", f"prod: {ticket} is closed", env, tool_input)
    if APPROVAL_LABEL not in {l["name"] for l in issue["labels"]}:
        decide("deny", f"prod: {ticket} has no '{APPROVAL_LABEL}' label", env, tool_input)
    labelled_by = [e["actor"]["login"] for e in github(f"/issues/{number}/events?per_page=100")
                   if e["event"] == "labeled" and e["label"]["name"] == APPROVAL_LABEL]
    if not labelled_by or labelled_by[-1] not in managers:
        decide("deny", f"prod: '{APPROVAL_LABEL}' on {ticket} was not added by a release manager", env, tool_input)
    decide("allow", f"prod: {ticket} approved by release manager {labelled_by[-1]}", env, tool_input)

decide("deny", f"unknown environment '{env}'", env, tool_input)
