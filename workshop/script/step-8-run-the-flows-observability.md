# Step 8 — Run the Flows, Observability & Wrap-up

**Target runtime:** 14–17 min · **Lab section:** `Run the Flows, Observability & Wrap-up`

---

## 00:00 — Cold open

[SCREEN: the console's scenario picker, four options.]

Everything is built, secured and traced, so this step uses it.

Four scenarios, each ending differently: a signed contract, a hard block, a human-in-the-loop question, and a sourcing decision. Test this claim as we go — it's the same graph every time, same nodes, same edges, same agents, with nothing branching on a scenario id, and only the data in the request changes.

---

## 00:45 — Opening the console

```bash
cd ~/vibeflix-audit
source ./env.sh
gcloud run services describe vibeflix-app --region "$REGION" --format 'value(status.url)'
```

[DO: open it.]

The scenario picker above the chat box only fills in the form. Every scenario sends the same request shape to the orchestrator, and only the values differ.

---

## 01:30 — What to watch

The workflow graph, where nodes move from idle to running to done. When dispatch fans out, three boxes light up simultaneously.

The tool LEDs, where each blink is a deterministic check firing on an MCP server, and now also a gateway decision that came back yes.

And the report, painted by the UI Renderer.

---

## 02:15 — Scenario one, the happy path

[DO: pick it, hit Run.]

A clean vendor and product clears the brand, pricing and vendor checks. The fan-out sends all three specialists off at once, the join waits, and contract finalize executes.

Four kinds of expertise applied consistently in under a minute, with a record of which checks ran.

---

## 03:15 — Scenario two, the exclusivity block

[DO: pick it, point out the diff — the market changes to North America.]

Two fields change.

An exclusive partner holds that territory for that character and category, so vendor clearance blocks the deal. Brand style and deal pricing both still pass, and only vendor clearance is red.

A sequential pipeline stops at the first failure and tells the vendor one thing. Here they learn everything true about their deal in one pass: the artwork is fine, the money is fine, and there's a contract in the way.

The block names a partner, a category and a contract expiry date, all of it from a registry row through a deterministic tool.

---

## 05:00 — Scenario three, onboarding and a human

[DO: pick it. Market becomes Europe, vendor becomes a name not in the registry.]

The vendor lookup comes back not-found, so clearance stops and asks you for the one field it can't work out.

[SCREEN: the question in the console.]

Answer it and the run continues. The vendor gets onboarded, clearance hands off to legal over A2A, and legal executes the contract.

This is the same conversation you had in the Dev UI in Step 4, and here you can answer directly, because the console has a form supplying the state fields. Same agent, different transport.

Legal needed a safety-cert ID, and legal sits behind vendor clearance, behind the orchestrator, behind the app. That question travelled up three boundaries and your answer travelled back down. It's the hardest plumbing in this system, and it's why the shared task store in Step 5 mattered.

---

## 07:00 — Scenario four, over the volume cap

[DO: pick it. One field — volume goes to 40,000.]

One field changes.

All three guards pass, then the orchestrator's report step compares the volume against the authorized cap of 25,000 and stops for a sourcing decision: split the excess into an addendum contract, or cap the volume and cancel the rest. Either finishes with a contract.

This pause is plain code in the graph, a number compared against a cap. Scenario three's question came from a model that discovered it needed something. Two mechanisms, and from the user's side they look identical.

Your users shouldn't be able to tell which pauses come from a model and which from an if statement, and you should always know which is which.

Answer it and the audit re-runs with all three compliance reports reused.

---

## 08:45 — Three views of one run

The mesh has been emitting telemetry throughout, since every engine deploy turned it on.

Cloud Trace answers where the time went. Every request is one distributed trace whose spans stitch across A2A hops and MCP tool calls, so one audit shows the orchestrator, the three specialists and their tools with timing, in one waterfall.

[SCREEN: the waterfall, with three overlapping spans.]

The three specialists' spans overlap, which is your proof the fan-out is real.

Cloud Logging answers what a component said, and there's a trap here. The engines and the Cloud Run services log under different resource types: the six agents are reasoning engines, and the MCP servers and app are Cloud Run revisions. Filter on the wrong one and an agent looks silent while it's logging normally.

Cloud Monitoring's topology answers what the system is, drawing the mesh from aggregated traces. Architecture diagrams describe what somebody meant, and a topology built from traces shows the calls that happened, so an unexpected edge on it is a finding.

Three APIs have to be enabled, and with one off the topology comes back empty even though the agents are fine.

---

## 10:45 — Verify telemetry

```bash
cd ~/vibeflix-audit
source ./env.sh
./deploy/verify/step8.sh
```

Confirms all six engines have telemetry on, trace propagation on, and the shared task store wired. None of those failing produces an error — you get less signal, or slower runs, with nothing indicating why.

---

## 11:30 — What the four scenarios showed

The same graph produced four endings, driven by data alone.

A single blocking verdict stops the contract even when everything else passes.

Human-in-the-loop and an A2A handoff can both happen inside one run.

A pause can come from an agent or from deterministic code, with the user unable to tell.

---

## 12:15 — What you built

[SCREEN: the full architecture, everything lit.]

Three MCP tool servers, deterministic and IAM-gated. Six agents, each with its own identity. One console, a thin client hosting the shared task store. Governed by identity, gateway and registry, observable through trace, live telemetry and topology.

And the ideas underneath: MCP, the split between deterministic and non-deterministic work, Skills, loop engineering, RAG, A2A handoffs, human-in-the-loop, the ADK graph and its fan-out, the shared task store, A2UI, and governance in the traffic path.

Keep one sentence from all eight steps. The model does the fuzzy work, code does the deciding, and governance sits in the traffic path.

---

## 13:15 — Teardown

```bash
cd ~/vibeflix-audit
source ./env.sh
./deploy/destroy.sh
```

Removes the six engines, the app, the gateway, the registry entries, the Pub/Sub topic, the buckets, Firestore and the service accounts. Already-deleted resources get skipped, so it's safe to re-run.

If the project was created for this workshop, the `--project` flag deletes the whole thing.

Both are destructive and irreversible, and the script asks you to type the project id, so read what it says first.

One note that trips people up. The Step 7 rule about never deleting an engine was about redeploys, because deleting one mid-workshop orphans its identity and grants. At teardown, deleting is what you want.

---

## 14:15 — Where to go next

Re-read an agent's code now that you know the concepts. The files that looked dense in Step 2 read differently once you know what a Skill is and why the tool signature looks like a form.

Read the design docs in the repository, which go deeper than a workshop can.

And read the operational runbook if you want to run this beyond a workshop day.

Thanks for building this with me. Six agents move real money and sign real contracts here, and the engineering was all in one question asked repeatedly: which decisions are these agents allowed to make?

[SCREEN: the finished console, one last time.]
