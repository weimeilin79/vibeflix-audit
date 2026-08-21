# Step 5 — The Orchestrator

**Target runtime:** 22–26 min · **Lab section:** `The Orchestrator`

---

## 00:00 — Cold open

[SCREEN: the workflow graph. One node fans out to three, then converges.]

We have four agents so far, and each of them does its job when you talk to it directly. This step turns them into a system, where one request arrives and three specialists work on it simultaneously in three different engines, and something waits for all three of them before any decision gets made.

Along the way we run into a bug that I think is the most instructive failure in the whole workshop. It stays invisible during development, appears only under real conditions, and the fix for it is architectural rather than a patch.

---

## 01:30 — The orchestrator is an ordinary agent

One thing to establish up front, because it shapes everything else.

The orchestrator is an agent, deployed exactly like the other four, with its own identity and its own engine, and the app calls it over A2A the same way it calls anything else. That's what makes the whole mesh uniformly governable later, since there's no privileged component with a back door into the system. When we put a gateway in the traffic path in Step 7, the orchestrator is subject to it like everything else.

---

## 02:30 — The graph

[SCREEN: `agents/orchestrator/agent.py`, the Workflow at the bottom.]

Open the orchestrator and scroll to the bottom of the file, where you'll find a Workflow, which is a directed graph.

If you read the edges out loud you get the entire business process: ingest the request, dispatch it, run the three guards, merge their reports, self-heal anything that came back malformed, compile the UI, generate the report and finalize the contract. Each of those names is a node defined just above with a decorator.

That's worth appreciating for a moment, because it means you can read the business process straight off the code rather than off a diagram that has drifted away from it. When somebody asks what happens during an audit, you show them nine lines. That's the benefit of declaring the flow, and it's the thing you give up the moment you let a model decide what happens next.

---

## 04:30 — Fan-out and join

Two edges do the heavy lifting here.

[SCREEN: the tuple edge.]

An edge pointing at a tuple is a fan-out, so all three of those nodes run in parallel. A join node then waits for all three of them to finish.

The reason to run them in parallel is that these checks are genuinely independent of each other. Brand compliance has no bearing on pricing, and vendor clearance has no bearing on brand. Running them one after another would only make the audit slower, and when each one is a model-driven agent taking ten to twenty seconds, that's the difference between a demo you'd show someone and one you wouldn't.

The reason to join is that the decision needs all three verdicts before a contract can be finalized. The join is where three independent opinions become one decision.

---

## 06:00 — The specialists are remote agents

[SCREEN: `_AGENTS[...]` and `_remote_agent(...)`.]

Look at how the guard nodes call the specialists. Each one is a remote agent, which is the ADK stand-in for something running in another engine, and those are the engines you deployed in Steps 2 through 4. So a single orchestrator run fans out into three simultaneous A2A calls to three separate engines.

Now look at what the constructor does, and specifically at what it avoids doing. It never branches on transport. All three specialists are built with the same constructor, and a single boolean decides pacing.

[SCREEN: the long-running set.]

Brand style and deal pricing both finish well inside Agent Runtime's blocking ceiling of roughly 180 seconds, so they take the stock path. Vendor clearance can exceed it, because it fans out into legal's multi-round question loop, so it sends non-blocking and polls instead. Same class, same call site, one flag, which means moving a hop across that ceiling costs you a boolean. That's a design property worth copying.

---

## 08:00 — The bug

Here's the failure I promised.

Every A2A call is two HTTP requests. First a POST that starts the task and returns a task id, and then a GET on that id, polled until the task is done. Agent Runtime runs each engine as several replicas, with no session affinity between them.

[SCREEN: animate it. POST lands on replica A, task created in memory. GET is load-balanced, lands on replica B.]

The POST creates the task on replica A, in that replica's memory. The GET gets load-balanced and lands on replica B, which has never heard of the task you're asking about, so it returns a 404 saying the task doesn't exist — for a task that exists and is running perfectly well a few metres away on a different machine.

The odds are as bad as they sound. With several replicas in play, most of your polls miss.

---

## 10:00 — Why it stays hidden

What makes this one nasty is where it doesn't happen.

On your laptop it never happens, because there's one process and one task store, so every poll hits the right place and everything works. In a single-replica deployment it never happens either. It appears when you scale, which means it appears in production, under load, at the moment you'd least like a new class of failure.

It also doesn't announce itself as an architecture problem. It looks like a timeout, or a flaky agent. In the real build of this system it showed up in traces as an enormous share of all spans — twenty-six percent of every span in the system was this bug.

The general lesson is older than agents. Any time you have a stateful handle combined with a load balancer, ask where that state lives, and if the answer is that it lives in the memory of whichever instance happened to answer first, you have this bug. Web sessions have had the same problem for decades.

---

## 12:00 — The fix

Retrying harder achieves nothing here, because a retry just plays the same game of chance again. The fix is to move the task state somewhere every replica can see.

[SCREEN: the task store module.]

The engines are wired to a remote task store that reads and writes through the app's Firestore-backed endpoints, rather than to ADK's default in-memory store. The POST writes the task to Firestore, the GET reads it from Firestore on whatever replica happens to receive it, and affinity stops being something you need.

