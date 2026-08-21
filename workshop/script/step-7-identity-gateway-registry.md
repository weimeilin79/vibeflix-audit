# Step 7 — Identity, Gateway & Registry

**Target runtime:** 21–25 min · **Lab section:** `Identity, Gateway & Registry`

---

## 00:00 — Cold open

[SCREEN: the finished mesh. Six agents, three tool servers. All green.]

Everything works. Six agents. Three tool servers. A console. You can run a full audit end to end.

[BEAT]

Now. One of those agents gets compromised tomorrow. A prompt injection buried in a vendor's document.

What stops it from calling the licensing server and writing itself a contract?

[BEAT]

Right now: its own IAM. And nothing else.

That's real. It's not nothing. But it's coarse. It says *this agent may reach that server.* It does not say *this agent may call this one tool, and nothing else.*

Today we close that gap. And the word that matters is **path.**

---

## 01:30 — A document is not a control

Most organisations have governance. It's in a spreadsheet. Which system may talk to which. Who approved it. When it was last reviewed.

That spreadsheet describes what somebody *intended*.

And the gap between the spreadsheet and the running system is where every interesting incident lives.

[BEAT]

What we're building instead is governance **in the traffic path.** A component that traffic physically goes through, that applies the rules, and that says no.

Here's the test. **Can you violate the policy without changing the policy?**

If yes, you have a document. If no, you have a guardrail.

---

## 03:00 — Three pieces

Three things here. People mix them up constantly. Let's separate them.

**Agent Identity.** Every agent is its own principal, with its own name.

That's what makes an action *attributable*. And it's what makes least privilege possible at all. You've been building this since Step 2.

**The Registry.** The catalogue of what exists and where. Every MCP server. Every agent. You registered the servers back in Step 1.

**The Gateway.** The governed front door. Traffic goes through it. It is **deny-by-default.** And it only routes to destinations that are in the registry.

[BEAT]

Now watch how they compose. This is the neat part.

Identity answers *who is calling.* The registry answers *what may be called.* The gateway is where those two facts meet and a decision happens.

None of the three is enough alone. Together they're a policy engine.

And notice what happens to registration. An unregistered destination is **unreachable.**

Enrolment becomes enforcement.

---

## 05:30 — The policy map

[SCREEN: `deploy/policies.yaml`.]

Open the policy file. It maps each agent to the exact tools it may call. Brand style may call the brand audit tool. Deal pricing may call the pricing lookup.

[BEAT]

That's the difference between *"this agent can reach the licensing server"* and *"this agent can call **only** this one tool on it."*

Think about what that buys you.

The licensing server also exposes tools that *change* things. Update a vendor. Write a contract. Reset the store.

Deal pricing has no business calling any of them. Under coarse IAM — it could. Under per-tool policy, it cannot. The attempt is refused in the path, and logged.

That's blast radius, made concrete. A compromised pricing agent can look up prices. It cannot write a contract.

---

## 07:00 — Register, gate, grant

```bash
cd ~/vibeflix-audit
source ./env.sh
./deploy/setup_gateway.sh
```

[DO: run it.]

Four things, in order.

**Registry** — the six agents get registered. The MCP servers already were.

**Gateway** — the governed front door gets created.

**Policies** — the authorization extension is attached. That's what makes the gateway consult policy per request.

**Grants** — then it calls the IAM script, which adds the **egress grants** on top of the per-agent access from Steps 2 through 5.

That last distinction matters. Until now, each agent's grants were about what it may *do.* These new ones are about where it may *go.*

Two different questions. Two different grants.

---

## 09:00 — Attach the engines

```bash
cd ~/vibeflix-audit
source ./env.sh
python deploy/deploy_agents_a2a.py
```

This is the **one redeploy the workshop still needs.** And it's worth knowing why you can't dodge it.

The gateway exists **now.** It didn't when you deployed these engines in Steps 2 through 5. Each deploy said so at the time — deploying without governed egress.

An engine's gateway attachment is part of its **deployment spec.** It's baked in when the engine is created.

[BEAT]

