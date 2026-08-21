# Step 5 — The Orchestrator

**Target runtime:** 22–26 min · **Lab section:** `The Orchestrator`

---

## 00:00 — Cold open

[SCREEN: the workflow graph. One node fans out to three. Then converges.]

Four agents so far. Each one does its job when you talk to it.

Today they become a system.

One request comes in. Three specialists work on it **at the same time**, in three different engines. And something waits for all three before deciding anything.

[BEAT]

And along the way we hit a bug that I think is the most instructive failure in this whole workshop.

It's invisible in development. It only shows up under real conditions. And you cannot patch your way out of it.

---

## 01:30 — The orchestrator is just another agent

One thing straight up front, because it shapes everything.

The orchestrator is an agent, deployed like the other four. Own identity. Own engine. The app calls it over A2A exactly like anything else.

That's what makes the whole mesh governable later. There's no privileged component with a back door. In Step 7, when the gateway goes in the path, the orchestrator is subject to it like everyone else.

---

## 02:30 — The graph

[SCREEN: `agents/orchestrator/agent.py`, the Workflow at the bottom.]

Open the orchestrator. Go to the bottom of the file.

There's a `Workflow`. A directed graph.

Read the edges out loud and you have the entire business process. Ingest the request. Dispatch it. Run the three guards. Merge their reports. Self-heal anything malformed. Compile the UI. Generate the report. Finalize the contract.

[BEAT]

Catch what that means.

**You can read the business process straight off the code.**

Somebody asks "what happens during an audit?" — you show them nine lines.

That's the real benefit of declaring flow instead of writing it. And it's exactly what you lose the moment you let a model decide what happens next.

---

## 04:30 — Fan-out and join

Two edges do the heavy lifting.

[SCREEN: the tuple edge.]

An edge to a **tuple** is a fan-out. All three run in parallel.

Then a **join** waits for all three of them. Every one.

Why parallel? Because these checks are genuinely independent. Brand compliance doesn't depend on pricing. Vendor clearance doesn't depend on brand.

Running them in sequence is just slower for nothing. And when each one is a model-driven agent taking ten to twenty seconds, sequential is the difference between a demo you'd show and one you wouldn't.

Why join? Because the *decision* needs all three. You can't finalize a contract with a verdict missing.

The join is where three independent opinions become one decision.

---

## 06:00 — The specialists are remote

[SCREEN: `_AGENTS[...]` and `_remote_agent(...)`.]

Look at how the guard nodes call the specialists. Each is a **remote agent** — the stand-in for something running in another engine.

So one orchestrator run fans out into **three simultaneous A2A calls, to three separate engines.**

Now look at what the constructor *doesn't* do. It never branches on transport. All three are built the same way. One boolean decides pacing.

[SCREEN: the long-running set.]

Brand style and deal pricing finish well inside Agent Runtime's 180-second ceiling. They take the stock path. Vendor clearance can blow past it — it fans out into legal's question loop — so it sends non-blocking and polls.

Same class. Same call site. One flag.

**Moving a hop across that ceiling costs you one boolean.** Worth copying.

---

## 08:00 — The bug

Right. Here's the failure I promised.

Every A2A call is two HTTP requests. A POST that starts the task and returns an id. Then a GET on that id, polled until it's done.

Agent Runtime runs each engine as **several replicas.** No session affinity.

[BEAT]

Do you see it yet?

[SCREEN: animate it. POST lands on replica A. Task created in memory. GET is load-balanced — lands on replica B.]

The POST creates the task on replica A. In memory.

The GET gets load-balanced. And lands on replica B.

Replica B has never heard of this task.

[BEAT]

**404. Task not found.**

For a task that exists. That's running perfectly well. Three metres away. On a different replica.

And the odds are exactly as bad as they sound. Several replicas — most of your polls miss.

---

## 10:00 — Why it hides

Here's what makes this one genuinely nasty.

**On your laptop, it never happens.** One process. One task store. Every poll hits the right place. Works perfectly.

**In a single-replica deployment, it never happens.** Also fine.

It appears when you scale. Which is to say — it appears in production, under load, at exactly the moment you least want a new class of failure.

And it doesn't look like an architecture problem. It looks like a timeout. Or a flaky agent.

In the real build of this system, this showed up in traces as a huge share of every span. Twenty-six percent of all spans in the system were this bug.

[BEAT]

Here's the general lesson, and it's older than agents.

**Any time you have a stateful handle plus a load balancer — ask where the state lives.**

If the answer is "in the memory of whichever instance answered first", you have this bug. It doesn't matter that these are agents. This is as old as web sessions.

---

## 12:00 — The fix

Retrying harder just plays roulette again.

The fix is to move the task state somewhere **every replica can see.**

[SCREEN: the task store module.]

The engines don't use the default in-memory task store. They're wired to a remote one, reading and writing through the app's Firestore-backed endpoints.

POST writes the task to Firestore. GET — on whatever replica — reads it from Firestore.

