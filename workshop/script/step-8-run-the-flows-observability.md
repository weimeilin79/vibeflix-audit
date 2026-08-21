# Step 8 — Run the Flows, Observability & Wrap-up

**Target runtime:** 20–24 min · **Lab section:** `Run the Flows, Observability & Wrap-up`

---

## 00:00 — Cold open

[SCREEN: the console's scenario picker. Four options.]

Everything is built. Secured. Traced.

Today we stop building and start using.

Four scenarios. Four completely different endings. A signed contract. A hard block. A human-in-the-loop question. And a sourcing decision.

[BEAT]

Here's the claim I want you testing as we go.

**It's the same graph every time.**

Same nodes. Same edges. Same agents. Nothing branches on a scenario id. The only thing that changes is the data in the request.

If that holds, it tells you something real about how this system is built.

---

## 01:30 — Open the console

```bash
cd ~/vibeflix-audit
source ./env.sh
gcloud run services describe vibeflix-app --region "$REGION" --format 'value(status.url)'
```

[DO: open it.]

Above the chat box there's a **scenario picker.** Picking one only fills in the form. Every scenario sends the same request shape to the orchestrator. Only the values differ.

One graph. Four outcomes. Decided by data.

---

## 02:30 — What to watch

Three things, every run.

**The graph.** Nodes go idle, running, done. When dispatch fans out, three boxes light up **at the same time.** That's the parallelism from Step 5, drawn live.

**The tool LEDs.** Each blink is a deterministic check firing. And now, also a gateway decision that came back yes.

**The report.** Painted by the UI Renderer.

---

## 03:30 — Scenario 1: happy path

[DO: pick it. Run.]

A clean vendor and product clears brand, pricing and vendor checks.

Watch the fan-out. All three at once. The join waits. Finalize executes. You get a contract id.

[BEAT]

This is the boring one. Boring is the achievement.

Four kinds of expertise, applied consistently, in under a minute — with a record of exactly which checks ran.

---

## 05:00 — Scenario 2: exclusivity block

[DO: pick it. Show the diff — market changes to North America.]

**Two fields change.** That's it.

An exclusive partner holds that territory for that character and category. Vendor clearance blocks it.

Now look at the graph carefully. **Brand style and deal pricing still pass.** Green. Only vendor clearance is red.

[BEAT]

That's the fan-out earning its keep.

A sequential pipeline stops at the first failure and tells you one thing. Here, the vendor gets told everything that's true about their deal, in one pass. The artwork is fine. The money is fine. There's a contract in the way.

And notice the block is **specific.** Not "rejected". A named partner. A named category. A contract expiry date.

That came out of a registry row, through a deterministic tool. Exactly the kind of fact you never want a model inferring from prose.

---

## 07:30 — Scenario 3: onboarding, and a human

[DO: pick it. Market → Europe. Vendor → a name not in the registry.]

This one's different.

The vendor lookup comes back not-found. Clearance can't proceed. And it does the right thing — it **stops and asks you** for the one field it can't work out.

[SCREEN: the question.]

Answer it. The run continues. The vendor gets onboarded. Clearance hands off to **legal over A2A.** And legal executes the contract itself.

[BEAT]

Two things to call out.

First — **this is the same conversation you had in the Dev UI in Step 4.** But here you can just answer. Because the console has a **form.** The state fields come from the form, not from your sentence.

Same agent. Different transport. Much better experience. Worth having seen both halves.

Second — look at *where* that question came from.

Legal needed a safety-cert ID. Legal sits behind vendor clearance. Which sits behind the orchestrator. Which sits behind the app.

That question travelled up three boundaries to reach you. And your answer travelled back down.

Human-in-the-loop across a distributed agent mesh is the hardest plumbing in this system. And it's why the shared task store in Step 5 mattered.

---

## 10:30 — Scenario 4: over the cap

[DO: pick it. One field — volume goes to 40,000.]

**One field changes.**

All three guards pass. Then the orchestrator's own report step compares the volume to the authorized cap of 25,000. And stops for a **sourcing decision.** Split the excess into an addendum contract, or cap and cancel it.

Pick either. Both finish with a contract.

[BEAT]

Here's what makes this scenario worth including. It's subtle.

**This pause is plain code in the graph.**

Scenario 3's question came from a model that discovered it needed something. This one comes from a deterministic comparison in a node. A number against a cap.

Two completely different mechanisms. And to the user, they look identical. The system stopped and asked.

That's a good property. **Your users shouldn't be able to tell which of your pauses are AI and which are `if` statements.** And you should always know exactly which is which.

Answer it, and the audit re-runs with all three compliance reports **reused.** It doesn't redo work it already did.

---

## 13:00 — Three views of one run

Now let's look at what just happened from the outside.

The mesh has been emitting telemetry this whole time. Every engine deploy turned it on.

Three views. Each answers a different question.

**Cloud Trace** answers *where did the time go?*

Every request is one distributed trace. Its spans stitch across A2A hops **and** MCP tool calls. One audit shows the orchestrator, the three specialists, and their tools — with timing — in a single waterfall.

[SCREEN: the waterfall. Three overlapping spans.]

And look at the shape. The three specialists' spans **overlap.**

That's your proof the fan-out is real — three calls genuinely overlapping in time.

**Cloud Logging** answers *what did this component say?*

And there's a trap here that costs people real time. The engines and the Cloud Run services log under **different resource types.** The six agents are reasoning engines. The MCP servers and the app are Cloud Run revisions.

Filter on the wrong one and an agent looks completely silent — while it's logging perfectly well.

If you take one operational fact from this step, take that one.

**Cloud Monitoring's topology** answers *what is this system, actually?*

It draws the mesh as a graph, built from aggregated traces. It's the architecture diagram from Step 1, drawn from real traffic.

[BEAT]

That last one deserves a moment.

Architecture diagrams lie. They describe what someone meant.

A topology built from traces cannot lie. It shows the calls that actually happened.

So if there's an edge on it you didn't expect — that's a discovery.

One caveat: three APIs all have to be on. With one off, the topology comes back empty even though the agents are fine.

---

## 16:30 — Verify telemetry

```bash
cd ~/vibeflix-audit
source ./env.sh
./deploy/verify/step8.sh
```

Confirms all six engines have telemetry on, trace propagation on, and the shared task store wired.

Three flags a deploy can silently drop.

**Silently** is the word. None of them failing produces an error. You just get less signal, or slower runs, and no clue why.

---

## 18:00 — What the four showed

Four things. One per scenario.

The **same graph** produced four endings, driven by data alone.

A **single blocking verdict** stops the contract even when everything else passes.

**Human-in-the-loop** and an **A2A handoff** can both happen inside one run.

And a pause can come from an **agent** or from **deterministic code** — and the user can't tell. Which is exactly right.

---

## 19:00 — What you built

[SCREEN: the full architecture, everything lit.]

Step back.

**Three MCP tool servers.** Deterministic. IAM-gated.

**Six agents.** Each with its own identity.

**One console.** A thin client, and host of the shared task store.

Governed by **identity, gateway and registry.** Observable through **trace, telemetry and topology.**

And the ideas underneath. MCP. Deterministic versus non-deterministic work. Skills. Loop engineering. RAG. A2A handoffs. Human-in-the-loop. The graph and the fan-out. The shared task store. A2UI. Governance in the path.

[BEAT]

If you remember one sentence from all eight steps, make it this one.

**The model does the fuzzy work. Code does the deciding. Governance sits in the path, not in a document.**

Every design decision in this system is that sentence, applied at a different altitude.

---

## 21:00 — Tear it down

This workshop leaves real, billable resources running. When you're finished:

```bash
cd ~/vibeflix-audit
source ./env.sh
./deploy/destroy.sh
```

It removes the six engines, the app, the gateway, the registry entries, the topic, the buckets, Firestore and the service accounts. Already-deleted resources get skipped, so it's safe to re-run.

If the project was created just for this workshop, the `--project` flag deletes the whole thing. Fastest and cleanest.

[BEAT]

Both are **destructive and irreversible.** The script asks you to type the project id. Read what it says before you type.

One note that trips people up. Back in Step 7 there was a rule about never deleting an engine. That was about *redeploys* — deleting an engine mid-workshop orphans its identity and its grants.

At teardown, deleting is exactly what you want.

---

## 22:30 — Where to go next

Three things.

**Re-read an agent's code now that you know the concepts.** The files that looked dense in Step 2 read completely differently once you know what a Skill is, and why the tool signature looks like a form.

**Read the design docs** in the repo. The architecture notes go deeper than a workshop can.

**And the operational runbook** — if you want to run something like this for real, not just for a day.

[BEAT]

Thanks for building this with me.

You now have a mesh where six agents move real money and sign real contracts.

And the interesting engineering was never about making them smart.

It was deciding, over and over, which decisions they were never allowed to make.

[SCREEN: the finished console, one last time.]
