# Step 7 — Identity, Gateway & Registry

**Target runtime:** 30–34 min · **Lab section:** `Identity, Gateway & Registry`

> There's a companion explainer, `step-7-explainer-identity-in-plain-words.md`, that
> builds the office-building picture from scratch with no code. This script uses the
> same picture as an anchor and then goes to the mechanism.

---

## 00:00 — Cold open

[SCREEN: the finished mesh. Six agents, three tool servers, all green.]

Everything works. Six agents, three tool servers, a console, and a full audit end to end.

So here's the question this step exists to answer. If one of those agents were compromised tomorrow, through a prompt injection buried in a vendor's document, what stops it calling the licensing server and writing itself a contract?

Quite a lot is already stopping it, and has been since Step 2. We'll walk through what's guarding the mesh right now, find the one call where that guard goes blind, and build for that.

One picture will carry you through the whole step. Think of an office building with a security desk at the door. Your agents are the workers inside it, and the tool servers are other buildings across the street.

---

## 01:00 — The badge, and where the name comes from

Each worker has a badge with their own name on it. That badge is the agent's identity.

Open `agent_identities.json` and look at a principal.

```
principal://agents.global.org-<ORG>.system.id.goog/…/reasoningEngines/<ID>
```

That's a SPIFFE ID, a standard for naming a running workload with a URI the workload can prove is its own. The spec writes it `spiffe://` and Google's IAM renders it `principal://`.

Read it in three parts. `agents.global.org-<ORG>.system.id.goog` is the **trust domain**, scoped to your organization, so a badge issued in somebody else's org means nothing at your desk. Then the path down to `reasoningEngines/<ID>` names one engine.

The badge is a real document. It's an **X.509 certificate** with the SPIFFE ID in its subject-alternative-name field. The engine presents it during the TLS handshake, the far side verifies it against the trust domain, and the call proceeds as that agent's principal.

---

## 02:30 — One badge each

Before agent identity, workers shared a badge that said STAFF and lived in a drawer. That's a service account. When something goes wrong you can't tell which worker did it, and anyone who can reach the drawer becomes that worker.

In `deploy_agents_a2a.py` the engine is created with `identity_type: AGENT_IDENTITY`. The agent identity already serves as that engine's workload identity, so a config that also names a `service_account` fails with a 400. The drawer is empty. No shared badge sits behind the metadata server.

What you get is one principal per agent that starts with zero permissions, is attributable to one engine, and stops existing when that engine is deleted.

That last property explains the rule about never deleting an engine to redeploy it. Deleting the engine destroys the badge, which orphans every role you granted to that principal, and the redeployed engine comes back with a new name and none of its access.

---

## 03:45 — The building prints the badge

Nobody in the building prints their own badge, and neither do you.

When an engine is created with agent identity, Agent Runtime issues the certificate and puts that engine's SPIFFE ID on it. There's nothing for you to create, save or renew.

That's what makes the badge worth anything. An agent can show its badge and it has no way to make one up, or to change what's printed on it. So when `brand_style` turns up at Firestore, Firestore knows it's `brand_style`, and no other agent can walk up claiming to be it.

You can't bring your own printer either. The principal, the trust domain and the certificate all come from the platform, inside your organization's trust domain, so an agent identity can't be pointed at your own identity provider or your own certificate authority.

The Google auth library handles the worker's side. It reads the certificate, asks the metadata server for a token, and puts that token on outgoing calls.

---

## 05:15 — Who is checking all this today

[SCREEN: brand_style → aiplatform.googleapis.com, with the IAM binding beside it.]

**Every one of those badges is already being checked, on every call, and there's no gateway in your project yet.**

Follow `brand_style` asking Gemini to look at a mock-up. The request goes to `aiplatform.googleapis.com` carrying a short-lived credential Google issued to that engine, naming that engine's principal. Google's API front end resolves the credential, reads your project's IAM policy, finds the `roles/aiplatform.user` binding you made in Step 2 for exactly that principal, and lets the call through.

Firestore is the same. Pub/Sub is the same. An A2A hop to a peer engine is the same. **The destination does the checking**, using the grants you already made.

And notice where the configuration for that lives. There's none in Firestore and none in Pub/Sub. You never told those services what an agent identity is. Every `*.googleapis.com` endpoint sits behind the same front end, which authenticates the caller and applies IAM, and a SPIFFE principal is simply another member type in a policy, sitting alongside `user:` and `serviceAccount:`. The whole of your setup was one line per role in `grant_agent_access.sh`:

```bash
gcloud projects add-iam-policy-binding "$PROJECT" --member="$PRINCIPAL" --role="$R"
```

So least privilege has been live since Step 2. Six agents, six sets of grants, enforced by whatever they call.

