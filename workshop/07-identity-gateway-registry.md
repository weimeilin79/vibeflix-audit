# Step 7 — Identity, Gateway & Registry

The mesh works, and each agent already has its **own identity** with **its own least-privilege
IAM** (you granted that per agent in Steps 2–5), and the MCP servers are in the **registry**
(Step 1). What's still missing is the **governed gateway** in the path. This step adds it — and it
registers the *agents* as destinations too. This is the part of the demo that's *the point*: the
governance becomes real, in the path of every hop.

## 💡 Concept — three pieces of the security model

**1. Agent Identity — every agent is its own principal.**
No shared service account stands in for the mesh. Each engine runs *as*
`principal://…/reasoningEngines/<id>` — a first-class identity, enabled at deploy time. In Steps
2–5 you granted each one its least-privilege **IAM** with `grant_agent_access.sh` — keyed to that
agent's own principal, one agent at a time.

> ⚠️ The engine id is baked into the principal. **Never delete an engine** and recreate it — the
> new id means a new principal, and every grant is orphaned onto a dead one. Always *update in
> place*.

**2. Agent Registry — the list of who can be called.**
Every MCP server and every agent is registered as a **destination**, and an **unregistered
destination is blocked**. You registered the **MCP servers** in Step 1; this step registers the
**6 agents** too — the gateway's policies and A2A egress grants key off these entries.

**3. Agent Gateway — one governed front door, deny-by-default.**
Agents can't reach the open internet or each other freely. A governed gateway sits in the path,
and an agent may only reach a destination it's been **explicitly granted**. On top of that,
per-tool **IAP authz policies** (CEL conditions on tool attributes, in `deploy/policies.yaml`)
decide *which tools* each agent may call — not just which servers.

Together: **least privilege, enforced by the platform, not by convention.**

## 📝 Look — the policy map

Open `deploy/policies.yaml` — it maps each agent to the exact tools it's allowed to invoke (e.g.
`brand_style` → `run_brand_audit`; `deal_pricing` → `get_license_pricing`). That's the difference
between "this agent can reach the licensing server" and "this agent can call *only*
`get_license_pricing` on it."

`deploy/setup_gateway.sh` reads this and builds, in order: **registry** (registers the 6 agents;
the MCP servers were already registered in Step 1) → **gateway** (the governed front door) →
**policies** (the IAP authz extension) → and finally calls **`grant_agent_iam.sh`**, which adds
the **gateway egress grants** (`roles/iap.egressor` on each allowed destination) on top of the
per-agent access you granted in Steps 2–5.

## 💻 Run — register, gate, and grant

```bash
./deploy/setup_gateway.sh
```

One command runs all four sub-steps. It uses **preview** gcloud surfaces, so if a step reports a
spelling drift, re-run just that phase — `./deploy/setup_gateway.sh registry` / `gateway` /
`policies`.

> ⏱️ IAM and gateway changes take **2–5 minutes** to propagate. If a call is still denied right
> after, wait before assuming it's broken.

## 👀 Verify

```bash
./deploy/verify/step7.sh
```

It confirms the **gateway exists**, the **6 agents + 3 MCP servers are registered**, and **all six
agents run under their own agent identity** (`principal://`).

## 💡 What you learned

- **Agent Identity** makes every agent its own principal — attributable, least-privilege, never
  a shared SA.
- **Agent Registry** declares callable destinations; unregistered ones are blocked.
- **Agent Gateway** enforces deny-by-default egress plus **per-tool** policies — the governance is
  genuinely in the path, which is the whole demonstration.

**Next:** [Step 8 — Run the Flows, Observability & Wrap-up →](./08-run-observability-wrap.md)
