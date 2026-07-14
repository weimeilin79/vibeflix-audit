"""Collect every vibeflix engine's identity principal → deploy/agent_identities.json.

Template-deployed engines (deploy_agents_a2a.py) get AGENT_IDENTITY at create,
so nothing needs enabling — this just reads principals for step 4's grants
(grant_mcp_egress.sh, registry loops).

Usage: PROJECT=… REGION=… python deploy/collect_agent_identities.py
"""
import json, os, pathlib
import vertexai

PROJECT = os.environ.get("PROJECT") or os.environ.get("GOOGLE_CLOUD_PROJECT", "")
if not PROJECT:
    raise SystemExit(
        "✗ PROJECT / GOOGLE_CLOUD_PROJECT is not set. Refusing to guess.\n"
        "  This used to default to a hardcoded project, so forgetting to export it\n"
        "  silently pointed the script at SOMEONE ELSE'S project.\n"
        "  Run:  export PROJECT=<your-project> REGION=<your-region>")

REGION = os.environ.get("REGION", "us-central1")
client = vertexai.Client(project=PROJECT, location=REGION,
                         http_options=dict(api_version="v1beta1"))
out = {}
for e in client.agent_engines.list():
    r = e.api_resource
    if not (r.display_name or "").startswith("vibeflix-"):
        continue
    p = getattr(getattr(r, "spec", None), "effective_identity", None)
    out[r.display_name] = {"engine": r.name,
                           "principal": f"principal://{p}" if p else None}
    print(f"{r.display_name:28s} {'✓' if p else '⚠️ NO IDENTITY'}")
path = pathlib.Path(__file__).parent / "agent_identities.json"
path.write_text(json.dumps(out, indent=2))
print(f"wrote {path} ({len(out)} agents)")