Compare that to Step 6. The task-store URL turned out to be computable, so no second pass was needed there.

This one is a relationship to a thing that didn't exist yet.

**Until this pass, the agents' egress isn't governed.** So this isn't a formality. This is the step where the guardrail actually goes into the path.

---

## 11:00 — Verify the wiring

```bash
cd ~/vibeflix-audit
source ./env.sh
./deploy/verify/step7.sh
```

Confirms the gateway exists. The six agents and three MCP servers are registered. And all six agents run under their own agent identity.

---

## 12:00 — Now run it for real

[BEAT]

A script can tell you the wiring is right.

The only thing that proves the mesh still **works** with governance in the path is a full audit through the deployed console.

```bash
cd ~/vibeflix-audit
source ./env.sh
gcloud run services describe vibeflix-app --region "$REGION" --format 'value(status.url)'
```

[DO: open the console. Happy path. Run.]

Same scenario you ran locally in Step 6. But nothing about this run is local.

The app calls the **orchestrator engine** over A2A. That fans out to three more **engines.** Each one authenticates as its own principal. Each reaches the MCP servers **through the gateway.**

Watch three things.

**The graph animating** — and note where those events come from. The engines publish them over Pub/Sub, and the console subscribes.

**The tool LEDs firing** — which means the gateway **allowed** those calls. Every blink is a policy decision that came back yes.

**And a contract at the end.**

---

## 15:00 — What a failure looks like

Learn this shape. You will see it eventually, and it's much less alarming once you recognise it.

[SCREEN: a branch failing — 403, egress request is not authorized.]

An agent reports **403. Egress request is not authorized.** Its branch fails. The others pass.

That means one of two things. The destination isn't registered. Or that agent doesn't have the egress role on it.

[BEAT]

And here's the mindset shift I want you to make.

**That's the system working.**

Deny-by-default means a misconfiguration fails closed.

In an ungoverned system, the same mistake produces no error at all. The call goes through. And you find out during an audit. Or a breach.

Re-applying the policies fixes it. But the important part is that you found out **immediately.**

One practical note. **IAM and gateway changes take two to five minutes to propagate.** If the first run right after this step fails on egress — wait, and run it again, before you assume something's broken.

That one has caught a lot of people.

---

## 17:30 — The whole security story

Let's put it together. This is the payoff of the entire workshop.

[SCREEN: build the chain, one layer at a time.]

**Step 1.** The tool servers went up with no public access. A browser gets a 403. They still do.

**Steps 2 to 5.** Every agent got its own identity and its own narrow roles. No shared service account anywhere. And because an agent identity can't authenticate to Cloud Run directly, each one reaches the tool servers by *impersonating* an invoker service account — a deliberate, grantable, revocable relationship.

**Step 6.** The app got its own identity too.

**Step 7.** A gateway in the path. Deny-by-default. Per-tool policy. And destinations that must be registered to be reachable at all.

[BEAT]

At no point did we write a document saying what should be allowed.

At every point we changed what is **possible.**

That's what guardrails means here. Physics.

---

## 19:30 — Do and don't

**Do give every agent its own identity.** A shared service account destroys attribution and makes least privilege impossible.

**Don't confuse a policy document with enforcement.** If you can violate it without editing it, it isn't a control.

**Do scope policy per tool, not per server.** "May reach the licensing server" and "may call one read-only tool on it" are very different blast radii.

**Don't treat a gateway 403 as something to route around.** It's the guardrail reporting. Fix the policy or the registration. Never the guardrail.

**Do register everything you intend to be reachable.** Under deny-by-default, the registry *is* the allowlist.

**Don't debug a fresh gateway change in the first five minutes.** Propagation is real.

---

## 21:30 — Recap and hook

Governance is in the path now. Every hop is checked. Every agent is attributable. A misconfiguration fails loudly instead of quietly succeeding.

One step left.

We're going to *use* the thing. Four scenarios. Four different endings — and the same graph every time, driven entirely by data.

Then we look at the whole system through three lenses. And tear it all down.

See you there.
