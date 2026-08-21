# Step 8 — Run the Flows, Observability & Wrap-up

**Target runtime:** 20–24 min · **Lab section:** `Run the Flows, Observability & Wrap-up`

---

## 00:00 — Cold open

[SCREEN: the console's scenario picker, four options.]

Everything is built, secured and traced, so this step is where we stop building and start using it.

There are four scenarios, and each one ends differently: a signed contract, a hard block, a human-in-the-loop question, and a sourcing decision. The claim I'd like you to test as we go is that it's the same graph every time — same nodes, same edges, same agents, with nothing branching on a scenario id — and that the only thing changing is the data in the request. If that holds up, it tells you something useful about how the system is built.

---

## 01:30 — Opening the console

```bash
cd ~/vibeflix-audit
source ./env.sh
gcloud run services describe vibeflix-app --region "$REGION" --format 'value(status.url)'
```

[DO: open it.]

Above the chat box there's a scenario picker, and picking one only fills in the form. Every scenario sends the same request shape to the orchestrator, and only the values differ, which is the point: one graph, four outcomes, decided by data.

---

## 02:30 — What to watch during each run

Three things, every time.

The workflow graph, where nodes move from idle to running to done. When dispatch fans out you'll see three boxes light up simultaneously, which is the parallelism from Step 5 drawn live.

The tool LEDs, where each blink is a deterministic check firing on an MCP server, and now also a gateway decision that came back yes.

And the report, painted by the UI Renderer.

---

## 03:30 — Scenario one, the happy path

[DO: pick it, hit Run.]

A clean vendor and product clears the brand, pricing and vendor checks. Watch the fan-out send all three specialists off at once, the join wait for them, and contract finalize execute, giving you a contract id.

This is the boring scenario, and boring is the achievement. Four kinds of expertise applied consistently in under a minute, with a record of exactly which checks ran.

---

## 05:00 — Scenario two, the exclusivity block

[DO: pick it, and point out the diff — the market changes to North America.]

Two fields change, and that's all.

An exclusive partner holds that territory for that character and category, so vendor clearance blocks the deal. Look at the graph carefully, though, because brand style and deal pricing both still pass. Only vendor clearance is red.

That's the fan-out earning its keep. A sequential pipeline would stop at the first failure and tell the vendor one thing, whereas here they learn everything that's true about their deal in a single pass: the artwork is fine, the money is fine, and there's a contract in the way.

Notice also how specific the block is. It names a partner, a category and a contract expiry date, and all of that came out of a registry row through a deterministic tool. It's exactly the kind of fact you'd never want a model inferring from prose.

---

## 07:30 — Scenario three, onboarding and a human

[DO: pick it. Market becomes Europe, vendor becomes a name that isn't in the registry.]

This one behaves differently. The vendor lookup comes back not-found, so clearance can't proceed, and it does the right thing by stopping and asking you for the one field it can't work out for itself.

[SCREEN: the question in the console.]

Answer it and the run continues. The vendor gets onboarded, clearance hands off to legal over A2A, and legal executes the contract itself.

Two things are worth calling out here. The first is that this is the same conversation you had in the Dev UI back in Step 4, and here you can simply answer, because the console has a form and the state fields come from that form. Same agent, different transport, and a much better experience, which is a contrast worth having seen both halves of.

The second is where that question came from. Legal needed a safety-cert ID, and legal sits behind vendor clearance, which sits behind the orchestrator, which sits behind the app. That question travelled up three boundaries to reach you and your answer travelled back down through all of them. Human-in-the-loop across a distributed agent mesh is the hardest plumbing in this system, and it's why the shared task store in Step 5 mattered.

---

## 10:30 — Scenario four, over the volume cap

[DO: pick it. One field — volume goes to 40,000.]

One field changes this time.

All three guards pass, and then the orchestrator's own report step compares the volume against the authorized cap of 25,000 and stops for a sourcing decision: either split the excess into an addendum contract, or cap the volume and cancel the rest. Pick either one and the audit finishes with a contract.

What makes this scenario worth including is subtle. This pause is plain code in the graph — a number compared against a cap in a node — whereas scenario three's question came from a model that discovered it needed something. Two completely different mechanisms, and from the user's side they look identical, because in both cases the system stopped and asked.

That's a good property to aim for. Your users shouldn't be able to tell which of your pauses come from a model and which come from an if statement, and you should always know exactly which is which.

Answer it and the audit re-runs with all three compliance reports reused, so it doesn't redo work it has already done.

---

## 13:00 — Three views of one run

Now let's look at what happened from the outside, because the mesh has been emitting telemetry the whole time — every engine deploy turned it on.

There are three views, and each answers a different question.

Cloud Trace answers where the time went. Every request is one distributed trace whose spans stitch across the A2A hops and the MCP tool calls, so a single audit shows the orchestrator, the three specialists and their tools with timing, in one waterfall.

[SCREEN: the waterfall, with three overlapping spans.]

Look at the shape of it, because the three specialists' spans overlap, and that overlap is your proof the fan-out is real rather than three sequential calls with optimistic labelling.

Cloud Logging answers what a component said, and there's a trap here that costs people real time. The engines and the Cloud Run services log under different resource types: the six agents are reasoning engines, while the MCP servers and the app are Cloud Run revisions. Filter on the wrong one and an agent looks completely silent while it's logging perfectly well. If you take one operational fact away from this step, take that one.

Cloud Monitoring's topology answers what the system actually is, drawing the mesh as a graph built from aggregated traces. It's the architecture diagram from Step 1, drawn from real traffic.

That last one deserves a moment, because architecture diagrams describe what somebody meant, while a topology built from traces shows the calls that really happened. If there's an edge on it you didn't expect, you've found something.

One caveat: three APIs all need to be enabled, and with one of them off the topology comes back empty even though the agents are fine.

---

## 16:30 — Verifying telemetry

```bash
cd ~/vibeflix-audit
source ./env.sh
./deploy/verify/step8.sh
```

This confirms all six engines have telemetry on, trace propagation on, and the shared task store wired, which are three flags a deploy can drop silently. Silently is the operative word, because none of them failing produces an error — you just get less signal, or slower runs, with nothing to indicate why.

---

## 18:00 — What the four scenarios showed

Four things, one per scenario.

The same graph produced four different endings, driven by data alone.

A single blocking verdict stops the contract even when everything else passes.

Human-in-the-loop and an A2A handoff can both happen inside one run.

And a pause can come from an agent or from deterministic code, with the user unable to tell the difference, which is exactly right.

---

## 19:00 — What you built

[SCREEN: the full architecture, everything lit.]

Stepping back: three MCP tool servers, deterministic and IAM-gated. Six agents, each with its own identity. One console, acting as a thin client and hosting the shared task store. Governed by identity, gateway and registry, and observable end to end through trace, live telemetry and topology.

And the ideas underneath all of it: MCP, the split between deterministic and non-deterministic work, Skills, loop engineering, RAG, A2A handoffs, human-in-the-loop, the ADK graph and its fan-out, the shared task store, A2UI, and governance in the traffic path.

If you keep one sentence from all eight steps, make it this one. The model does the fuzzy work, ordinary code does the deciding, and governance sits in the traffic path. Every design decision in this system is that sentence applied at a different altitude.

---

## 21:00 — Tearing it down

The workshop leaves real, billable resources running, so when you're finished:

```bash
cd ~/vibeflix-audit
source ./env.sh
./deploy/destroy.sh
```

That removes the six engines, the app, the gateway, the registry entries, the Pub/Sub topic, the buckets, Firestore and the service accounts. Resources that are already gone get skipped, so it's safe to run again.

If the project was created purely for this workshop, the `--project` flag deletes the whole thing, which is the fastest and cleanest option.

Both of those are destructive and irreversible, and the script asks you to type the project id to confirm, so read what it says before you type.

There's one note that trips people up. Back in Step 7 there was a rule about never deleting an engine, and that rule was about redeploys, because deleting an engine mid-workshop orphans its identity and its grants. At teardown, deleting is exactly what you want.

---

## 22:30 — Where to go next

Three suggestions.

Re-read an agent's code now that you know the concepts, because the files that looked dense in Step 2 read very differently once you know what a Skill is and why the tool signature looks like a form.

Read the design docs in the repository, since the architecture notes and the shared library walkthrough go deeper than a workshop can.

And read the operational runbook if you want to run something like this beyond a workshop day.

Thanks for building this with me. You now have a mesh where six agents move real money and sign real contracts, and the interesting engineering was all in one question, asked over and over: which decisions are these agents allowed to make?

[SCREEN: the finished console, one last time.]
