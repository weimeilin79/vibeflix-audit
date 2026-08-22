# Step 7 — Identity, Gateway & Registry

**Target runtime:** 22–26 min · **Lab section:** `Identity, Gateway & Registry`

---

## 00:00 — Cold open

[SCREEN: the finished mesh. Six agents, three tool servers, all green.]

Everything works. Six agents, three tool servers, a console, and a full audit end to end.

If one of those agents were compromised tomorrow, through a prompt injection buried in a vendor's document, what stops it calling the licensing server and writing itself a contract?

Its own IAM, which is coarse. IAM grants an agent reach to a whole server. It can't express that this agent may call one specific tool and nothing else.

This step closes that gap. We'll go through where an agent's identity actually comes from, what travels on the wire when it makes a call, and which component checks which claim.

---

## 01:15 — Where the principal comes from

Open `agent_identities.json` and look at a principal.

```
principal://agents.global.org-<ORG>.system.id.goog/…/reasoningEngines/<ID>
```

That's a SPIFFE ID. SPIFFE is a standard for naming a running workload with a URI that the workload can prove is its own. The spec writes it `spiffe://` and Google's IAM renders the same thing as `principal://`.

Read it in three parts. `agents.global.org-<ORG>.system.id.goog` is the **trust domain**, scoped to your organization, so a name issued in somebody else's org can never be mistaken for one of yours. Then the path down to `reasoningEngines/<ID>` names one specific engine.

The agent proves that name with an **X.509 certificate**. The SPIFFE ID sits in the certificate's subject-alternative-name field, and the engine presents that certificate during the TLS handshake. The host verifies it against the trust domain, and the call proceeds as that agent's principal.

---

## 03:00 — Can you switch it to something else?

Agent identity **replaces** the service account. In `deploy_agents_a2a.py` the engine is created with `identity_type: AGENT_IDENTITY`, and if you also try to set `service_account` on that config the API returns a 400. You get one or the other.

Without agent identity, an engine runs as a service account — the Reasoning Engine Service Agent, or a custom one you attach. A service account is shared by whatever you attach it to, it can be impersonated, and it outlives the workload. With agent identity there is no service account behind the metadata server at all.

What you get instead is one principal per agent that starts with zero permissions, is attributable to exactly one engine, and disappears when that engine is deleted.

That last property explains a rule you'll see in the docs: don't delete an engine to redeploy it. Deleting the engine destroys the identity, which orphans every role you granted to that principal, so the redeployed engine comes back with a new name and none of its access.

---

## 05:00 — The certificate, and where it comes from

The agent proves its name with a certificate, so the next question is where that certificate comes from.

Agent Runtime issues it. When an engine is created with agent identity, the platform provisions a certificate for it carrying that engine's SPIFFE ID. You don't generate it, or store it.

The certificate does two jobs. It proves the engine's name during a TLS handshake, which we covered a moment ago. And it makes the engine's tokens unique to that engine, which is the part worth walking through.

---

## 06:15 — Why the token isn't shared

An engine gets its access token from the metadata server, the same way any Google Cloud workload does. There are two kinds of token it can ask for.

A plain token is handed out without reference to the certificate. Anyone holding a copy of that token can use it.

A **certificate-bound** token is requested with the certificate's fingerprint attached. What comes back is tied to that certificate, so it only works on a connection where that certificate is presented. Copy the token to another machine and it stops working there, because the copier doesn't hold the certificate's private key.

That binding is what makes it this engine's token rather than a credential that travels.

mTLS is how the certificate gets onto the connection. Mutual TLS means both ends present certificates, so the engine's certificate is on the connection when the token arrives. The receiving service can then check that the token it was handed was issued to the certificate it can see. Without the certificate on the connection there's nothing to check the binding against.

So the mTLS settings on an engine are part of how its credentials work, rather than transport tuning you can switch off for convenience. Leave them at their defaults.

---

## 07:30 — Can you use a different token issuer?

No, and it's worth being clear about which part is fixed.

The principal, the trust domain and the certificate are all issued by Agent Runtime, inside your organization's trust domain. You can't point an agent identity at your own identity provider, your own certificate authority, or a third-party issuer. The platform mints the name and the proof of it.