So that's what's already in place. Now let's find the one call it doesn't cover.

---

## 08:00 — The trip where the name changes

[SCREEN: agent → iamcredentials → invoker SA → Cloud Run MCP server.]

Follow a tool call to an MCP server and something different happens.

Those servers are Cloud Run services, closed to unauthenticated traffic, and Cloud Run asks for an **audience-bound ID token** naming its own URL. Minting one of those needs a service account. Our workers gave up the shared badge to get personal ones, so they have no service account behind them.

So the worker sends a runner. The engine mints its own access token, uses that to call the IAM credentials API, impersonates `vibeflix-mcp-invoker`, and receives an audience-bound ID token issued to that account. The token-creator role you granted back in Step 2 is what authorises the errand.

The call then succeeds. `roles/run.invoker` belongs to the invoker service account, the token checks out, the server answers.

But look at who arrived. All six agents send the same runner, so all six arrive wearing the same badge. Cloud Run can answer *"may this caller reach this service?"*, and it answers that well. The questions **which agent is asking** and **which tool it wants** never travel with the request at all.

---

## 10:00 — Two passes for one trip

[SCREEN: the two headers on an outbound MCP call.]

The agent's own name does survive that trip, on a different piece of paper.

When a worker visits another building they carry two passes.

The first is their **own day pass**, with their badge number on it. On the wire that's `Proxy-Authorization`, carrying the agent's own access token, and **your desk reads it** on the way out.

The second is a **visitor pass made out to one named building**. On the wire that's `Authorization`, carrying the ID token the runner fetched, and **Cloud Run reads it** on arrival.

Each pass answers a different desk's question. Yours asks whether this worker may leave for that destination. Reception across the street asks whether this visitor may come in.

For an A2A hop to a peer agent, the same access token appears in both headers, because the far end is another engine that verifies the agent identity directly.

Remember that first header. The desk you're about to build reads it, and it's the only place the agent's own name still appears.

---

## 11:45 — A pass reception can read, and one they have to phone about

The visiting building's reception can be handed two kinds of pass. One has to be phoned in. Reception rings head office to ask whether it's real, and waits. When several workers arrive at once the line gets busy and somebody is turned away for no good reason. That's an access token, which Cloud Run verifies remotely, and under a concurrent fan-out it surfaces as an intermittent 401 saying the token could not be verified.

The other can be read on the spot, because it carries a stamp reception recognises and it names this specific building. That's an ID token, verified locally against Google's public keys with the audience checked against the receiving service's URL. Nothing is called, so nothing can flake.

ADK's MCP session manager injects the agent's access token into `Authorization` itself and skips that when the header is already set, so this codebase pre-sets the ID token through a header provider.

---

## 13:15 — What is still open

So where does that leave us, with everything working and nothing built yet?

**The tool question has nowhere to be asked.** Every agent reaches the licensing server as the same invoker account. That server also exposes tools that change things. Updating a vendor. Writing a contract. Resetting the store. A compromised pricing agent holds a badge that opens the whole building, and reception has no way to tell it apart from vendor clearance.

**And the open internet has no desk at all.** An agent that decides to POST to `somewhere-else.example.com` meets no policy anywhere, because there's no IAM on the far end of that call to consult.

Both of those happen on the way **out**, and both can be answered from that `Proxy-Authorization` header.

That's what you're about to build.

---

## 14:45 — One desk, both directions

[SCREEN: client → INGRESS → agent → EGRESS → MCP / APIs / peer agents.]

The security desk watches two directions, and it's one desk. The gateway is the same way: **one resource governs traffic coming in and traffic going out.**

**Ingress is Client-to-Agent.** It asks which clients may call your agents and what security policies apply to those calls. The client is something like Cursor, a CLI, or somebody's app.

**Egress is Agent-to-Anywhere.** It asks what this agent may reach and whether what it's sending is safe.

Model Armor attaches to either direction with a template per direction. On ingress it evaluates the request going in and the response coming back. On egress it intercepts the outbound payload before it reaches an LLM, a third-party agent or an MCP server.

Vibeflix staffs the outward direction only. `deploy/agent-gateway.yaml` sets `governedAccessPath: AGENT_TO_ANYWHERE` and configures no Model Armor template, because the console calls the agents over A2A from its own app, so there's no third-party client to gate. Opening these agents to external callers is when you'd staff the inward direction.

---

## 16:15 — Who stands at the desk

The gateway is the desk. **IAP is the guard standing at it.**

You've likely met Identity-Aware Proxy already. It's the thing that sits in front of a web application and decides who may come in, the piece that replaced "you're inside the VPN, so you're trusted" with "show me who you are". Same guard here, working the outbound side, and `roles/iap.egressor` is the role that says where a principal may go.

