# Step 8 — Run the Flows, Observability & Wrap-up

**Target runtime:** 20–24 min · **Lab section:** `Run the Flows, Observability & Wrap-up`

---

## 00:00 — Cold open

[SCREEN: the console's scenario picker, four options.]

Everything is built, secured and traced. This step is the one where we stop building and start *using*.

Four scenarios. Four completely different endings — a signed contract, a hard block, a human-in-the-loop question, and a sourcing decision.

[BEAT]

And here's the claim I want you to test as we go: **it's the same graph every time.** Same nodes, same edges, same agents. Nothing branches on a scenario id. The only thing that differs is the data in the request.

If that holds, it tells you something important about how this system is built.

---

## 01:30 — Open the console

```bash
cd ~/vibeflix-audit
source ./env.sh
gcloud run services describe vibeflix-app --region "$REGION" --format 'value(status.url)'
```

[DO: open the URL.]

Above the chat box there's a **scenario picker**. Picking one only fills in the form. Every scenario sends the same request shape to the orchestrator — only the field values differ.

That's the point. One graph, four outcomes, decided entirely by the data.

---

## 02:30 — What to watch while each runs

Three things, in every run.

**The workflow graph.** Nodes go from idle to running to done. When dispatch fans out, you'll see three boxes light up **at the same time** — that's the parallelism from Step 5, drawn live.

**The tool LEDs.** Each one is a deterministic check firing on an MCP server. Every blink is also, now, a gateway decision that came back yes.

**The report.** Painted by the UI Renderer, not written by the app.

---

## 03:30 — Scenario 1: the happy path

[DO: pick it, hit Run.]

A clean vendor and product clears brand, pricing and vendor checks.

Watch the fan-out. All three specialists go at once. The join waits. Contract finalize executes, and you get a contract id.

[BEAT]

This is the boring one, and boring is the achievement. Four kinds of expertise, applied consistently, in under a minute, with a record of exactly which checks ran.

---

## 05:00 — Scenario 2: the exclusivity block

[DO: pick it. Point out the diff — market changes to North America.]

**Two fields change.** That's it.

An exclusive partner holds the territory for this character and category, so vendor clearance blocks it.

Now look carefully at the graph: **brand style and deal pricing still pass.** Their branches are green. Only vendor clearance is red.

[BEAT]

That's the fan-out earning its keep. A sequential pipeline would have stopped at the first failure and told you one thing. Here the vendor gets told everything that's true about their deal in one pass — the artwork is fine, the money is fine, and there's a contract in the way.

And notice the block is **specific**. Not "rejected". A named partner, a named category, a contract expiry date. That came out of a registry row via a deterministic tool — exactly the kind of fact you never want a model inferring from prose.

---

## 07:30 — Scenario 3: onboarding, and a human in the loop

[DO: pick it. Market → Europe, vendor → a name that isn't in the registry.]

This one's different. The vendor lookup comes back not-found, so clearance can't proceed — and it does the right thing: it **stops and asks you** for the one field it can't work out.

[SCREEN: the question in the console.]

Answer it, and the run continues: the vendor gets onboarded, clearance hands off to **legal over A2A**, and legal executes the contract itself.

[BEAT]

Two things worth calling out here.

First, **this is the same conversation you had in the Dev UI in Step 4** — but here you can just answer, because the console has a **form**. The state fields come from the form rather than from your sentence. Same agent, different transport, much better experience. That contrast is a genuinely useful thing to have seen both halves of.

Second, look at *where* the question came from. Legal needed a safety-cert ID. Legal is behind vendor clearance, which is behind the orchestrator, which is behind the app. That question travelled up three boundaries to reach you, and your answer travelled back down.

Human-in-the-loop across a distributed agent mesh is not a checkbox. It's the hardest plumbing in this system, and it's why the shared task store in Step 5 mattered.

---

## 10:30 — Scenario 4: over the volume cap

[DO: pick it. One field — volume goes to 40,000.]

**One field changes.**

All three guards pass. And then the orchestrator's own report step compares the volume against the authorized cap of 25,000, and stops for a **sourcing decision**: split the excess to an addendum contract, or cap and cancel the excess.

Pick either. Both finish with a contract.

[BEAT]

Here's what makes this scenario worth including, and it's subtle.

**This pause is plain code in the graph. Not an agent asking.**

Scenario 3's question came from a model that discovered it needed something. This one comes from a deterministic comparison in a node — a number against a cap. Two completely different mechanisms, and to the user they look identical: the system stopped and asked.

That's a good property. **Your users shouldn't be able to tell which of your pauses are AI and which are `if` statements** — and you should always know exactly which is which.

Answer it, and the audit re-runs with all three compliance reports **reused**. It doesn't redo work it already did.

---

## 13:00 — Observability: three views of one run

[BEAT]

Now let's look at what just happened from the outside. The mesh has been emitting telemetry this whole time — every engine deploy turned it on.

There are three views, and each answers a different question.

**Cloud Trace** answers *where did the time go?* Every request is one distributed trace, whose spans stitch across A2A hops **and** MCP tool calls. One audit shows the orchestrator, the three specialists, and their tools, with timing, in a single waterfall.

[SCREEN: the trace waterfall — three overlapping spans.]

And look at the shape of it. The three specialists' spans **overlap**. That's your proof the fan-out is real, not three sequential calls with optimistic labelling.

**Cloud Logging** answers *what did this component say?* And there's a trap here that costs people real time: the engines and the Cloud Run services log under **different resource types**. The six agents are reasoning engines. The MCP servers and the app are Cloud Run revisions.

Filter on the wrong one and an agent looks completely silent while it's logging perfectly well. If you take one operational fact from this step, take that one.

**Cloud Monitoring's topology** answers *what is this system, actually?* It draws the mesh as a graph, built from aggregated traces. It's the architecture diagram from Step 1 — except drawn from real traffic rather than from someone's intentions.

[BEAT]

That last one is worth dwelling on. Architecture diagrams lie, because they describe what someone meant. A topology built from traces cannot lie — it shows the calls that actually happened. If there's an edge on it you didn't expect, that's not a diagram error. That's a discovery.

One caveat: three APIs all have to be enabled. With one off, the topology comes back empty even though the agents are fine.

---

## 16:30 — Verify telemetry

```bash
cd ~/vibeflix-audit
source ./env.sh
./deploy/verify/step8.sh
```

This confirms all six engines have telemetry on, trace propagation on, and the shared task store wired — the three flags a deploy can silently drop that would leave you blind or slow.

**Silently** is the operative word. None of those three failing produces an error. You just get less signal, or slower runs, and no indication why.

---

## 18:00 — What the four scenarios showed

Four things, one per scenario.

The **same graph** produced four different endings, driven by data alone.

A **single blocking verdict** stops the contract even when everything else passes.

**Human-in-the-loop** and an **A2A handoff** can both happen inside one run.

And a pause can come from an **agent** or from **deterministic code** — and the user can't tell, which is exactly right.

---

## 19:00 — What you built

[SCREEN: the full architecture, all layers lit.]

Step back and look at the whole thing.

**Three MCP tool servers**, deterministic and IAM-gated. **Six agents**, each with its own identity. **One console**, a thin client and the host of the shared task store. Governed by **identity, gateway and registry**. Observable end to end through **trace, live telemetry and topology**.

And the concepts underneath: MCP. Deterministic versus non-deterministic work. Skills. Loop engineering. RAG. A2A handoffs. Human-in-the-loop. The ADK graph and fan-out. The shared task store. A2UI. And enterprise governance in the path.

[BEAT]

If you remember one sentence from all eight steps, make it this one:

**The model does the fuzzy work. Deterministic code does the deciding. Governance sits in the path, not in a document.**

Every design decision in this system is that sentence, applied at a different altitude.

---

## 21:00 — Tear it down

The workshop leaves real, billable resources running. When you're finished:

```bash
cd ~/vibeflix-audit
source ./env.sh
./deploy/destroy.sh
```

It removes the six engines, the app, the gateway, the registry entries, the Pub/Sub topic, the buckets, Firestore and the service accounts. Already-deleted resources are skipped, so it's safe to re-run.

If the project was created just for this workshop, the fastest and cleanest option is the `--project` flag, which deletes the whole thing.

[BEAT]

Both are **destructive and irreversible**. The script asks you to type the project id to confirm — read what it says before you type.

And one note that trips people up: back in Step 7 there was a rule about never deleting an engine. That was about *redeploys* — deleting an engine mid-workshop orphans its identity and its grants. At teardown, deleting is exactly what you want.

---

## 22:30 — Where to go next

Three suggestions.

**Re-read an agent's code now that you know the concepts.** The files that looked dense in Step 2 read very differently once you know what a Skill is and why the tool signature looks like a form.

**Read the design docs** in the repo — the architecture notes and the shared library walkthrough go deeper than a workshop can.

**And the operational runbook**, if you want to run something like this for real rather than for a day.

[BEAT]

Thanks for building this with me. You now have a mesh where six agents move real money and sign real contracts — and where the interesting engineering wasn't making them smart. It was deciding, over and over, which decisions they were never allowed to make.

[SCREEN: the finished console, one last time.]