What the Google auth library does is the client half: it reads the certificate the platform provisioned, asks the metadata server for a bound token, and attaches the credential to outgoing calls. Any client that spoke the same metadata protocol could do that work, so the library isn't the constraint. The issuer is.

There's one consequence of this you'll meet in the code. Because an agent-identity engine has no service account behind the metadata server, the normal call for fetching an ID token can't work. So when the engine needs an audience-bound ID token for Cloud Run, it bootstraps: it mints its own access token, uses that to call the IAM credentials API, impersonates the MCP invoker service account, and gets the ID token back from there.

That's why the grant in Step 2 included the token-creator role on that service account. Without it, a SPIFFE principal has no way to obtain a token Cloud Run accepts.

---

## 09:00 — One gateway, on both sides of the agent

[SCREEN: client → INGRESS → agent → EGRESS → MCP / APIs / peer agents.]

Now the gateway, and the first thing to get right is the topology. **The same gateway resource governs traffic coming in and traffic going out.** Drawing it as two separate products misrepresents what it is.

**Ingress is Client-to-Agent.** It answers which clients may call your agents, and what security policies apply to those calls. The client here is something like Cursor, a CLI, or somebody's app.

**Egress is Agent-to-Anywhere.** It answers what this agent may reach, and whether what it's sending is safe. The destinations are MCP servers, third-party APIs, and peer agents.

Model Armor attaches to either direction, with a template **per direction**. On ingress it evaluates the request going in and the response coming back. On egress it intercepts the outbound payload before it reaches an LLM, a third-party agent, or an MCP server.

Vibeflix configures egress only. Look at `deploy/agent-gateway.yaml` and you'll find `governedAccessPath: AGENT_TO_ANYWHERE` and no Model Armor template. Ingress isn't set up because the console calls the agents over A2A from its own app, so there's no third-party client to gate. If you were exposing these agents to external callers, that's the half you'd turn on.

---

## 11:00 — Two tokens on every call

[SCREEN: the two headers on an outbound MCP call.]

Now what actually travels on the wire. An outbound MCP call carries **two** authorization headers, and they're for two different readers.

`Proxy-Authorization` carries the agent's own access token, issued by its agent identity. **The gateway reads this one.** It's how the gateway knows which agent is calling.

`Authorization` carries an ID token minted for the MCP server's URL, obtained by impersonating the MCP invoker service account. **Cloud Run reads this one.**

Two readers, two questions. The gateway asks whether this agent may go there. Cloud Run asks whether this caller may come in. Neither can answer the other's question, so both headers are on the call.

For an A2A hop to a peer agent, the same access token appears in both headers, because the far end is another engine rather than a Cloud Run service, and it verifies the agent identity directly.

---

## 13:00 — Why an ID token and not an access token

The choice of an **ID** token for the Cloud Run hop looks like a detail and isn't.

Cloud Run has to verify an access token **remotely**, by calling Google's token introspection endpoint. Under a concurrent fan-out — three agents hitting MCP servers at once — that introspection flakes, and it surfaces as an intermittent 401 saying the access token could not be verified.

An ID token is verified **locally**, by checking the signature against Google's public keys and checking that the audience matches the receiving service's own URL. Nothing has to be called, so it can't flake that way.

There's an implementation wrinkle worth knowing if you hit it. ADK's MCP session manager injects the agent's access token into `Authorization` itself, and it skips doing that when the header is already present. So this codebase pre-sets the ID token through a header provider, which makes ADK leave it alone.

---

## 14:30 — What checks what

[SCREEN: the layers, in order.]

Follow one MCP call from the agent to the tool and count the checkpoints.

**At the gateway**, three checks in sequence. Is this destination registered in the Agent Registry? Does this agent hold `roles/iap.egressor` on that entry? And does the CEL condition on that grant allow this specific tool? All three read `Proxy-Authorization` to work out who's asking.

**At Cloud Run**, two checks. Does the token's audience match this service's own URL, and is the signature real and unexpired? Those read `Authorization`.

**At a peer engine**, on an A2A hop, the far side asks Google's token service whether the token is valid and whose it is, then resolves which agent identity sits behind it.

**At a Google API**, the check is different again, because the token is certificate-bound. The API verifies that the token was issued to the certificate on this connection, and that the certificate is this engine's own SPIFFE identity.