The gateway on its own routes traffic and holds no opinion about your policy. The **authorization extension** you're about to create is what gives it one. It tells the gateway to call IAP for a verdict on every request, and IAP answers by evaluating the IAM conditions you granted.

By the time IAP is consulted, the gateway has already parsed the MCP request, so IAP can read attributes of the call **in flight**:

```
api.getAttribute('iap.googleapis.com/mcp.toolName', '')
```

A condition can therefore say "`deal_pricing` may call `get_license_pricing`". That's a sentence IAM has no vocabulary for on its own, where `run.invoker` covers a service and every tool on it.

---

## 18:15 — Three questions on the way out

Every time a worker walks out, the desk asks three things in order, and each maps to a real check.

**Is that building on the list?** The desk keeps a list of buildings that can be visited, and that's the Agent Registry. A destination nobody registered can't be reached.

**Is this worker named for it?** Each agent is separately granted `roles/iap.egressor` on the entries it may reach.

**And which room?** The CEL condition on that grant names which tool this agent may call there.

All three read `Proxy-Authorization` to work out who's asking. That's the pass Cloud Run never sees.

At the far end the checks continue as they always did. Cloud Run checks the audience and the signature. A peer engine resolves the token back to a principal. A Google API checks that the token was issued to the certificate on this connection.

---

## 19:45 — What a registry entry contains

The desk's list has more on it than addresses, and the difference between the two kinds of entry is what makes per-tool policy possible.

An **MCP server** registers with its tool spec. `setup_gateway.sh` generates that spec from the running server and passes it as `--mcp-server-spec-type=tool-spec`, so the registry entry lists every tool that server exposes. The gateway can name a tool in a policy because the registry already knows the tool exists.

An **agent** registers with `--endpoint-spec-type=no-spec` and an interface URL. That URL matters, because it points at the **mTLS** aiplatform host. The gateway authorises the mTLS host and refuses the plain one, which is the same detail that forced this project to build its own agent cards back in Step 4.

Both kinds carry a protocol binding, JSONRPC, so the gateway knows what it's routing.

---

## 21:00 — Deny-by-default reaches further than you'd think

Once the gateway is in the path, an agent can only reach registered destinations. This is why `grant_agent_iam.sh` registers far more endpoints than you'd expect. **That includes Google's own APIs.** The very ones that have been checking these badges since Step 2. The model call goes to aiplatform. Session writes go to the regional aiplatform mTLS host. The runner's errand goes to iamcredentials.

None of those are your services, and every one of them now needs a registry entry and an egress grant, or the agent can't think, can't save a session, and can't collect the pass it needs to reach an MCP server.

So the script registers both the plain and mTLS hosts for iamcredentials, the global aiplatform host and the regional one. Which an agent uses depends on configuration, so both get granted.

There's also **all-to-all A2A egress**: every agent principal is granted the egress role on every agent endpoint. The orchestrator calls three specialists and vendor clearance calls legal, and the script grants the lot rather than maintaining that graph by hand.

That brings a trap with it. An agent endpoint advertising the aiplatform host **shadows** the general aiplatform entry for every engine's own model call, so an engine holding no agent-endpoint grant can lose the ability to call Gemini for reasons that have nothing to do with agents calling agents.

---

## 23:00 — Two lists, and where to look

[SCREEN: the console, one agent's policy rows, then an MCP server's.]

By the end of this step the desk keeps two separate lists, and they show up in different places in the console.

**The first is life support.** Those Google APIs we just talked about, plus the console app, registered with `GCP …` display names and granted to all six agents **with no condition attached**. Every agent needs every one of them to function, so there's nothing per-agent to express.

**The second is `policies.yaml`.** Each row becomes an `iap.egressor` grant on an **MCP server** entry, carrying one agent principal and a CEL condition listing that agent's tools. This is the layer where the agents differ from each other.

In the console that split is visible. Open an agent and you'll see rows named `GCP agentregistry`, `GCP aiplatform` and so on with the Conditions column empty. That's the first list, behaving exactly as designed. The tool rules live on the three **MCP server** resources, and that's where the conditions are.

Two resources, two lists. Looking at an agent shows you life support; looking at a server shows you policy.

---

## 24:30 — Where the guarantees stop

Three things this doesn't do, before you describe it in an audit conversation.

**The extension fails open.** `iap-authz-extension.yaml` sets `failOpen: true` with a five-second timeout, so an outage in the policy engine lets traffic pass rather than taking down every agent in the mesh. It's a control that degrades toward availability, and you should know which way yours falls.