Affinity stops mattering.

[BEAT]

One consequence you need now. The engines get that endpoint from a variable pointing at the **app**, which you deploy in Step 6.

Until then, a fan-out run falls back to per-replica memory, with a loud warning. Fine for a single-replica smoke test. The real multi-replica run comes together once the app is up.

---

## 14:00 — Two kinds of memory

While we're here. Two memory concepts people constantly confuse.

A **session** is the memory of **one run.** Everything that happened during this audit. It's what makes a human-in-the-loop resume possible, and what survives a replica dying mid-run.

A **Memory Bank** is memory **across runs.** It's how the console answers "what did we decide about this vendor last quarter?" Written once by the finalize node. Read by a responder agent when you type in the chat box.

Different lifetimes. One run, versus one company's history.

---

## 15:30 — Deploy

```bash
cd ~/vibeflix-audit
source ./env.sh
python deploy/deploy_agents_a2a.py orchestrator
python deploy/collect_agent_identities.py
./deploy/grant_agent_access.sh orchestrator
```

Deploy it last. It auto-discovers the three specialists' URLs from the identities file — which is exactly why we've been running collect after every deploy.

[DO: start it. Don't wait. Go straight to the local run.]

---

## 17:00 — Watch the fan-out

First time you can see one request light up all three specialists at once.

[DO: second tab — the whole local backend.]

```bash
cd ~/vibeflix-audit
source ./env.sh
export RUN_LOCAL=true
./run_local.sh mesh
```

Wait for all five agents to report ✓.

[DO: third tab — Dev UI on the orchestrator, with the three A2A URLs exported.]

Open Web Preview on 8000. Pick the orchestrator. And paste the request **as one line of JSON.**

---

## 18:30 — Why JSON, when English works too

The ingest node takes either. But the plain-English path is deliberately small. It pulls out the **image link**, the **market**, and the **volume**. Nothing else.

Describe the vendor, character, category or pricing in prose, and those fields don't get extracted. So the agents do the sensible thing and ask you for them.

That's fine for a quick "audit this image". Try it once — it's instructive.

But a full audit has eleven fields. And JSON is how the console sends them. These keys are exactly the ones the console's API uses.

---

## 19:30 — Why these values clear

Nothing in that request is arbitrary. Every field dodges a block you've already met.

**The image and the character have to agree.** Brand style looks at the artwork and compares. Point it at the wrong character's mock-up and you get a mismatch.

**The medium is supplied on purpose.** These are character *artwork* files, not product mock-ups. Leave it blank and brand style infers something like "artwork" — which isn't on the approved list. Flagged.

**Stitch, vinyl figures, North America** — no exclusivity lock. Stitch's lock is in Asia-Pacific.

**This vendor** already makes vinyl figures in North America. No onboarding. No legal handoff.

**Volume 20,000** is under the 25,000 cap.

**The rate, advance and MG** all clear what the card computes.

[BEAT]

Building a request that passes every guard is a decent exercise by itself. It forces you to hold the whole rule set in your head at once.

---

## 21:00 — Run it

[SCREEN: the Dev UI graph.]

Dispatch fans out. Brand style, vendor clearance, deal pricing — **in parallel.** The merge node waits for all three. Finalize executes the contract. You get a contract id.

**Now change one field and watch a single branch fail.**

Set the market to Asia-Pacific. Same request now hits stitch's exclusivity lock in vendor clearance — while brand style and pricing still come back cleared.

Or swap the image, and only *brand style* fails, on the character mismatch.

That's the fan-out doing its job. One branch blocking doesn't stop the others reporting.

[BEAT]

Compare that to a sequential pipeline that stops at the first failure. You'd know one thing was wrong.

Here you know *everything* that's wrong. In one pass.

When a vendor's deal has three problems, they'd rather hear all three today than one a day for three days.

---

## 23:00 — Verify

[DO: Ctrl+C both tabs.]

```bash
cd ~/vibeflix-audit
source ./env.sh
./deploy/verify/step5.sh
```

---

## 23:30 — Do and don't

**Do fan out work that's genuinely independent.** Three ten-second agents in parallel is ten seconds.

**Don't fan out and then use only the first result.** If you don't need all of them, you didn't need a join.

**Do put shared task state in shared storage.** The moment more than one replica can answer a poll, in-memory state is a bug waiting for traffic.

**Don't fix replica roulette with retries.** You'll mask it, slow everything down, and it comes back.

**Do keep the orchestrator ordinary.** A privileged coordinator is a component your governance can't see.

**Don't confuse session memory with cross-run memory.**

---

## 25:00 — Recap and hook

You have a real distributed system. An orchestrator that fans out to three engines, joins their verdicts, finalizes a contract — with task state in Firestore so polls land no matter which replica answers.

What you don't have is a way for a human to use it.

Next: the console. And the interesting part isn't the React.

**The agents generate the UI.** The report you see is painted by another agent — because the shape of a result isn't known until the result exists.

See you there.
