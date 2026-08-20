# Step 6 — UI Renderer, A2UI, and the Frontend

**Target runtime:** 20–24 min · **Lab section:** `UI Renderer, A2UI, and the Frontend`

---

## 00:00 — Cold open

[SCREEN: three audit results side by side — a clean pass, a blocked exclusivity conflict, a question waiting for an answer.]

Three audits. Three completely different results.

One is a clean report. One is a blocked deal, with a conflicting contract to show. And one isn't a result at all — it's a *question*, waiting for a human.

[BEAT]

So. How many React components do you write for that?

Go down the normal path and the answer is: one per shape you can think of. Plus a fallback for the ones you couldn't. Plus a new one every time an agent learns to say something new.

It's a treadmill. And it gets worse as the system gets smarter.

Today we stop running.

---

## 01:30 — A2UI

The idea is called **A2UI**. Agent to user interface. It flips the direction.

Instead of the frontend guessing every possible result shape — **the result decides the interface.** An agent looks at what the backend produced, and emits a description of the UI to draw.

The frontend's job shrinks to rendering what it's handed.

[BEAT]

Now, "let the AI build the UI" is the kind of sentence that makes sensible engineers reach for the door. So let's be exact about what is and isn't happening.

The renderer does **not** emit HTML. Or CSS. Or JavaScript.

It emits **components from a fixed schema.** A card. A table. A badge. A question with options. The frontend knows how to draw each of those, and it draws nothing else.

So the space of possible UIs is bounded by the schema. Not by the model's imagination.

The model picks *which* components, and *what goes in them*. That's a much smaller job than "generate an interface." And a much safer one.

---

## 03:30 — Just another agent

[SCREEN: the ui_renderer folder.]

Two things about how it's built.

**It's an independent A2A agent.** Own engine. Called over A2A. The app talks to it exactly like it talks to the orchestrator. Not a library. Not a function. A peer.

**Its procedure is a Skill** — same pattern as deal pricing. No tools. Its instruction carries the component schema, so it emits the real wire format directly.

And here's a design call worth stopping on. There's **no output schema** on the model call. A2UI blocks are a text format. So reliability comes from **validate-then-fallback** instead.

[BEAT]

Meaning: the renderer emits a panel. The app parses it. If it doesn't validate, the app heals what it can and falls back to a plain rendering.

The user always gets *something*.

That's the right shape — for a presentation layer. A malformed panel should degrade to a plain report. Not to a blank screen with a stack trace behind it.

Now contrast that with pricing. There, a malformed answer must **fail**. Loudly. Never degrade.

**Where you put the fallback depends on whether being approximately right is acceptable.** In a verdict, it isn't. In a layout, it is.

---

## 06:00 — The app is a thin client

[SCREEN: browser → app → orchestrator, and app → ui_renderer.]

So what does the app actually do?

It runs the audit by calling the **orchestrator** over A2A. It turns reports into panels by calling the **renderer** over A2A. And it hosts the shared task store the engines read and write — the piece from Step 5.

What it does **not** do is run any agent workflow itself. No fan-out. No reasoning. No business logic.

Thin client, plus one piece of shared infrastructure.

Which is why it runs pinned to a single instance. It's the one component holding state that everything else depends on.

---

## 07:30 — Deploy the renderer

```bash
cd ~/vibeflix-audit
source ./env.sh
python deploy/deploy_agents_a2a.py ui_renderer
python deploy/collect_agent_identities.py
./deploy/grant_agent_access.sh ui-renderer
```

Sixth and final agent. Deployed exactly like the other five.

