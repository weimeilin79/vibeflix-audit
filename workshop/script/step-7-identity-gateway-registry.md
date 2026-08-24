# Step 7 — Identity, Gateway & Registry

**Target runtime:** 28–32 min · **Lab section:** `Identity, Gateway & Registry`

> There's a companion explainer, `step-7-explainer-identity-in-plain-words.md`, that
> builds the office-building picture from scratch with no code. This script uses the
> same picture as an anchor and then goes to the mechanism.

---

## 00:00 — Cold open

[SCREEN: the finished mesh. Six agents, three tool servers, all green.]

Everything works. Six agents, three tool servers, a console, and a full audit end to end.

If one of those agents were compromised tomorrow, through a prompt injection buried in a vendor's document, what stops it calling the licensing server and writing itself a contract?

Its own IAM, which is coarse. IAM grants an agent reach to a whole server. It can't express that this agent may call one specific tool and nothing else.

To follow the rest of this step, hold one picture: an office building with a security desk at the door. Your agents are workers in it. The tool servers are other buildings across the street. Every idea from here is an object in that building.

---

## 01:15 — The badge, and where the name comes from

Each worker has a badge with their own name on it, and the badge is the agent's identity.

Open `agent_identities.json` and look at a principal.

```
principal://agents.global.org-<ORG>.system.id.goog/…/reasoningEngines/<ID>
```

That's a SPIFFE ID, a standard for naming a running workload with a URI the workload can prove is its own. The spec writes it `spiffe://` and Google's IAM renders it `principal://`.

Read it in three parts. `agents.global.org-<ORG>.system.id.goog` is the **trust domain**, scoped to your organization, so a badge issued in somebody else's org means nothing at your desk. Then the path down to `reasoningEngines/<ID>` names one engine.

The badge is a real document: an **X.509 certificate** with the SPIFFE ID in its subject-alternative-name field. The engine presents it during the TLS handshake, the far side verifies it against the trust domain, and the call proceeds as that agent's principal.

---

## 03:00 — One badge each

Before agent identity, workers shared a badge that said STAFF and lived in a drawer. That's a service account. When something goes wrong you can't tell which worker did it, and anyone who can reach the drawer becomes that worker.

In `deploy_agents_a2a.py` the engine is created with `identity_type: AGENT_IDENTITY`, and setting `service_account` on that same config returns a 400. You get one or the other, and there is no shared badge in a drawer behind the metadata server.

What you get instead is one principal per agent that starts with zero permissions, is attributable to one engine, and stops existing when that engine is deleted.

That last property explains the rule about never deleting an engine to redeploy it. Deleting the engine destroys the badge, which orphans every role you granted to that principal, and the redeployed engine comes back with a new name and none of its access.

---

## 04:30 — The building prints the badge

Workers don't print their own badges, and neither do you.

When an engine is created with agent identity, Agent Runtime provisions the certificate carrying that engine's SPIFFE ID. You don't generate it, store it or rotate it, and there's no key material in your repo.

You also can't bring your own badge printer. The principal, the trust domain and the certificate are all issued by the platform inside your organization's trust domain, so you can't point an agent identity at your own identity provider or your own certificate authority.

The Google auth library does the client half of this: it reads the certificate the platform provisioned, asks the metadata server for a token, and attaches the credential to outgoing calls. Any client speaking the same metadata protocol could do that work, so the library isn't the constraint. The issuer is.

---

## 06:00 — The day pass, and why it isn't shared

A badge says who you are. A day pass says you're allowed to do something today, and the machine inside the building gives out two kinds.

A **plain** day pass carries nothing but today's date. Anyone holding a copy of it can use it.

A **matched** day pass has your badge number printed on it. The door asks to see both, so a copy is useless to anyone who doesn't also hold your badge.

The matched pass is a certificate-bound token, and it's what an agent-identity engine gets from the metadata server. The request carries the certificate's fingerprint, and the token that comes back is tied to that certificate.

mTLS is how the badge gets onto the connection. Mutual TLS means both ends present certificates, so the engine's certificate is visible when the token arrives and the receiving service can check that the token it was handed was issued to the certificate it can see. Without the certificate on the connection there's nothing to check the binding against.

So the mTLS settings on an engine are part of how its credentials work. Leave them at their defaults.

---

## 08:00 — Two passes for one trip

[SCREEN: the two headers on an outbound MCP call.]

When a worker visits another building they carry two passes, and they're different documents.

The first is their **own day pass**, with their badge number on it, which says who this worker is. On the wire that's `Proxy-Authorization`, carrying the agent's own access token, and **the gateway reads it** to work out which agent is calling.

The second is a **visitor pass made out to one named building**, which says where they're going and works at that address and nowhere else. On the wire that's `Authorization`, carrying an ID token minted for the MCP server's specific URL, and **Cloud Run reads it**.

Each pass is for a different desk asking a different question. Your own desk asks whether this worker may leave for that destination. The far building's reception asks whether this visitor may come in. Neither can answer the other's question, which is why both headers are on the call.

