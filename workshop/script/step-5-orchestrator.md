# Step 5 — The Orchestrator

**Target runtime:** 16–19 min · **Lab section:** `The Orchestrator`

---

## 00:00 — Cold open

[SCREEN: the workflow graph. One node fans out to three, then converges.]

Four agents so far, each doing its job when you talk to it directly. This step makes them a system, where one request arrives, three specialists work on it simultaneously in three engines, and something waits for all three before any decision gets made.

It's also where we hit the most instructive failure in the workshop: a bug that stays invisible during development, appears only under real conditions, and needs an architectural fix.

---

## 01:00 — The orchestrator is an ordinary agent

The orchestrator is an agent, deployed like the other four, with its own identity and engine, and the app calls it over A2A the same way it calls anything else. There's no privileged component with a back door, so when the gateway goes into the traffic path in Step 7, the orchestrator is subject to it like everything else.

---

## 01:45 — The graph

[SCREEN: `agents/orchestrator/agent.py`, the Workflow at the bottom.]

At the bottom of the file there's a Workflow, which is a directed graph.

Read the edges and you have the business process: ingest the request, dispatch it, run the three guards, merge their reports, self-heal anything malformed, compile the UI, generate the report, finalize the contract. Each name is a node defined above with a decorator.

You can read the business process straight off the code. When somebody asks what happens during an audit, you show them nine lines. That's what you give up the moment you let a model decide what happens next.

---

## 03:00 — Fan-out and join

[SCREEN: the tuple edge.]

An edge pointing at a tuple is a fan-out, so those three nodes run in parallel. A join node waits for all three.

They run in parallel because the checks are independent. Brand compliance has no bearing on pricing, and vendor clearance has no bearing on brand. Running them sequentially only makes the audit slower, and when each is a model-driven agent taking ten to twenty seconds, that's the difference between a demo you'd show and one you wouldn't.

They join because the decision needs all three verdicts before a contract can be finalized.

---

## 04:00 — The specialists are remote agents

[SCREEN: `_AGENTS[...]` and `_remote_agent(...)`.]

Each guard node calls a remote agent, the ADK stand-in for something running in another engine. One orchestrator run fans out into three simultaneous A2A calls to three separate engines.

The constructor never branches on transport. All three specialists are built the same way, and one boolean decides pacing.

[SCREEN: the long-running set.]

Brand style and deal pricing finish inside Agent Runtime's blocking ceiling of roughly 180 seconds, so they take the stock path. Vendor clearance can exceed it, because it fans out into legal's question loop, so it sends non-blocking and polls. Same class, same call site, one flag, so moving a hop across that ceiling costs a boolean.

---

## 05:30 — The bug

Every A2A call is two HTTP requests: a POST that starts the task and returns an id, then a GET on that id, polled until done. Agent Runtime runs each engine as several replicas with no session affinity.

[SCREEN: animate it. POST lands on replica A, task created in memory. GET is load-balanced, lands on replica B.]

The POST creates the task on replica A, in that replica's memory. The GET gets load-balanced and lands on replica B, which has never heard of it, so it returns a 404 for a task running perfectly well a few metres away.

With several replicas in play, most of your polls miss.

---

## 06:45 — Why it stays hidden

On your laptop it never happens, because one process and one task store mean every poll hits the right place. In a single-replica deployment it never happens either.

It appears when you scale, which means it appears in production, under load. It also presents as a timeout or a flaky agent, which sends you looking in the wrong place. In the real build of this system it accounted for twenty-six percent of every span in the traces.

The general lesson is older than agents. When you have a stateful handle plus a load balancer, ask where the state lives. If it lives in the memory of whichever instance answered first, you have this bug.

---

## 08:00 — The fix

Retrying plays the same game of chance again. The fix is moving task state somewhere every replica can see.

[SCREEN: the task store module.]

