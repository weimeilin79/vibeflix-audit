"""Enable AGENT IDENTITY on every deployed vibeflix engine (cloud phase 2, step 3c).

Agent identity gives each Agent Runtime engine its OWN principal
(`principal://agents.global.org-…/…/reasoningEngines/<id>`) — the thing the
Agent Gateway policies and per-agent IAM bind to. It is an ENGINE CONFIG field
(v1beta1): set at create, or flipped on afterwards via update — this script does
the update so the engines can be deployed with the plain `adk deploy agent_engine`
CLI first.

    https://docs.cloud.google.com/gemini-enterprise-agent-platform/scale/runtime/agent-identity

Usage:
    PROJECT=pokedemo-test REGION=us-central1 python deploy/enable_agent_identity.py
    # or one engine:  … python deploy/enable_agent_identity.py vibeflix-legal

Prints each engine's effective identity principal and writes them all to
deploy/agent_identities.json for the gateway-policy step.
"""

import json
import os
import pathlib
import sys

import vertexai
from vertexai import types

PROJECT = os.environ.get("PROJECT") or os.environ.get("GOOGLE_CLOUD_PROJECT")
REGION = os.environ.get("REGION", "us-central1")
ONLY = sys.argv[1] if len(sys.argv) > 1 else None
assert PROJECT, "set PROJECT (or GOOGLE_CLOUD_PROJECT)"

# Agent identity is a v1beta1 surface.
client = vertexai.Client(project=PROJECT, location=REGION,
                         http_options=dict(api_version="v1beta1"))

identities: dict[str, dict] = {}
for engine in client.agent_engines.list():
    res = engine.api_resource
    if not res.display_name.startswith("vibeflix-"):
        continue
    if ONLY and res.display_name != ONLY:
        continue
    spec = getattr(res, "spec", None)
    principal = getattr(spec, "effective_identity", None) if spec else None
    if not principal:
        print(f"── enabling agent identity on {res.display_name}…")
        updated = client.agent_engines.update(
            name=res.name,
            config={"identity_type": types.IdentityType.AGENT_IDENTITY},
        )
        res = updated.api_resource
        principal = getattr(getattr(res, "spec", None), "effective_identity", None)
    print(f"{res.display_name}\n  engine:    {res.name}\n  principal: {principal}")
    identities[res.display_name] = {"engine": res.name, "principal": principal}

out = pathlib.Path(__file__).parent / "agent_identities.json"
out.write_text(json.dumps(identities, indent=2))
print(f"\nwrote {out} — bind gateway policies / IAM to these principals, e.g.:")
print("  gcloud run services add-iam-policy-binding <mcp-service> --region <region> \\")
print("    --member 'principal://…' --role roles/run.invoker")
