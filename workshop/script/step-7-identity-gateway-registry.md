# Step 7 — Identity, Gateway & Registry

**Target runtime:** 21–25 min · **Lab section:** `Identity, Gateway & Registry`

---

## 00:00 — Cold open

[SCREEN: the finished mesh. Six agents, three tool servers, all green.]

Everything works at this point. Six agents, three tool servers, a console, and a full audit that runs end to end.

So here's a question worth sitting with. If one of those agents were compromised tomorrow — say through a prompt injection buried in a vendor's document — what stops it from calling the licensing server and writing itself a contract?

The answer today is its own IAM, and that's genuine but coarse. IAM grants an agent reach to a whole server. The thing it can't express is that this agent may call one specific tool on that server and nothing else.

This step closes that gap, and the word that matters throughout is path.

---

## 01:30 — Governance that sits in the traffic path

Most organisations already have governance, and it lives in a spreadsheet describing which system may talk to which, who approved it and when it was last reviewed. That spreadsheet describes what somebody intended, and the gap between the intention and the running system is where every interesting incident lives.

What we're building instead is governance in the traffic path: a component that requests physically travel through, which applies the rules and refuses anything outside them.

The test for whether you have one is simple enough to apply to your own systems. Can you violate the policy without changing the policy? If you can, what you have is a document. If you can't, what you have is a guardrail.

---

## 03:00 — Three pieces that compose

There are three things involved here and people mix them up constantly, so let's separate them.

Agent Identity means every agent is its own principal with its own name, which is what makes an action attributable and what makes least privilege possible at all. You've been building this since Step 2.

The Registry is the catalogue of what exists and where it lives, covering every MCP server and every agent. You registered the servers back in Step 1.

The Gateway is the governed front door that traffic goes through. It works on a deny-by-default basis and it only routes to destinations that appear in the registry.

The way those three compose is the elegant part. Identity answers who is calling, the registry answers what may be called, and the gateway is the place where those two facts meet and a decision gets made. None of the three is sufficient on its own, and together they're a policy engine.

It also changes what registration means. An unregistered destination is unreachable, so enrolment becomes enforcement.

---

## 05:30 — The policy map

[SCREEN: `deploy/policies.yaml`.]

Open the policy file and you'll find each agent mapped to the exact tools it's allowed to invoke, so brand style may call the brand audit tool and deal pricing may call the pricing lookup.

That's the difference between saying an agent can reach the licensing server and saying it can call one specific tool on it, and the difference matters more than it might appear.

The licensing server also exposes tools that change things: updating a vendor, writing a contract, resetting the store. Deal pricing has no business calling any of them, and under coarse IAM it could. Under per-tool policy it can't, and the attempt gets refused in the path and logged.

That's blast radius made concrete. A compromised pricing agent can look up prices, and it has no route to writing a contract.

---

## 07:00 — Register, gate and grant

```bash
cd ~/vibeflix-audit
source ./env.sh
./deploy/setup_gateway.sh
```

[DO: run it.]

Four things happen in order.

The six agents get registered, since the MCP servers already were. The governed front door gets created. The authorization extension gets attached, which is what makes the gateway consult policy on every request. And then it calls the IAM script, which adds the egress grants on top of the per-agent access you granted in Steps 2 through 5.

That last distinction is worth holding on to. Until now, each agent's grants described what it may do. These new ones describe where it may go, which is a separate question answered by a separate grant.

---

## 09:00 — Attaching the engines

```bash
cd ~/vibeflix-audit
source ./env.sh
python deploy/deploy_agents_a2a.py
```

This is the one redeploy the workshop still requires, and it's worth knowing why it can't be avoided.

The gateway exists now, and it didn't exist when you deployed these engines in Steps 2 through 5 — each deploy said as much at the time, reporting that it was deploying without governed egress. An engine's gateway attachment is part of its deployment spec, baked in when the engine is created.

