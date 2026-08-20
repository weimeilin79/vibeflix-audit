# Step 5 — The Orchestrator

**Target runtime:** 22–26 min · **Lab section:** `The Orchestrator`

---

## 00:00 — Cold open

[SCREEN: the workflow graph — one node fanning out to three, then converging.]

Four agents so far, each doing its own job when you talk to it directly.

This step is the one that makes them a system. One request comes in, and three specialists work on it **at the same time**, in three different engines, and something waits for all three before deciding anything.

[BEAT]

And along the way we're going to hit a bug that I think is the most instructive failure in this entire workshop — because it's invisible in development, it only appears under real conditions, and the fix is architectural rather than a patch.

---

## 01:30 — The orchestrator is just another agent

One thing to get straight up front, because it shapes everything.

The orchestrator is **not** a special coordinator service sitting above the mesh. It's an agent, deployed exactly like the other four, with its own identity and its own engine. The app calls it over A2A exactly like any other agent.

That's what makes the whole mesh uniformly governable later. There's no privileged component with a back door. In Step 7, when we put a gateway in the path, the orchestrator is subject to it like everything else.

---

## 02:30 — The graph

[SCREEN: `agents/orchestrator/agent.py`, the Workflow at the bottom.]

Open the orchestrator and go to the bottom of the file. There's a `Workflow` — a directed graph.

Read the edges out loud and you have the whole business process: ingest the request, dispatch it, run the three guards, merge their reports, self-heal anything that came back malformed, compile the UI, generate the report, finalize the contract.

Each of those names is a node defined just above with a decorator.

[BEAT]

I want to point at something about this that's easy to skate past. **You can read the business process off the code.** Not a diagram that drifts from the code — the code. When somebody asks "what happens during an audit", you show them nine lines.

That's a real benefit of declaring flow instead of writing it. And it's the thing you lose the moment you let a model decide what to do next.

---

## 04:30 — Fan-out and join

Two edges do the heavy lifting.

[SCREEN: the tuple edge — `(dispatch, (guard_brand, guard_clearance, guard_pricing))`.]

An edge to a **tuple** is a fan-out. All three run in parallel.

Then a **join node** waits for all of them. Not the fastest, not the first — all three.

Why parallel? Because these three checks are genuinely independent. Brand compliance doesn't depend on pricing. Vendor clearance doesn't depend on brand. Running them in sequence would just be slower for no benefit — and in a system where each one is a model-driven agent taking ten to twenty seconds, sequential is the difference between a demo you'd show and one you wouldn't.

Why join at all? Because the *decision* needs all three. A contract can't be finalized while one verdict is missing. The join is where "three independent opinions" becomes "one decision".

---

## 06:00 — The specialists are remote agents

[SCREEN: `_AGENTS[...]` and `_remote_agent(...)`.]

Look at how the guard nodes call the specialists. Each one is a **remote agent** — the ADK stand-in for something running in another engine, the ones you deployed in Steps 2 through 4.

So a single orchestrator run fans out into **three simultaneous A2A calls to three separate engines**.

Now look at what `_remote_agent` *doesn't* do: it never branches on transport. All three specialists are built with the same constructor. One boolean decides pacing.

[SCREEN: `_LONG_RUNNING_A2A = {"vendor_clearance_agent"}`.]

Brand style and deal pricing finish well inside Agent Runtime's roughly 180-second blocking ceiling, so they take the stock path. Vendor clearance can exceed it — it fans out into legal's multi-round question loop — so it sends non-blocking and polls instead.

Same class, same call site, one flag. **Moving a hop across that ceiling is a boolean, not a different client.** That's a design property worth copying.

---

## 08:00 — The bug: replica roulette

Right. Here's the failure I promised.

Every A2A call is two HTTP requests. First a POST that starts the task and returns a task id. Then a GET on that task id, polled until it's done.

Agent Runtime runs each engine as **several replicas**, with no session affinity.

[BEAT]

Do you see it?

[SCREEN: animate — POST lands on replica A, which creates the task in its own memory. GET is load-balanced to replica B. Replica B has never heard of that task.]

The POST creates the task on replica A, in memory. The GET is load-balanced — and lands on replica B, which has no idea what you're talking about.

**404. Task not found.** For a task that exists and is running perfectly well, three metres away, on a different replica.

And the odds are exactly as bad as they sound. With several replicas, most of your polls miss.

---

## 10:00 — Why this is invisible until it isn't

Here's what makes this bug genuinely nasty, and why I want you to sit with it.

**On your laptop, it never happens.** One process, one task store, every poll hits the right place. It works perfectly.

**In a single-replica deployment, it never happens.** Also fine.

It appears when you scale — which is to say, it appears in production, under load, at exactly the moment you least want a new class of failure. And it *looks* like a timeout or a flaky agent, not like an architecture problem.

In the real build of this system, this showed up in traces as a huge fraction of all spans being 404 polls. Twenty-six percent of every span in the system was this bug.

[BEAT]

The general lesson: **any time you have a stateful handle plus a load balancer, ask where the state lives.** If the answer is "in the memory of whichever instance answered first", you have this bug. It doesn't matter that it's agents — this is as old as web sessions.

---

## 12:00 — The fix: a shared task store

The fix is not to retry harder. Retrying just plays roulette again.

The fix is to move the task state somewhere **all replicas can see**.

[SCREEN: `packages/vibeflix-common/vibeflix_common/a2a/task_store.py`.]

The engines don't use ADK's default in-memory task store. They're wired to a remote task store that reads and writes through the app's Firestore-backed endpoints.

