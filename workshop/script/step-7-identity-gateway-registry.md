# Step 7 — Identity, Gateway & Registry

**Target runtime:** 14–17 min · **Lab section:** `Identity, Gateway & Registry`

---

## 00:00 — Cold open

[SCREEN: the finished mesh. Six agents, three tool servers, all green.]

Everything works. Six agents, three tool servers, a console, and a full audit end to end.

If one of those agents were compromised tomorrow, through a prompt injection buried in a vendor's document, what stops it calling the licensing server and writing itself a contract?

Its own IAM, which is coarse. IAM grants an agent reach to a whole server. It can't express that this agent may call one specific tool and nothing else.

---

## 01:00 — Governance in the traffic path

Most organisations have governance in a spreadsheet describing which system may talk to which, who approved it, and when it was reviewed. That spreadsheet describes an intention, and the gap between the intention and the running system is where incidents live.

We're building a component that requests physically travel through, which applies the rules and refuses anything outside them.

The test for your own systems: can you violate the policy without changing the policy? If you can, it's a document. If you can't, it's a guardrail.

---

## 02:00 — Three pieces

Agent Identity means every agent is its own principal with its own name, which makes an action attributable and makes least privilege possible. You've been building this since Step 2.

The Registry is the catalogue of what exists and where, covering every MCP server and agent. You registered the servers in Step 1.

The Gateway is the governed front door traffic goes through. It's deny-by-default and only routes to destinations in the registry.

Identity answers who is calling, the registry answers what may be called, and the gateway is where those two facts meet and a decision gets made. An unregistered destination is unreachable, so enrolment becomes enforcement.

---

## 03:30 — The policy map

[SCREEN: `deploy/policies.yaml`.]

Each agent is mapped to the exact tools it may invoke, so brand style may call the brand audit tool and deal pricing may call the pricing lookup.

The licensing server also exposes tools that change things: updating a vendor, writing a contract, resetting the store. Deal pricing has no business calling any of them, and under coarse IAM it could. Under per-tool policy the attempt is refused in the path and logged.

A compromised pricing agent can look up prices and has no route to writing a contract.

---

## 04:30 — Register, gate and grant

```bash
cd ~/vibeflix-audit
source ./env.sh
./deploy/setup_gateway.sh
```

[DO: run it.]

Four things in order. The six agents get registered, since the MCP servers already were. The governed front door gets created. The authorization extension gets attached, which makes the gateway consult policy per request. Then it calls the IAM script, which adds egress grants on top of the per-agent access from Steps 2 through 5.

Until now each agent's grants described what it may do. These describe where it may go.

---

## 05:45 — Attaching the engines

```bash
cd ~/vibeflix-audit
source ./env.sh
python deploy/deploy_agents_a2a.py
```

This is the one redeploy the workshop still requires.

The gateway didn't exist when you deployed these engines in Steps 2 through 5, and each deploy said so at the time. An engine's gateway attachment is part of its deployment spec, baked in when the engine is created.

In Step 6 the task-store URL turned out computable, so no second pass was needed. This one is a relationship to a thing that didn't exist yet.

Until this pass runs, the agents' egress is ungoverned, so this is where the guardrail goes into the path.

---

## 07:00 — Verify the wiring

```bash
cd ~/vibeflix-audit
source ./env.sh
./deploy/verify/step7.sh
```

Confirms the gateway exists, the six agents and three MCP servers are registered, and all six agents run under their own agent identity.

---

## 07:45 — Running it for real

A script confirms the wiring. A full audit through the deployed console demonstrates the mesh still works with governance in the path.

```bash
cd ~/vibeflix-audit
source ./env.sh
gcloud run services describe vibeflix-app --region "$REGION" --format 'value(status.url)'
```

[DO: open the console, pick the happy path, run it.]

Same scenario as Step 6, all of it in the cloud. The app calls the orchestrator engine over A2A, which fans out to three more engines, each authenticating as its own principal and reaching the MCP servers through the gateway.

The graph animates from events the engines publish over Pub/Sub. The tool LEDs fire, and each blink is a gateway decision that came back yes. And the run ends with a contract.

---

## 09:30 — What a failure looks like

[SCREEN: a branch failing — 403, egress request is not authorized.]

An agent reports a 403 saying egress is not authorized, its branch fails, and the others pass. Either the destination isn't registered, or that agent lacks the egress role on it.

This is the system working. Deny-by-default means a misconfiguration fails closed and you find out immediately. In an ungoverned system the same mistake produces no error, the call goes through, and you find out during an audit or a breach.

Re-applying the policies fixes it.

IAM and gateway changes take two to five minutes to propagate, so if the first run right after this step fails on egress, wait and run it again.

---

## 11:00 — The whole security story

[SCREEN: build the chain up, one layer at a time.]

In Step 1 the tool servers went up with no public access, and a browser still gets a 403 today.

In Steps 2 through 5 every agent got its own identity and its own narrow roles, with no shared service account. Because an agent identity can't authenticate to Cloud Run directly, each reaches the tool servers by impersonating an invoker service account, a relationship that can be granted and revoked.

In Step 6 the app got its own identity on the same basis.

In Step 7 a gateway went into the path, deny-by-default, applying per-tool policy, with destinations that must be registered to be reachable.

At every step we changed what is possible, so the allowlist is the running system.

---

## 12:30 — Do and don't

Give every agent its own identity, because a shared service account destroys attribution.

Apply the test: if you can violate a policy without editing it, it isn't a control.

Scope policy per tool rather than per server, since reaching a server and calling one read-only tool on it are very different blast radii.

Don't route around a gateway 403. Fix the policy or the registration.

Register everything you intend to be reachable, since under deny-by-default the registry is the allowlist.

Give a fresh gateway change five minutes before debugging it.

---

## 13:30 — Where that leaves us

Governance sits in the traffic path. Every hop is checked, every agent is attributable, and a misconfiguration fails immediately.

One step left, where we use the thing. Four scenarios that each end differently, driven entirely by data. Then three observability views, and teardown.

See you there.
