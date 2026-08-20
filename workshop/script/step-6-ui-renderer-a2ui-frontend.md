# Step 6 — UI Renderer, A2UI, and the Frontend

**Target runtime:** 20–24 min · **Lab section:** `UI Renderer, A2UI, and the Frontend`

---

## 00:00 — Cold open

[SCREEN: three different audit results — a clean pass, a blocked exclusivity conflict, a question asking for a safety-cert ID. Three completely different shapes.]

Three audits. Three completely different results.

One is a clean report. One is a blocked deal with a conflicting contract to show. One isn't a result at all — it's a *question*, waiting for a human to answer it.

[BEAT]

Now: how many React components do you write for that?

The honest answer, if you go down the normal path, is *one per shape you can think of*, plus a fallback for the ones you couldn't, plus a new one every time an agent learns to say something new. It's a losing battle, and the losing gets worse as the system gets smarter.

This step is about not fighting it.

---

## 01:30 — A2UI: the agents generate the UI

The idea is called **A2UI** — agent to user interface — and it flips the direction.

Instead of the frontend anticipating every result shape, the **result decides the interface**. An agent looks at what the backend actually produced and emits a description of the UI to draw. The frontend's job shrinks to rendering components it's given.

[BEAT]

I want to be careful here, because "let the AI build the UI" is the kind of sentence that makes sensible engineers reach for the door. So let's be precise about what is and isn't happening.

The renderer does **not** emit HTML, or CSS, or JavaScript. It emits **components from a fixed schema** — a card, a table, a badge, a question with a set of options. The frontend knows how to draw each of those, and it draws nothing else.

So the space of possible UIs is bounded by the schema, not by the model's imagination. The model chooses *which* components and *what goes in them*. That's a much smaller, much safer job than "generate an interface".

---

## 03:30 — The UI Renderer is just another agent

[SCREEN: `agents/ui_renderer/`.]

Two things worth noticing about how it's built.

**It's an independent A2A agent**, exactly like the domain agents. Its own engine, called over A2A. The app talks to it the same way it talks to the orchestrator. It is not a library, not a function in the app — a peer.

**Its rendering procedure is a Skill** — the same pattern as deal pricing. It has **no tools**, and its instruction carries the A2UI component schema, so it emits the real wire format directly.

And here's a design decision worth pausing on: there's **no output schema** on the model call. A2UI blocks are a text format, so reliability comes from **validate-then-fallback** instead.

[BEAT]

That means: the renderer emits its panel, the app parses it, and if it doesn't validate, the app heals what it can and falls back to a plain rendering rather than showing nothing. The user always gets *something*.

That's the right shape for a presentation layer. A malformed panel should degrade to a plain report — not to a blank screen with a stack trace behind it. Contrast that with pricing, where a malformed answer must *fail*, loudly, rather than degrade. **Where you put the fallback depends on whether being approximately right is acceptable.** In a verdict it isn't. In a layout it is.

---

## 06:00 — The app is a thin client to two agents

[SCREEN: `browser ──► app ──A2A──► orchestrator` and `──A2A──► ui_renderer`.]

So what does the app actually do?

It runs the audit by calling the **orchestrator** over A2A. It turns reports into panels by calling the **UI renderer** over A2A. And it hosts the shared task store the engines read and write — which is the piece we set up in Step 5.

What it does **not** do is run any agent workflow itself. No fan-out, no reasoning, no business logic. It's a thin client and a piece of shared infrastructure.

That's why it runs pinned to a single instance — because it's the one component holding state everything else depends on.

---

## 07:30 — Deploy the UI Renderer

```bash
cd ~/vibeflix-audit
source ./env.sh
python deploy/deploy_agents_a2a.py ui_renderer
python deploy/collect_agent_identities.py
./deploy/grant_agent_access.sh ui-renderer
```

The sixth and final agent, deployed exactly like the other five.