Different layers verify different claims, and no single layer is doing all of it.

---

## 17:00 — The policy map

[SCREEN: `deploy/policies.yaml`.]

Each agent is mapped to the exact tools it may invoke, so brand style may call the brand audit tool and deal pricing may call the pricing lookup. Those entries become the CEL conditions the gateway evaluates.

The licensing server also exposes tools that change things: updating a vendor, writing a contract, resetting the store. Deal pricing has no business calling any of them, and under coarse IAM it could. Under per-tool policy the attempt is refused in the path and logged.

A compromised pricing agent can look up prices and has no route to writing a contract.

---

## 18:15 — Register, gate and grant

```bash
cd ~/vibeflix-audit
source ./env.sh
./deploy/setup_gateway.sh
```

[DO: run it.]

Four things in order. The six agents get registered, since the MCP servers already were in Step 1. The gateway gets created. The authorization extension gets attached, which is what makes the gateway consult policy per request rather than just routing. Then it calls the IAM script, which adds the egress grants.

Until now each agent's grants described what it may do. These describe where it may go, and they're the `iap.egressor` roles the gateway checks.

The registry matters more than it looks. Under deny-by-default, an unregistered destination is unreachable, so the registry is the allowlist.

---

## 19:45 — Attaching the engines

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

## 20:45 — Verify and run it for real

```bash
cd ~/vibeflix-audit
source ./env.sh
./deploy/verify/step7.sh
```

Confirms the gateway exists, the six agents and three MCP servers are registered, and all six agents run under their own agent identity — you'll see the `principal://` form in the output.

Then run a full audit through the deployed console, because a script confirms the wiring and only a real run demonstrates the mesh still works with governance in the path.

[DO: open the console, pick the happy path, run it.]

The tool LEDs firing means the gateway allowed those calls, so every blink is three checks that came back yes.

---

## 22:00 — What a failure looks like

[SCREEN: a branch failing — 403, egress request is not authorized.]

An agent reports a 403 saying egress is not authorized, its branch fails, and the others pass. That points at one of the three gateway checks: the destination isn't registered, the agent lacks `iap.egressor` on it, or the CEL condition excludes that tool.

This is the system working. Deny-by-default means a misconfiguration fails closed and you find out immediately. In an ungoverned system the same mistake produces no error, the call goes through, and you find out during an audit or a breach.

Re-applying the policies fixes it. IAM and gateway changes take two to five minutes to propagate, so if the first run right after this step fails on egress, wait and run it again.

A 401 rather than a 403 points at the credential path instead of the policy path, so check the token rather than the registration.

---

## 23:30 — The whole security story

[SCREEN: build the chain up, one layer at a time.]

In Step 1 the tool servers went up with no public access, and a browser still gets a 403 today.

In Steps 2 through 5 every agent got its own SPIFFE principal, proved by a certificate, with its own narrow roles and no service account anywhere. Because that principal can't authenticate to Cloud Run directly, each agent reaches the tool servers by impersonating an invoker service account to mint an audience-bound ID token.

In Step 6 the app got its own identity, as an ordinary Cloud Run service account, since it isn't an engine.

In Step 7 a gateway went into the path on the egress side, deny-by-default, checking the registry, the egress role and a per-tool CEL condition on every call.

At every step we changed what is possible, so the allowlist is the running system.

---

## 25:00 — Do and don't

Give every agent its own identity, because a shared service account destroys attribution and can be impersonated by anything it's attached to.

Leave the mTLS settings at their defaults, because a certificate-bound token needs the certificate on the connection.

Don't delete an engine to redeploy it, because the identity dies with it and takes every grant along.

Scope policy per tool rather than per server, since reaching a server and calling one read-only tool on it are very different blast radii.

Turn on ingress as well as egress if anything outside your own app will call these agents.

Don't route around a gateway 403. Fix the registration, the role, or the CEL condition.

---

## 26:15 — Where that leaves us

Governance sits in the traffic path on the egress side. Every hop carries two tokens for two different verifiers, every agent is a SPIFFE principal that can be named and revoked on its own, and a misconfiguration fails closed.

One step left, where we use the thing. Four scenarios that each end differently, driven entirely by data. Then three observability views, and teardown.

See you there.