**Calls carrying no tool name are allowed.** The CEL condition begins by admitting them, which is what keeps Gemini calls, A2A hops and the MCP handshake working. The allowlist governs MCP tool invocations, and everything else passes on the strength of the first two questions.

**Life support is a blanket.** `ui_renderer` can reach `agentregistry` whether it needs to or not. Curating that list per agent drifted during development and produced 403s nobody could trace, so it's granted wholesale, and the precision lives at the tool layer.

---

## 25:45 — Register, gate and grant

```bash
cd ~/vibeflix-audit
source ./env.sh
./deploy/setup_gateway.sh
```

[DO: run it.]

Four things, and they have to happen in this order. The six agents get registered, since the MCP servers already were in Step 1. The gateway gets created. The authorization extension gets attached, which is what makes the gateway consult policy per request. Then the IAM script adds the egress grants.

Each step supplies what the next one refers to. A policy can only name a destination the registry knows, and the grants need to be in place before the first governed call goes out.

Until now, each agent's grants described what it may do. These describe where it may go.

---

## 26:45 — Attaching the engines

```bash
cd ~/vibeflix-audit
source ./env.sh
python deploy/deploy_agents_a2a.py
```

This is the one redeploy the workshop still requires.

The gateway didn't exist when you deployed these engines in Steps 2 through 5, and each deploy said so at the time. An engine's gateway attachment is part of its deployment spec, baked in when the engine is created.

In Step 6 the task-store URL turned out to be computable, so no second pass was needed. This one is a relationship to a thing that didn't exist yet.

Until this pass runs, the agents' egress is ungoverned. Everything from Step 2 still guards them; the desk simply isn't in the path yet.

> On a project with a small Agent Engine quota, six deploys at once can come back
> `RESOURCE_EXHAUSTED`. Deploy them one at a time and nothing is lost, because re-deploying an
> engine that already attached is harmless.

---

## 27:45 — Verify, then run it for real

```bash
cd ~/vibeflix-audit
source ./env.sh
./deploy/verify/step7.sh
```

Confirms the gateway exists, the six agents and three MCP servers are registered, and all six agents run under their own agent identity.

Then run a full audit through the deployed console, because a script confirms the wiring and only a real run shows the mesh still works with governance in the path.

[DO: open the console, pick the happy path, run it.]

Every tool LED that blinks is three gateway questions that came back yes.

---

## 28:45 — When somebody gets turned away

[SCREEN: a branch failing — 403, egress request is not authorized.]

An agent reports a 403 saying egress is not authorized, its branch fails, and the others pass. One of the three answers at the desk was no. Either the destination isn't registered, or the agent isn't named for it, or the CEL condition excludes that tool.

Being refused is the desk doing its job. Deny-by-default means a misconfiguration fails closed and you find out immediately, where the same mistake in an ungoverned system produces no error at all and surfaces during an audit or a breach.

Re-applying the policies fixes it. IAM and gateway changes take two to five minutes to propagate, so if the first run right after this step fails on egress, wait and run it again.

Tell the two refusals apart. A 403 at your own desk on the way out is a permission problem. A 401 at the far end is a pass problem, so check the token rather than the registration.

---

## 29:45 — The whole security story

[SCREEN: build the chain up, one layer at a time.]

In Step 1 the tool servers went up with no public access, and a browser still gets a 403 today.

In Steps 2 through 5 every agent got its own badge, a SPIFFE principal proved by a platform-issued certificate, with its own narrow roles and no shared service account. From that moment every Google service it touched was checking that badge against the grants you made.

Because that principal has no way to authenticate to Cloud Run directly, each agent sends a runner for an audience-bound ID token, and the agents become indistinguishable at that one door.

In Step 6 the app got its own identity as an ordinary Cloud Run service account, since it isn't an engine.

In Step 7 a desk went in on the outward side, deny-by-default, asking three questions on every call. The third question is the one that closes the door the runner left open.

---

## 30:45 — Do and don't

Give every agent its own badge, because a shared service account destroys attribution and can be taken by anything it's attached to.

Leave the mTLS settings at their defaults, because a certificate-bound token needs the certificate on the connection.

Don't delete an engine to redeploy it, since the badge dies with it and takes every grant along.

Scope policy per tool, because reaching a building and entering one room in it are very different blast radii.

Staff the inward direction as well if anything outside your own app will call these agents.

Don't route around a gateway 403. Fix the registration, the role, or the CEL condition.

---

## 31:30 — Where that leaves us

Every agent carries a badge only the platform can print, and every Google service it calls has been checking that badge since Step 2. For the one destination that can't see it, a desk now stands on the way out and asks who's leaving, where they're going, and which room they mean to enter.

One step left, where we use the thing. Four scenarios that each end differently, driven entirely by data. Then three observability views, and teardown.

See you there.