[DO: start it. This is another few-minute wait — and this time there's a genuinely good use for it. Jump ahead to the local console run below.]

---

## 09:00 — The app's identity

```bash
cd ~/vibeflix-audit
source ./env.sh
./deploy/setup_app_iam.sh
```

The app runs as its own service account with its own least-privilege IAM. Same principle as every agent — but the list is different, because its job is different.

It needs to call the engines over A2A. It needs to read and write the shared task state — and **without that one, task-store reads fail and audits hang**, which is a confusing failure to debug from the outside. It needs to read the Firestore data it serves: the registries, the audit history, the task store. It needs to resolve engine URLs from the registry. It needs to store uploaded mock-ups. And it needs to publish its own events and consume the telemetry subscription.

That script grants exactly that set and creates the subscription.

---

## 10:30 — Build and deploy the app

```bash
cd ~/vibeflix-audit
source ./env.sh
./deploy/deploy_app.sh
```

It builds the frontend and API image, auto-resolves the engine A2A URLs and the three MCP URLs, and deploys to Cloud Run pinned to a single instance.

---

## 11:30 — The circular dependency, and how to break it

Here's a subtlety worth understanding properly, because the lesson generalises well beyond this workshop.

The engines need the **app's** URL, for the task store. But the app needed the **engines'** URLs first. That's a genuine circular dependency.

The obvious fix is a second pass: deploy the engines, deploy the app, then redeploy all six engines so they learn the URL. That works. It's what this workshop used to do.

[BEAT]

You don't have to — because **the URL is computable before the app exists**.

Cloud Run serves every service at two addresses. One is the hashed form that `gcloud run services describe` reports. The other is deterministic: the service name, your project number, the region. Just as live, and derivable from things you already know.

So the deploy script computes it during the first pass, and the engines are wired to the task store from the start. `TASK_STORE_URL` is only read at **run time**, so pointing at a service that doesn't exist yet is harmless — it just has to be up before you run an audit, which it now is.

[BEAT]

That's a habit worth taking with you: **when two components need each other's addresses, look for the one that's derivable rather than reaching for a second deployment pass.**

And note the contrast with Step 4. Engine ids are *not* derivable — Agent Runtime mints a random one — which is exactly why that step needs deploy-collect-deploy and this one doesn't. Knowing which of your identifiers are computable and which are assigned tells you where your deployment ordering constraints really are.

If the engines ever *do* log that they're falling back to the per-replica store, that's this wiring having failed — you're back to the 404 storm from Step 5, and redeploying the engines is the fix.

---

## 14:30 — Run the console locally first

Before checking the cloud deploy, let's drive the **whole thing on your own machine**.

```bash
cd ~/vibeflix-audit
source ./env.sh
./run_local.sh console
```

**No Docker build here.** This starts the same processes the `mesh` command has been starting since Step 4 — from your virtual environment, in seconds — and adds the two pieces mesh leaves out: the orchestrator, and the console app.

There's also an `up` command that runs the identical stack in containers. It builds seven images first, so it's the slow way to see the same thing.

It does need **application-default credentials**, because the agents call Gemini. If it warns that they're missing, run the login once and start again.

And `source ./env.sh` matters here specifically: it exports the Firestore database name, so the MCP servers read the registries you seeded in Step 1 rather than their built-in fallback data.

[DO: wait for every service to report ✓, then Web Preview → port 8000.]

---

## 17:00 — Watch a real audit

[SCREEN: the console.]

This is the real thing — the same app you just deployed to Cloud Run, running locally against local agents.

Pick the **happy path** scenario and hit Run.

[SCREEN: the graph animating.]

Four things to watch, and each one is a concept from an earlier step made visible.

**The graph lights up** as each specialist starts and finishes — brand style, vendor clearance and deal pricing running **in parallel**. That's the fan-out you drove by hand in Step 5.

**The MCP tool LEDs blink** as the deterministic checks fire. Those are the tool calls — the exact half of the work.

**The report is painted by the UI Renderer.** That's A2UI. The app didn't write that layout; an agent chose those components.

**The run ends with an executed contract.**

Try a second scenario while you're here — **exclusivity block** is the same request in North America, where a competitor holds the lock. One branch turns red, the others still pass, and no contract is issued.

[BEAT]

That's worth ten seconds of appreciation. One branch failing didn't take down the run, didn't hide the other results, and produced a specific reason rather than a generic error.

[DO: Ctrl+C to stop everything.]

What you just ran is the *local* mesh — processes talking over localhost. The engines you deployed to Agent Runtime were not involved. Step 8 runs the identical console against those, which is the only difference that matters between this and production.

---

## 20:00 — Verify

```bash
cd ~/vibeflix-audit
source ./env.sh
./deploy/verify/step6.sh
```

---

## 20:30 — Do and don't

**Do let results choose their own presentation** when the space of result shapes is open-ended. Hand-coding a panel per shape is a treadmill.

**Don't let a model emit raw markup.** A fixed component schema bounds what can possibly appear on screen.

**Do use validate-then-fallback in a presentation layer.** A degraded panel beats a blank screen.

**Don't use fallback in a decision layer.** A degraded verdict is worse than an error.

**Do keep the app a thin client.** The moment it starts doing business logic, it becomes a component your governance model didn't plan for.

**Don't add a deployment pass for a value you can compute.** Check whether the identifier is derivable first.

---

## 22:00 — Recap and bridge

You have a working product: six agents, three tool servers, and a console where a human can run an audit and read a result that an agent chose how to display.

And it is, right now, **almost entirely ungoverned**. Each agent has its own identity and its own IAM — that part's real. But there's no policy in the path. Nothing checks, per call, whether *this* agent is allowed to call *that* tool.

That's the last piece, and it's the whole reason this workshop is called Guardrails. Next step: identity, registry, and a deny-by-default gateway that sits in the traffic path and enforces per-tool policy.

See you there.
