"""Enable AGENT IDENTITY and A2A ROUTING on every deployed vibeflix engine.

This script updates each deployed Reasoning Engine to:
1. Set the identity type to AGENT_IDENTITY (step 3c).
2. Set the framework type to "a2a" so it natively speaks the A2A protocol.
3. Automatically generate the agent card from the local python code and embed it into the registered A2A class methods.

It uses direct REST API calls to bypass Python SDK pydantic validation constraints.

Usage:
    PROJECT=<your-project> REGION=us-central1 python deploy/enable_agent_identity_and_a2a.py
    # or for a single engine:
    PROJECT=<your-project> REGION=us-central1 python deploy/enable_agent_identity_and_a2a.py vibeflix-brand-style
"""

import asyncio
import json
import os
import pathlib
import sys
import urllib.request
import urllib.error

# Add workspace root to sys.path so the agents package can be imported
sys.path.append(str(pathlib.Path(__file__).parent.parent.resolve()))

# Set up dummy environment variables for imports to avoid failures
os.environ["MCP_BRAND_STYLE_URL"] = "http://localhost:9001/mcp"
os.environ["MCP_LICENSING_URL"] = "http://localhost:9001/mcp"
os.environ["MCP_MARKET_URL"] = "http://localhost:9001/mcp"
os.environ["LEGAL_A2A_URL"] = "http://localhost:8005"
os.environ["RAG_CORPUS"] = "projects/mock-project/locations/us-central1/ragCorpora/mock-corpus"

import vertexai
from google.adk.a2a.utils.agent_card_builder import AgentCardBuilder
from a2a.types import AgentCapabilities
import google.auth
import google.auth.transport.requests

PROJECT = os.environ.get("PROJECT") or os.environ.get("GOOGLE_CLOUD_PROJECT")
REGION = os.environ.get("REGION", "us-central1")
ONLY = sys.argv[1] if len(sys.argv) > 1 else None

assert PROJECT, "set PROJECT (or GOOGLE_CLOUD_PROJECT)"

# Get OAuth token
credentials, project = google.auth.default()
auth_req = google.auth.transport.requests.Request()
credentials.refresh(auth_req)
token = credentials.token

client = vertexai.Client(project=PROJECT, location=REGION,
                         http_options=dict(api_version="v1beta1"))

identities: dict[str, dict] = {}
for engine in client.agent_engines.list():
    res = engine.api_resource
    if not (res.display_name or "").startswith("vibeflix-"):
        continue
    if ONLY and res.display_name != ONLY:
        continue

    print(f"\n── Configuring A2A and Identity on {res.display_name}...")
    
    # 1. Resolve agent app name
    app_name = res.display_name.removeprefix("vibeflix-").replace("-", "_")
    
    # 2. Import agent and build card
    try:
        import importlib
        mod = importlib.import_module(f"agents.{app_name}.agent")
        root_agent = mod.root_agent
    except Exception as e:
        print(f"   ⚠️  Failed to import agent module agents.{app_name}.agent: {e}")
        continue
        
    rpc_url = f"https://{REGION}-aiplatform.googleapis.com/v1beta1/{res.name}/a2a"
    capabilities = AgentCapabilities(streaming=True, extended_agent_card=True)
    builder = AgentCardBuilder(agent=root_agent, rpc_url=rpc_url, capabilities=capabilities)
    
    try:
        card = asyncio.run(builder.build())
        card_json = card.model_dump_json()
    except Exception as e:
        print(f"   ⚠️  Failed to build agent card: {e}")
        continue

    # 3. Read current class methods and append/overwrite A2A ones
    current_methods = getattr(res.spec, "class_methods", []) or []
    
    # Clean out any old A2A extension methods
    updated_methods = []
    for m in current_methods:
        if m.get("api_mode") == "a2a_extension":
            continue
        updated_methods.append(m)
    
    # Add A2A methods with the embedded card
    a2a_methods = [
        "on_message_send",
        "on_get_task",
        "on_list_tasks",
        "on_cancel_task",
        "on_message_send_stream",
        "on_subscribe_to_task",
    ]
    for m_name in a2a_methods:
        updated_methods.append({
            "name": m_name,
            "api_mode": "a2a_extension",
            "a2a_agent_card": card_json,
        })
        
    # 4. Make direct REST PATCH call to update the config on Vertex AI
    # We must clear spec.service_account when setting identity_type to AGENT_IDENTITY
    url = f"https://{REGION}-aiplatform.googleapis.com/v1beta1/{res.name}?updateMask=spec.identityType,spec.agentFramework,spec.classMethods,spec.serviceAccount"
    
    payload = {
        "spec": {
            "identity_type": "AGENT_IDENTITY",
            "agent_framework": "a2a",
            "class_methods": updated_methods,
            "service_account": None,
        }
    }
    
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="PATCH",
    )
    
    try:
        with urllib.request.urlopen(req) as response:
            resp_data = json.loads(response.read().decode("utf-8"))
            
        op_name = resp_data.get("name")
        if op_name:
            import time
            print("   Waiting for update operation to complete...", end="", flush=True)
            op_url = f"https://{REGION}-aiplatform.googleapis.com/v1beta1/{op_name}"
            op_req = urllib.request.Request(
                op_url,
                headers={"Authorization": f"Bearer {token}"},
            )
            while True:
                with urllib.request.urlopen(op_req) as op_response:
                    op_data = json.loads(op_response.read().decode("utf-8"))
                if op_data.get("done"):
                    if "error" in op_data:
                        print(f"\n   ⚠️ Operation failed: {op_data['error']}")
                    else:
                        print("\n   → Operation completed successfully!")
                    break
                print(".", end="", flush=True)
                time.sleep(3)
            
        # Re-fetch the resource to confirm
        confirm_engine = client.agent_engines.get(name=res.name)
        confirm_res = confirm_engine.api_resource
        spec = getattr(confirm_res, "spec", None)
        principal = getattr(spec, "effective_identity", None) if spec else None
        
        print(f"   Identity: {principal}")
        print(f"   Framework: {getattr(spec, 'agent_framework', None)}")
        print(f"   A2A methods successfully exposed.")
        
        identities[res.display_name] = {"engine": res.name, "principal": principal}
    except urllib.error.HTTPError as e:
        print(f"\n   ⚠️  Failed REST update: HTTP {e.code} - {e.read().decode('utf-8')}")
    except Exception as e:
        print(f"\n   ⚠️  Failed to update Reasoning Engine spec: {e}")

out = pathlib.Path(__file__).parent / "agent_identities.json"
out.write_text(json.dumps(identities, indent=2))
print(f"\nWrote identities list to {out}")