The engines are wired to a remote task store reading and writing through the app's Firestore-backed endpoints. The POST writes to Firestore, the GET reads from Firestore on whatever replica receives it, and affinity stops mattering.

The engines get that endpoint from a variable pointing at the app, which you deploy in Step 6, so until then a fan-out run falls back to per-replica memory and logs a loud warning. That's fine for a single-replica smoke test.

---

## 09:15 — Two kinds of memory

A session is the memory of one run. It holds everything that happened during this audit, which makes a human-in-the-loop resume possible and lets a run survive a replica dying halfway through.

A Memory Bank is memory across runs. It answers questions like what did we decide about this vendor last quarter. It's written once by the contract-finalize node and read by a responder agent when you type into the console's chat box.

---

## 10:00 — Deploy

```bash
cd ~/vibeflix-audit
source ./env.sh
python deploy/deploy_agents_a2a.py orchestrator
python deploy/collect_agent_identities.py
./deploy/grant_agent_access.sh orchestrator
```

Deploy this one last, because it auto-discovers the three specialists' A2A URLs from the identities file.

[DO: start it, then go to the local run.]

---

## 11:00 — Watching the fan-out

[DO: second tab — the whole local backend.]

```bash
cd ~/vibeflix-audit
source ./env.sh
export RUN_LOCAL=true
./run_local.sh mesh
```

Wait for all five agents to report a tick.

[DO: third tab — Dev UI on the orchestrator, with the three A2A URLs exported.]

Open Web Preview on port 8000, pick the orchestrator, and paste the request as one line of JSON.

---

## 12:00 — Why JSON

The ingest node accepts either form, and the natural-language path extracts the image link, the market and the volume, and nothing else.

Describe the vendor, character, category or pricing in prose and those fields go unextracted, so the agents ask you for them. A full audit has eleven fields, and JSON is how the console sends them, so these keys are the ones the console's API uses.

---

## 12:45 — Why these values clear

Every field dodges a block you've already met.

The image and the character have to agree, because brand style compares the artwork against the character under audit.

The medium is supplied because these files are character artwork. Left blank, brand style infers something like "artwork", which isn't on the approved list, so the audit comes back flagged.

Stitch, vinyl figures and North America carry no exclusivity lock, because stitch's lock covers Asia-Pacific. The vendor already makes vinyl figures in North America, so there's no onboarding and no legal handoff. The volume of 20,000 sits under the 25,000 cap. And the rate, advance and minimum guarantee clear what the card computes.

---

## 13:45 — Running it

[SCREEN: the Dev UI graph.]

Dispatch fans out to all three specialists in parallel, the merge node waits, and contract finalize executes the licensing contract, giving you a contract id.

Now change one field. Set the market to Asia-Pacific and the same request hits stitch's exclusivity lock in vendor clearance, while brand style and pricing still come back cleared. Or swap the image for the wrong character's artwork and only brand style fails.

One branch blocking leaves the others free to report. A sequential pipeline stops at the first failure and tells the vendor one thing, and when a deal has three problems they'd rather hear all three today than one a day for three days.

---

## 15:00 — Verify

[DO: Ctrl+C in both tabs.]

```bash
cd ~/vibeflix-audit
source ./env.sh
./deploy/verify/step5.sh
```

---

## 15:30 — Do and don't

Fan out work that's independent, because three ten-second agents in parallel take ten seconds.

If you only need the first result, you didn't need a join or a fan-out.

Put shared task state in shared storage. Once more than one replica can answer a poll, in-memory state is a bug waiting for traffic.

Don't fix replica roulette with retries, because you'll mask it and see it again later.

Keep the orchestrator ordinary, since a privileged coordinator is invisible to your governance.

---

## 16:15 — Where that leaves us

You have an orchestrator that fans out to three engines, joins their verdicts and finalizes a contract, with task state in Firestore so polls land regardless of which replica answers.

There's no way for a human to use it yet. Next we build the console, where the agents generate the interface, because the shape of a result isn't known until the result exists.

See you there.