There's one consequence you need to know about now. The engines get that endpoint from a variable pointing at the app, which you deploy in Step 6, so until then a fan-out run falls back to per-replica memory and logs a loud warning about it. That's fine for a single-replica smoke test, and the real multi-replica behaviour arrives once the app is up.

---

## 14:00 — Two kinds of memory

While we're here, there are two memory concepts in this system that people routinely conflate.

A session is the memory of one run. It holds everything that happened during this particular audit, which is what makes a human-in-the-loop resume possible and what lets a run survive a replica dying halfway through.

A Memory Bank is memory across runs. It's how the console can answer a question like what did we decide about this vendor last quarter. It gets written once, by the contract-finalize node, and read by a responder agent whenever you type into the console's chat box.

Different lifetimes, and different purposes: one run, against one company's history.

---

## 15:30 — Deploying it

```bash
cd ~/vibeflix-audit
source ./env.sh
python deploy/deploy_agents_a2a.py orchestrator
python deploy/collect_agent_identities.py
./deploy/grant_agent_access.sh orchestrator
```

Deploy this one last of the agents, because it auto-discovers the three specialists' A2A URLs from the identities file, which is exactly why we've been running collect after every deploy.

[DO: start it, then go straight to the local run below.]

---

## 17:00 — Watching the fan-out

This is the first point in the workshop where you can watch one request light up all three specialists at once.

[DO: second tab — the whole local backend.]

```bash
cd ~/vibeflix-audit
source ./env.sh
export RUN_LOCAL=true
./run_local.sh mesh
```

Wait for all five agents to report a tick.

[DO: third tab — Dev UI on the orchestrator, with the three A2A URLs exported.]

Open it through Web Preview on port 8000, pick the orchestrator, and paste the request as a single line of JSON.

---

## 18:30 — Why JSON rather than a sentence

The ingest node accepts either form, and the natural-language path is deliberately small. It extracts the image link, the market and the volume, and that's the whole of it.

If you describe the vendor, character, category or pricing in prose, those fields go unextracted, so the agents do the sensible thing and ask you for them. That behaviour is fine for a quick request to audit an image, and it's worth trying once to see the difference. A full audit has eleven fields, though, and JSON is how the console sends them, so these keys are exactly the ones the console's API uses.

---

## 19:30 — Why these particular values clear

Every field in that request has been chosen to dodge a block you've already met.

The image and the character have to agree, because brand style looks at the artwork and compares it against the character under audit. Point it at the wrong character's mock-up and you get a mismatch.

The medium is supplied deliberately, because these files are character artwork. Leave it blank and brand style infers something like "artwork", which isn't on the approved list, so the audit comes back flagged.

Stitch, vinyl figures and North America together carry no exclusivity lock, because stitch's lock covers Asia-Pacific. The vendor already manufactures vinyl figures in North America, so there's no onboarding and no legal handoff. The volume of 20,000 sits under the 25,000 sourcing cap. And the rate, advance and minimum guarantee all clear what the rate card computes.

Assembling a request that passes every guard is a decent exercise in itself, because it forces you to hold the whole rule set in your head at once.

---

## 21:00 — Running it

[SCREEN: the Dev UI graph.]

Dispatch fans out to brand style, vendor clearance and deal pricing in parallel, the merge node waits for all three, and contract finalize executes the licensing contract, giving you a contract id in the final report.

Now change one field and watch a single branch fail. Set the market to Asia-Pacific and the same request hits stitch's exclusivity lock in vendor clearance, while brand style and pricing still come back cleared. Or swap the image for the wrong character's artwork and only brand style fails, on the mismatch.

That's the fan-out doing its job, because one branch blocking leaves the others free to report. Compare that to a sequential pipeline that stops at the first failure, where you'd learn about one problem. Here you learn about everything that's wrong in a single pass, and when a vendor's deal has three problems they'd much rather hear all three today than one a day for three days.

---

## 23:00 — Verifying

[DO: Ctrl+C in both tabs.]

```bash
cd ~/vibeflix-audit
source ./env.sh
./deploy/verify/step5.sh
```

---

## 23:30 — Do and don't

Fan out work that's genuinely independent, because three ten-second agents running in parallel take ten seconds.

If you only need the first result back, you didn't need a join, and you probably didn't need a fan-out either.

Put shared task state in shared storage. As soon as more than one replica can answer a poll, in-memory state is a bug waiting for traffic to find it.

Resist fixing replica roulette with retries, because you'll mask it, slow everything down, and see it again later.

Keep the orchestrator ordinary, since a privileged coordinator is a component your governance can't see.

And keep session memory and cross-run memory clearly separated in your head.

---

## 25:00 — Where that leaves us

You have a real distributed system now: an orchestrator that fans out to three engines, joins their verdicts and finalizes a contract, with task state in Firestore so that polls land regardless of which replica answers them.

What's missing is any way for a human to use it. The next step builds the console, and the interesting part is the way the agents generate the interface. The report you see gets painted by another agent, because the shape of a result isn't known until the result exists.

See you there.