Compare that with Step 6, where the task-store URL turned out to be computable and no second pass was needed. This one is a relationship to a thing that didn't exist yet, which is a different kind of problem.

Until this pass runs, the agents' egress is ungoverned, so this is the step where the guardrail actually goes into the path.

---

## 11:00 — Verifying the wiring

```bash
cd ~/vibeflix-audit
source ./env.sh
./deploy/verify/step7.sh
```

That confirms the gateway exists, that the six agents and three MCP servers are registered, and that all six agents run under their own agent identity.

---

## 12:00 — Running it for real

A script can confirm the wiring is correct. The only thing that demonstrates the mesh still works with governance in the path is a full audit through the deployed console.

```bash
cd ~/vibeflix-audit
source ./env.sh
gcloud run services describe vibeflix-app --region "$REGION" --format 'value(status.url)'
```

[DO: open the console, pick the happy path, run it.]

This is the same scenario you ran locally in Step 6, and everything about this run happens in the cloud. The app calls the orchestrator engine over A2A, which fans out to three more engines, each authenticating as its own principal and reaching the MCP servers through the gateway.

Three things to watch. The graph animates, and those events come from the engines over Pub/Sub, with the console subscribing to the stream. The tool LEDs fire, and each blink means the gateway allowed that call, so every one of them is a policy decision that came back yes. And the run ends with a contract.

---

## 15:00 — What a failure looks like

This shape is worth learning to recognise, because you'll see it eventually and it's much less alarming once you know it.

[SCREEN: a branch failing — 403, egress request is not authorized.]

An agent reports a 403 saying the egress request is not authorized, its branch fails, and the others pass. That means either the destination isn't registered, or that agent lacks the egress role on it.

The mindset shift I'd encourage here is that this is the system working. Deny-by-default means a misconfiguration fails closed, so you find out about it immediately. In an ungoverned system the same mistake produces no error at all, the call goes through, and you find out during an audit or a breach.

Re-applying the policies fixes it, and the valuable part is the immediacy of the feedback.

One practical note: IAM and gateway changes take two to five minutes to propagate, so if the first run right after this step fails on egress, wait and run it again before concluding that something is wrong. That one has caught a lot of people.

---

## 17:30 — The whole security story

Let's put the pieces together, because this is the payoff of the entire workshop.

[SCREEN: build the chain up, one layer at a time.]

In Step 1 the tool servers went up with no public access, so a browser gets a 403, and that's still true today.

In Steps 2 through 5 every agent received its own identity and its own narrow set of roles, with no shared service account anywhere. Because an agent identity can't authenticate to Cloud Run directly, each one reaches the tool servers by impersonating an invoker service account, which is a deliberate relationship that can be granted and revoked.

In Step 6 the app got its own identity on the same basis.

And in Step 7 a gateway went into the path, working deny-by-default, applying per-tool policy, with destinations that have to be registered before they can be reached at all.

At every step we changed what is possible, and the allowlist is the running system rather than a document describing it. That's what guardrails means here, and it's closer to physics than to advice.

---

## 19:30 — Do and don't

Give every agent its own identity, because a shared service account destroys attribution and makes least privilege impossible.

Treat a policy document and enforcement as different things, using the test from earlier: if you can violate it without editing it, it isn't a control.

Scope policy per tool rather than per server, since reaching a server and calling one read-only tool on it are very different blast radii.

Resist routing around a gateway 403, because it's the guardrail reporting, and the thing to fix is the policy or the registration.

Register everything you intend to be reachable, since under deny-by-default the registry is the allowlist.

And give a fresh gateway change five minutes before you start debugging it.

---

## 21:30 — Where that leaves us

Governance sits in the traffic path now. Every hop is checked, every agent is attributable, and a misconfiguration fails loudly and immediately.

One step remains, and in it we actually use the thing. Four scenarios that each end differently, driven entirely by the data rather than by different code paths. Then we look at the whole system through three observability lenses, and tear it all down.

See you there.
