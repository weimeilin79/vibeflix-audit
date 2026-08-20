# Step 7 — Identity, Gateway & Registry

**Target runtime:** 21–25 min · **Lab section:** `Identity, Gateway & Registry`

---

## 00:00 — Cold open

[SCREEN: the finished mesh diagram, all six agents and three tool servers, everything green.]

Everything works. Six agents, three tool servers, a console. You can run a full audit end to end.

[BEAT]

And if one of those agents were compromised tomorrow — a prompt injection in a vendor's document, say — what exactly stops it from calling the licensing server and writing itself a contract?

Right now: its own IAM, and nothing else. That's real, and it's not nothing. But it's coarse. It says *this agent may reach that server*. It doesn't say *this agent may call this one tool on that server, and nothing else*.

This step closes that gap. And the important word in it is **path**.

---

## 01:30 — Governance in a document versus governance in the path

Most organisations have governance. It's in a spreadsheet. It says which system may talk to which, who approved it, and when it was reviewed.

That document is not enforcement. It's a description of what someone *intended*. The gap between the spreadsheet and the running system is where every interesting incident lives.

[BEAT]

What we're building instead is governance **in the traffic path**. Not a document that describes the rules — a component that traffic physically goes through, that applies the rules, and that says no.

The test for whether you have this: **can you violate the policy without changing the policy?** If yes, you have a document. If no, you have a guardrail.

---

## 03:00 — Three pieces, and how they fit

There are three things here and people mix them up constantly, so let's separate them cleanly.

**Agent Identity.** Every agent is its own principal. Not a shared service account, not the app's identity — its own. That's what makes an action *attributable*, and it's what makes least privilege possible at all. You've been building this since Step 2.

**The Registry.** The catalogue of what exists and where it lives. Every MCP server, every agent. You registered the MCP servers back in Step 1.

**The Gateway.** The governed front door. Traffic goes through it. It is **deny-by-default**, and it will only route to destinations that are in the registry.

[BEAT]

Now watch how they compose, because this is the neat part.

Identity answers *who is calling*. The registry answers *what may be called*. The gateway is the place where those two facts meet and a decision gets made. None of the three is sufficient alone. Together they're a policy engine.

And notice: registration stops being bookkeeping. An unregistered destination isn't merely undiscoverable — it's **unreachable**. Enrolment becomes enforcement.

---

## 05:30 — The policy map

[SCREEN: `deploy/policies.yaml`.]

Open the policy file. It maps each agent to the exact tools it may invoke. Brand style may call the brand audit tool. Deal pricing may call the pricing lookup.

[BEAT]

That's the difference between *"this agent can reach the licensing server"* and *"this agent can call **only** `get_license_pricing` on it."*

Think about what that buys you. The licensing server also exposes `update_vendor`, `upsert_contract`, `reset_vendors` — tools that change things. Deal pricing has no business calling any of them. Under coarse IAM, it could. Under per-tool policy, it cannot, and the attempt is refused in the path and logged.

That's the blast-radius argument, made concrete. A compromised pricing agent can look up prices. It cannot write a contract.

---

## 07:00 — Register, gate, and grant

```bash
cd ~/vibeflix-audit
source ./env.sh
./deploy/setup_gateway.sh
```

[DO: run it.]

Four things happen, in order.

**Registry** — the six agents get registered. The MCP servers already were, in Step 1.

**Gateway** — the governed front door is created.

**Policies** — the authorization extension is attached, which is what makes the gateway consult policy per request.

**Grants** — and then it calls the IAM script, which adds the **egress grants** on top of the per-agent access you granted in Steps 2 through 5.

That last distinction matters. Up to now, each agent's grants were about what it may *do*. These new ones are about where it may *go*. Two separate questions, two separate grants.

---

## 09:00 — Attach the engines to the gateway

```bash
cd ~/vibeflix-audit
source ./env.sh
python deploy/deploy_agents_a2a.py
```

This is the **one redeploy the workshop still needs**, and it's worth understanding why it can't be avoided.

The gateway exists **now**. It didn't when you deployed these engines in Steps 2 through 5 — each deploy said so at the time, that it was deploying without governed egress.

An engine's gateway attachment is part of its **deployment spec**. It isn't a value read at runtime that you can point at a future address. It's baked in when the engine is created.

[BEAT]