For an A2A hop to a peer agent, the same access token appears in both headers, because the far end is another engine that verifies the agent identity directly rather than a Cloud Run service.

---

## 10:15 — A pass reception can read, and one they have to phone about

The visiting building's reception can be handed two kinds of pass.

One has to be phoned in. Reception rings head office to ask whether it's real, and waits. When several workers arrive at once the line gets busy and somebody gets turned away for no good reason. That's an access token, which Cloud Run verifies remotely through token introspection, and under a concurrent fan-out it surfaces as an intermittent 401 saying the token could not be verified.

The other can be read on the spot, because it carries a stamp reception already recognises and it names this specific building. That's an ID token, verified locally by checking the signature against Google's public keys and checking the audience matches the receiving service's own URL. Nothing has to be called, so nothing can flake.

One implementation note if you hit it. ADK's MCP session manager injects the agent's access token into `Authorization` itself, and skips doing that when the header is already set, so this codebase pre-sets the ID token through a header provider.

---

## 12:00 — The runner

There's a wrinkle in collecting that second pass. The readable pass is issued to holders of a shared STAFF badge, and our workers gave those up when they got personal badges.

So the worker sends a runner who does hold that kind of badge, and the worker has written permission to send that runner on errands.

In the system: an agent-identity engine has no service account behind the metadata server, so the normal ID-token call can't work. The engine mints its own access token, uses it to call the IAM credentials API, impersonates the MCP invoker service account, and gets the audience-bound ID token back from there.

That's why the grant in Step 2 included the token-creator role on that service account. Without it, a SPIFFE principal has no way to obtain a token Cloud Run accepts.

---

## 13:30 — One desk, both directions

[SCREEN: client → INGRESS → agent → EGRESS → MCP / APIs / peer agents.]

The security desk watches two directions, and it's one desk. The gateway is the same way: **one resource governs traffic coming in and traffic going out.**

**Ingress is Client-to-Agent.** It asks which clients may call your agents and what security policies apply to those calls. The client is something like Cursor, a CLI, or somebody's app.

**Egress is Agent-to-Anywhere.** It asks what this agent may reach and whether what it's sending is safe. The destinations are MCP servers, third-party APIs and peer agents.

Model Armor attaches to either direction with a template **per direction**. On ingress it evaluates the request going in and the response coming back. On egress it intercepts the outbound payload before it reaches an LLM, a third-party agent or an MCP server.

Vibeflix staffs the outward direction only. `deploy/agent-gateway.yaml` sets `governedAccessPath: AGENT_TO_ANYWHERE` and configures no Model Armor template, because the console calls the agents over A2A from its own app so there's no third-party client to gate. Opening these agents to external callers is when you'd staff the inward direction.

---

## 15:30 — Three questions on the way out

Every time a worker walks out, the desk asks three things in order, and each maps to a real check.

**Is that building on the list?** The desk keeps a list of buildings that can be visited, and that's the Agent Registry. A destination nobody registered can't be reached.

**Is this worker named for it?** Each agent is separately granted `roles/iap.egressor` on the entries it may reach.

**And which room?** The CEL condition on that grant names which tool this agent may call there.

All three read `Proxy-Authorization` to work out who's asking.

That third question is the one plain IAM can't ask. The licensing server also exposes tools that change things — updating a vendor, writing a contract, resetting the store — and a compromised pricing agent can look up prices while having no route to any of them.

At the far end the checks are different. Cloud Run checks the audience and the signature. A peer engine asks Google's token service whether the token is valid and resolves which principal is behind it. A Google API checks that the token was issued to the certificate on this connection and that the certificate is this engine's own.

---

## 17:00 — What a registry entry contains

The desk's list has more on it than addresses, and the difference between the two kinds of entry is what makes per-tool policy possible.

An **MCP server** registers with its tool spec. `setup_gateway.sh` generates that spec from the running server and passes it as `--mcp-server-spec-type=tool-spec`, so the registry entry lists every tool that server exposes. The gateway can name a tool in a policy because the registry already knows the tool exists.

An **agent** registers with `--endpoint-spec-type=no-spec` and an interface URL. That URL matters: it points at the **mTLS** aiplatform host, not the plain one. The gateway authorises the mTLS host and refuses the plain one, which is the same detail that forced this project to build its own agent cards back in Step 4.

Both kinds carry a protocol binding, JSONRPC, so the gateway knows what it's routing.

---

## 18:30 — Deny-by-default means everything

Here's the consequence that catches people, and it's the reason `grant_agent_iam.sh` registers more endpoints than you'd expect.

Once the gateway is in the path, an agent can only reach registered destinations. **That includes Google's own APIs.** The model call goes to aiplatform. The session writes go to the regional aiplatform mTLS host. And the runner's errand — the impersonation call that fetches the ID token — goes to iamcredentials.

None of those are your services, and all of them need registering as endpoints with the egress role granted, or the agent can't think, can't save a session, and can't obtain the pass it needs to reach an MCP server.