[DO: start it. Another few-minute wait — and this time there's a great use for it. Jump ahead to the local console run.]

---

## 09:00 — The app's identity

```bash
cd ~/vibeflix-audit
source ./env.sh
./deploy/setup_app_iam.sh
```

The app runs as its own service account, with its own least-privilege IAM. Same principle as every agent. Different list, because its job is different.

It calls the engines over A2A. It reads and writes shared task state — **and without that one, task-store reads fail and audits hang.** That's a nasty one to debug from outside.

It reads the Firestore data it serves. Resolves engine URLs from the registry. Stores uploaded mock-ups. Publishes its own events and consumes the telemetry subscription.

That script grants exactly that set, and creates the subscription.

---

## 10:30 — Deploy the app

```bash
cd ~/vibeflix-audit
source ./env.sh
./deploy/deploy_app.sh
```

Builds the frontend and API image. Auto-resolves the engine URLs and the three MCP URLs. Deploys to Cloud Run, pinned to one instance.

---

## 11:30 — The circular dependency

Here's a subtlety worth getting right. The lesson travels well beyond this workshop.

The engines need the **app's** URL, for the task store. But the app needed the **engines'** URLs first.

That's a real circular dependency.

The obvious fix is a second pass. Deploy the engines. Deploy the app. Then redeploy all six engines so they learn the URL.

That works. It's what this workshop used to do.

[BEAT]

You don't have to. Because **the URL is computable before the app exists.**

Cloud Run serves every service at two addresses. One is the hashed form that `describe` reports. The other is deterministic — service name, project number, region.

Just as live. And derivable from things you already know.

So the deploy script computes it on the first pass, and the engines are wired to the task store from the start. The URL is only read at **run time**, so pointing at a service that doesn't exist yet is harmless. It just has to be up before you run an audit. Which it now is.

[BEAT]

Take this one with you: **when two components need each other's addresses, look for the one that's derivable — before you reach for a second deployment pass.**

And notice the contrast with Step 4. Engine ids are *not* derivable. Agent Runtime mints a random one. That's exactly why that step needs deploy-collect-deploy and this one doesn't.

Knowing which identifiers are computable and which are assigned tells you where your real ordering constraints are.

If the engines ever *do* log that they're falling back to the per-replica store — that's this wiring having failed. You're back to the 404 storm from Step 5. Redeploy the engines.

---

## 14:30 — Run the whole thing locally

Before we check the cloud deploy — let's drive the **entire product** on this machine.

```bash
cd ~/vibeflix-audit
source ./env.sh
./run_local.sh console
```

**No Docker build here.** This starts the same processes the mesh command has been starting since Step 4 — from your virtual environment, in seconds — plus the two pieces the mesh leaves out. The orchestrator, and the console app.

There's also an `up` command that runs the identical stack in containers. It builds seven images first. Slow way to see the same thing.

It does need **application-default credentials**, because the agents call Gemini. If it warns they're missing, log in once and start again.

And `source ./env.sh` matters here specifically. It exports the Firestore database name — so the MCP servers read the registries you seeded in Step 1, not their built-in fallback data.

[DO: wait for every service to report ✓. Web Preview → port 8000.]

---

## 17:00 — Watch a real audit

[SCREEN: the console.]

This is the real thing. Same app you just deployed to Cloud Run. Running locally, against local agents.

Pick the **happy path** scenario. Hit Run.

[SCREEN: the graph animating.]

Four things to watch. Each one is a concept from an earlier step, made visible.

**The graph lights up** as each specialist starts and finishes. Brand style, vendor clearance, deal pricing — **in parallel.** That's the fan-out you drove by hand in Step 5.

**The MCP tool LEDs blink** as the deterministic checks fire. Those are the exact half of the work.

**The report is painted by the UI Renderer.** That's A2UI. The app didn't write that layout. An agent chose those components.

**And the run ends with an executed contract.**

Try a second one — **exclusivity block.** Same request, North America, where a competitor holds the lock. One branch turns red. The others still pass. No contract.

[BEAT]

Give that ten seconds of appreciation. One branch failed. It didn't take down the run. It didn't hide the other results. And it produced a specific reason, not a generic error.

[DO: Ctrl+C.]

What you just ran is the *local* mesh. Processes talking over localhost. The engines you deployed to Agent Runtime were not involved at all.

Step 8 runs the identical console against those. That's the only difference that matters between this and production.

---

## 20:00 — Verify

```bash
cd ~/vibeflix-audit
source ./env.sh
./deploy/verify/step6.sh
```

---

## 20:30 — Do and don't

**Do let results choose their own presentation** when result shapes are open-ended.

**Don't let a model emit raw markup.** A fixed component schema bounds what can appear on screen.

**Do use validate-then-fallback in a presentation layer.** A degraded panel beats a blank screen.

**Don't use fallback in a decision layer.** A degraded verdict is worse than an error.

**Do keep the app a thin client.** The moment it does business logic, it's a component your governance didn't plan for.

**Don't add a deployment pass for a value you can compute.**

---

## 22:00 — Recap and hook

You have a working product. Six agents. Three tool servers. A console where a human runs an audit and reads a result an agent chose how to display.

And right now, it is **almost entirely ungoverned.**

Every agent has its own identity and its own IAM — that part's real. But there's no policy in the path. Nothing checks, per call, whether *this* agent may call *that* tool.

That's the last piece. It's the whole reason this workshop is called Guardrails.

Next: identity, registry, and a deny-by-default gateway that sits in the traffic path and says no.

See you there.