Contrast that with the task-store URL in Step 6, which turned out to be computable, so no second pass was needed there. This one isn't a value you can predict — it's a relationship to a thing that didn't exist.

**Until this pass, the agents' egress isn't governed.** So this is not a formality; it's the step where the guardrail actually goes into the path.

---

## 11:00 — Verify the wiring

```bash
cd ~/vibeflix-audit
source ./env.sh
./deploy/verify/step7.sh
```

This confirms the gateway exists, the six agents and three MCP servers are registered, and all six agents run under their own agent identity — you'll see the principal form in the output.

---

## 12:00 — Now run it for real

[BEAT]

Scripts can tell you the wiring is right. The only thing that proves the mesh still **works** with governance in the path is a full audit through the deployed console.

```bash
cd ~/vibeflix-audit
source ./env.sh
gcloud run services describe vibeflix-app --region "$REGION" --format 'value(status.url)'
```

[DO: open the console, pick the happy path, run it.]

This is the same scenario you ran locally in Step 6. Nothing about this run is local now. The app calls the **orchestrator engine** over A2A. That fans out to three more **engines**. Each authenticates as its own principal, and reaches the MCP servers **through the gateway**.

Watch for three things.

**The graph animating** — and note where those events come from. Not your machine. The engines publish them over Pub/Sub, and the console subscribes.

**The tool LEDs firing** — which means the gateway **allowed** those calls. Every blink is a policy decision that came back yes.

**A contract at the end.**

---

## 15:00 — What a failure looks like

I want you to know this shape, because you will see it eventually and it's much less alarming once you recognise it.

[SCREEN: an agent branch failing with `403 Egress request is not authorized`.]

An agent reports **403 — egress request is not authorized** — and its branch fails while the others pass.

That means one of two things. Either the destination isn't registered, or that agent doesn't have the egress role on it.

[BEAT]

And here's the mindset shift I'd like you to make: **that is not a bug. That's the system working.**

Deny-by-default means the failure mode of a misconfiguration is *refusal*, not silent success. In an ungoverned system, the equivalent mistake doesn't produce an error at all — the call goes through, and you find out during an audit, or a breach.

Re-applying the policies fixes it. But the important thing is that you *found out immediately*.

One practical note: **IAM and gateway changes take two to five minutes to propagate.** If the first run right after this step fails on egress, wait and run it again before assuming something's broken. That one has caught a lot of people.

---

## 17:30 — The security story, end to end

Let's put the whole thing together, because this is the payoff of the entire workshop.

[SCREEN: build the chain up, one layer at a time.]

**Step 1** — the tool servers went up with no public access. A browser gets a 403. They still do.

**Steps 2 to 5** — every agent got its own identity and its own narrow set of roles. No shared service account anywhere. And because an agent identity can't authenticate to Cloud Run directly, each one reaches the MCP servers by *impersonating* an invoker service account — a deliberate, grantable, revocable relationship.

**Step 6** — the app got its own identity too, with its own list.

**Step 7** — a gateway in the path, deny-by-default, per-tool policy, and destinations that must be registered to be reachable.

[BEAT]

At no point did we write a document saying what should be allowed. At every point we changed what *is possible*.

That's what "guardrails" means here. Not advice. Physics.

---

## 19:30 — Do and don't

**Do give every agent its own identity.** A shared service account destroys attribution and makes least privilege impossible. This is the foundation everything else stands on.

**Don't confuse a policy document with enforcement.** If you can violate it without editing it, it isn't a control.

**Do scope policy per tool, not per server.** "May reach the licensing server" and "may call one read-only tool on it" are very different blast radii.

**Don't treat a 403 from the gateway as a defect to route around.** It's the guardrail reporting. Fix the policy or the registration — never the guardrail.

**Do register everything you intend to be reachable.** Under deny-by-default, the registry *is* the allowlist.

**Don't debug a fresh gateway change for the first five minutes.** Propagation is real; give it time before you start changing things.

---

## 21:30 — Recap and bridge

Governance is in the path now. Every hop is checked, every agent is attributable, and a misconfiguration fails loudly instead of quietly succeeding.

One step left. We're going to *use* the thing — four scenarios that each end differently, driven entirely by the data rather than by different code paths. Then we'll look at the whole system through three observability lenses, and tear it all down.

See you there.