So the script registers both the plain and mTLS hosts for iamcredentials, the global aiplatform host, and the regional one. Which of those an agent uses depends on configuration — a global location setting sends the model call to the global host, and pinning to a region sends it to the regional one — so both get granted.

There's also **all-to-all A2A egress**: every agent principal is granted the egress role on every agent endpoint. The orchestrator calls three specialists and vendor clearance calls legal, and rather than maintaining that graph by hand the script grants the lot.

That brings a trap with it. An agent endpoint advertising the aiplatform host **shadows** the general aiplatform entry for every engine's own model call, so an engine holding no agent-endpoint grant can lose the ability to call Gemini for reasons that have nothing to do with agents calling agents.

---

## 20:30 — One honest note about the extension

The authorization extension is configured with `failOpen: true`.

If the extension itself becomes unavailable, traffic passes rather than stopping. That keeps a policy-engine outage from taking down every agent in the mesh, and it means the guardrail is not absolute — it's a control that degrades toward availability.

Worth knowing which way yours fails before you rely on it in an audit conversation.

---

## 21:30 — Register, gate and grant

```bash
cd ~/vibeflix-audit
source ./env.sh
./deploy/setup_gateway.sh
```

[DO: run it.]

Four things in order. The six agents get registered, since the MCP servers already were in Step 1. The gateway gets created. The authorization extension gets attached, which makes the gateway consult policy per request rather than just routing. Then it calls the IAM script, which adds the egress grants.

Until now each agent's grants described what it may do. These describe where it may go.

---

## 22:30 — Attaching the engines

```bash
cd ~/vibeflix-audit
source ./env.sh
python deploy/deploy_agents_a2a.py
```

This is the one redeploy the workshop still requires.

The gateway didn't exist when you deployed these engines in Steps 2 through 5, and each deploy said so at the time. An engine's gateway attachment is part of its deployment spec, baked in when the engine is created.

In Step 6 the task-store URL turned out to be computable, so no second pass was needed. This one is a relationship to a thing that didn't exist yet.

Until this pass runs, the agents' egress is ungoverned.

---

## 23:30 — Verify, then run it for real

```bash
cd ~/vibeflix-audit
source ./env.sh
./deploy/verify/step7.sh
```

Confirms the gateway exists, the six agents and three MCP servers are registered, and all six agents run under their own agent identity, with the `principal://` form in the output.

Then run a full audit through the deployed console, because a script confirms the wiring and only a real run shows the mesh still works with governance in the path.

[DO: open the console, pick the happy path, run it.]

Every tool LED that blinks is three gateway checks that came back yes.

---

## 24:45 — When somebody gets turned away

[SCREEN: a branch failing — 403, egress request is not authorized.]

An agent reports a 403 saying egress is not authorized, its branch fails, and the others pass. One of the three answers at the desk was no: the destination isn't registered, the agent isn't named for it, or the CEL condition excludes that tool.

Being refused is the desk doing its job. Deny-by-default means a misconfiguration fails closed and you find out immediately, where in an ungoverned system the same mistake produces no error, the call goes through, and you find out during an audit or a breach.

Re-applying the policies fixes it. IAM and gateway changes take two to five minutes to propagate, so if the first run right after this step fails on egress, wait and run it again.

Tell the two refusals apart. A 403 at your own desk on the way out is a permission problem. A 401 at the far end is a pass problem, so check the token rather than the registration.

---

## 26:00 — The whole security story

[SCREEN: build the chain up, one layer at a time.]

In Step 1 the tool servers went up with no public access, and a browser still gets a 403 today.

In Steps 2 through 5 every agent got its own badge — a SPIFFE principal proved by a platform-issued certificate — with its own narrow roles and no shared service account. Because that principal can't authenticate to Cloud Run directly, each agent sends a runner to fetch an audience-bound ID token.

In Step 6 the app got its own identity as an ordinary Cloud Run service account, since it isn't an engine.

In Step 7 a desk went in on the outward side, deny-by-default, asking three questions on every call.

At every step we changed what is possible, so the allowlist is the running system.

---

## 27:15 — Do and don't

Give every agent its own badge, because a shared service account destroys attribution and can be taken by anything it's attached to.

Leave the mTLS settings at their defaults, because a certificate-bound token needs the certificate on the connection.

Don't delete an engine to redeploy it, since the badge dies with it and takes every grant along.

Scope policy per tool rather than per server, because reaching a building and entering one room in it are very different blast radii.

Staff the inward direction as well if anything outside your own app will call these agents.

Don't route around a gateway 403. Fix the registration, the role, or the CEL condition.

---

## 28:15 — Where that leaves us

Every agent carries a badge only the platform can print, day passes that are useless to anyone else, and two passes on every trip for two different desks. The desk asks three questions before anyone leaves, and a misconfiguration fails closed.

One step left, where we use the thing. Four scenarios that each end differently, driven entirely by data. Then three observability views, and teardown.

See you there.