So the POST writes the task to Firestore. The GET — on whatever replica — reads it from Firestore. Affinity stops mattering.

[BEAT]

One consequence you need to know about now: the engines get that endpoint from an environment variable pointing at the **app**, which you deploy in Step 6. Until then, a fan-out run falls back to per-replica memory, with a loud warning. Fine for a single-replica smoke test. The real, fast, multi-replica run comes together once the app is up.

---

## 14:00 — Two kinds of memory

While we're here — the orchestrator introduces two memory concepts that people routinely confuse.

A **session** is the memory of **one run**. Everything that happened during this audit. It's what makes a human-in-the-loop resume possible, and it's what survives a replica dying mid-run.

A **Memory Bank** is memory **across runs**. It's how the console can answer "what did we decide about this vendor last quarter?" It's written once, by the contract-finalize node, and read by a responder agent when you type in the console's chat box.

Different lifetimes, different purposes. One run versus one organisation's history.

---

## 15:30 — Deploy the orchestrator

```bash
cd ~/vibeflix-audit
source ./env.sh
python deploy/deploy_agents_a2a.py orchestrator
python deploy/collect_agent_identities.py
./deploy/grant_agent_access.sh orchestrator
```

Deploy it last of the agents — it auto-discovers the three specialists' A2A URLs from `agent_identities.json`, which is exactly why we've been running `collect` after every deploy.

[DO: start it. Don't wait — go straight to the local run below and come back.]

---

## 17:00 — Watch the fan-out, locally

This is the first time you can see one request light up all three specialists at once.

[DO: second tab — the whole local backend.]

```bash
cd ~/vibeflix-audit
source ./env.sh
export RUN_LOCAL=true
./run_local.sh mesh
```

Wait for all five agents to report ✓.

[DO: third tab — the Dev UI on the orchestrator, with the three A2A URLs exported.]

Open it via Web Preview on port 8000, pick the orchestrator, and paste the request **as one line of JSON**.

[SCREEN: the JSON request.]

---

## 18:30 — Why JSON, when English also works

The ingest node accepts either. But the natural-language path is deliberately small: it pulls out the **image link**, the **market**, and the **volume** — and nothing else.

Describe the vendor, character, category or pricing in prose and those fields simply aren't extracted, so the agents do the sensible thing and ask you for them.

That's fine for a quick "audit this image", and worth trying once to see the difference. But a full audit has eleven fields, and JSON is how the console sends them. These keys are exactly the ones the console's API uses.

---

## 19:30 — Why these values clear

Nothing in that request is arbitrary. Each field dodges a block you've already met.

**The image and the character must agree.** Brand style looks at the artwork and compares. Point it at the Grogu mock-up while auditing stitch and you get a character mismatch.

**The medium is supplied on purpose.** These images are character *artwork*, not product mock-ups. Left blank, brand style infers something like "artwork" — which isn't on the approved list, so the audit gets flagged. Supplying it says what the product actually is.

**Stitch, vinyl figures, North America** — no exclusivity lock. Stitch's lock is in Asia-Pacific.

**VND-1007** already makes vinyl figures in North America, so no onboarding, no legal handoff, no approval question.

**Volume 20,000** is under the 25,000 sourcing cap.

**The rate, advance and MG** all clear what the card computes.

[BEAT]

Assembling a request that passes every guard is itself a good exercise — it forces you to hold the whole rule set in your head at once.

---

## 21:00 — Watch it run

[SCREEN: the Dev UI graph.]

Dispatch fans out to brand style, vendor clearance and deal pricing **in parallel**. The merge node waits for all three. Contract finalize executes the licensing contract — and you get a contract id in the final report.

**Now change one field and watch a single branch fail.**

Set the market to Asia-Pacific. The same request hits stitch's exclusivity lock in vendor clearance — while brand style and pricing still come back cleared.

Or swap the image and only *brand style* fails, on the character mismatch.

That's the fan-out doing its job. One branch blocking doesn't stop the others reporting, and the merge shows you all three verdicts side by side.

[BEAT]

Compare that to a sequential pipeline that stops at the first failure. You'd know one thing was wrong. Here you know *everything* that's wrong, in one pass. When a vendor's deal has three problems, they'd rather hear all three today than one a day for three days.

---

## 23:00 — Verify

[DO: Ctrl+C in both tabs, then verify.]

```bash
cd ~/vibeflix-audit
source ./env.sh
./deploy/verify/step5.sh
```

Confirms the orchestrator engine is deployed with an agent identity.

---

## 23:30 — Do and don't

**Do fan out work that's genuinely independent.** Three ten-second agents in parallel is ten seconds.

**Don't fan out and then use only the first result.** If you don't need all of them, you didn't need a join — and probably didn't need a fan-out.

**Do put shared task state in shared storage.** The moment more than one replica can answer a poll, in-memory state is a bug waiting for traffic.

**Don't debug replica roulette by adding retries.** You'll mask it, slow everything down, and it'll come back.

**Do keep the orchestrator an ordinary agent.** A privileged coordinator is a component your governance can't see.

**Don't confuse session memory with cross-run memory.** One run versus one history — different tools, different lifetimes.

---

## 25:00 — Recap and bridge

You have a real distributed system now: an orchestrator that fans out to three engines, joins their verdicts, and finalizes a contract — with task state in Firestore so that polls land regardless of which replica answers.

What you don't have is a way for a human to *use* it. Next step: the console. And the interesting part isn't the React — it's that **the agents generate the UI**. The report you see is painted by another agent, from a schema, because the shape of a result isn't known until the result exists.

See you there.
