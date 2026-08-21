# Step 6 — UI Renderer, A2UI, and the Frontend

**Target runtime:** 20–24 min · **Lab section:** `UI Renderer, A2UI, and the Frontend`

---

## 00:00 — Cold open

[SCREEN: three audit results side by side — a clean pass, a blocked exclusivity conflict, a question waiting for an answer.]

Here are three audits that produced three completely different results. One is a clean report, one is a blocked deal with a conflicting contract to display, and the third is a question waiting for a human to answer it.

The question this raises is how many React components you write to cover that. Down the conventional path the answer is one per shape you can think of, plus a fallback for the shapes you couldn't, plus a new one every time an agent learns to say something new. It's a treadmill, and it gets worse as the system gets more capable.

This step is about getting off it.

---

## 01:30 — A2UI

The approach is called A2UI, for agent-to-user-interface, and it reverses the usual direction. Rather than the frontend anticipating every possible result shape, the result itself decides the interface: an agent looks at what the backend actually produced and emits a description of the UI to draw, and the frontend's job shrinks to rendering what it's handed.

The phrase "let the AI build the UI" tends to make sensible engineers reach for the door, so let me be exact about what happens here.

The renderer emits components drawn from a fixed schema — a card, a table, a badge, a question with a set of options — and the frontend knows how to draw each of those and nothing else. So the schema bounds the space of possible interfaces, and the model's job is choosing which components to use and what goes inside them. That's a much smaller and much safer job than generating an interface from scratch.

---

## 03:30 — The renderer is another agent

[SCREEN: the ui_renderer folder.]

Two things about how it's built are worth noticing.

It's an independent A2A agent with its own engine, called over A2A, and the app talks to it exactly the way it talks to the orchestrator. It's a peer in the mesh rather than a library the app imports.

Its rendering procedure is a Skill, which is the same pattern as deal pricing. It has no tools, and its instruction carries the A2UI component schema, so it emits the real wire format directly.

There's also a design decision here worth pausing on, which is that the model call has no output schema attached. A2UI blocks are a text format, so reliability comes from validating and falling back instead. The renderer emits a panel, the app parses it, and if it fails to validate the app heals what it can and falls back to a plain rendering, so the user always gets something on screen.

That's the right arrangement for a presentation layer, where a malformed panel degrading into a plain report is a good outcome. Pricing works the opposite way, because a malformed answer there has to fail loudly. Where you put a fallback depends on whether being approximately right is acceptable, and in a verdict it never is, while in a layout it usually is.

---

## 06:00 — The app is a thin client

[SCREEN: browser → app → orchestrator, and app → ui_renderer.]

So what does the app itself actually do?

It runs the audit by calling the orchestrator over A2A. It turns reports into panels by calling the renderer over A2A. And it hosts the shared task store that the engines read and write, which is the piece we set up in Step 5.

Every workflow runs somewhere else, so the app stays a thin client plus one piece of shared infrastructure. That's also why it runs pinned to a single instance, since it's the one component holding state that everything else depends on.

---

## 07:30 — Deploying the renderer

```bash
cd ~/vibeflix-audit
source ./env.sh
python deploy/deploy_agents_a2a.py ui_renderer
python deploy/collect_agent_identities.py
./deploy/grant_agent_access.sh ui-renderer
```

This is the sixth and final agent, deployed exactly like the other five.

[DO: start it. There's a genuinely good use for this wait — jump ahead to the local console run below.]

---

## 09:00 — The app's identity

```bash
cd ~/vibeflix-audit
source ./env.sh
./deploy/setup_app_iam.sh
```

The app runs as its own service account with its own least-privilege IAM, on the same principle as every agent, though the list of permissions is different because its job is different.

It needs to call the engines over A2A. It needs to read and write the shared task state, and missing that one causes task-store reads to fail and audits to hang, which is a confusing thing to debug from the outside. It needs to read the Firestore data it serves, which means the registries, the audit history and the task store. It needs to resolve engine URLs from the registry, store uploaded mock-ups, and publish its own events while consuming the telemetry subscription.

That script grants exactly that set and creates the subscription.

---

## 10:30 — Deploying the app

```bash
cd ~/vibeflix-audit
source ./env.sh
./deploy/deploy_app.sh
```

It builds the frontend and API image, auto-resolves the engine A2A URLs and the three MCP URLs, and deploys to Cloud Run pinned to a single instance.

---

## 11:30 — The circular dependency

There's a subtlety here worth getting right, and the lesson generalises well beyond this workshop.

The engines need the app's URL for the task store, and the app needed the engines' URLs before it could be deployed, which is a genuine circular dependency.

The obvious resolution is a second pass: deploy the engines, deploy the app, then redeploy all six engines so they learn the URL. That works, and this workshop used to do exactly that.

It turns out to be unnecessary, because the URL is computable before the app exists. Cloud Run serves every service at two addresses. One is the hashed form that `gcloud run services describe` reports, and the other is deterministic, built from the service name, your project number and the region. Both are equally live, and the second is derivable from things you already know.

So the deploy script computes it during the first pass and the engines are wired to the task store from the start. The value is only read at run time, so pointing at a service that doesn't exist yet does no harm, and it only has to be running before you execute an audit, which by then it is.

The habit worth taking away is that when two components need each other's addresses, it's worth checking whether one of them is derivable before you reach for a second deployment pass. The contrast with Step 4 is instructive, because engine ids are assigned randomly by Agent Runtime and can't be predicted, which is exactly why that step needs deploy-collect-deploy while this one doesn't. Knowing which of your identifiers are computable and which are assigned tells you where your real ordering constraints are.

If the engines ever do log that they're falling back to the per-replica store, that's this wiring having failed, which puts you back in the 404 storm from Step 5, and redeploying the engines is the fix.

---

## 14:30 — Running the whole product locally

Before we check the cloud deploy, let's drive the entire thing on your own machine.

```bash
cd ~/vibeflix-audit
source ./env.sh
./run_local.sh console
```

This starts the same processes the mesh command has been starting since Step 4, from your virtual environment, in seconds, and adds the two pieces the mesh leaves out: the orchestrator and the console app. There's also an `up` command that runs the identical stack in containers, which builds seven images first and is therefore the slow way to see the same thing.

It does need application-default credentials, because the agents call Gemini from your machine, so if it warns that they're missing, log in once and start again.

Sourcing the env file matters here specifically, because it exports the Firestore database name, which is what makes the MCP servers read the registries you seeded in Step 1 rather than their built-in fallback data.

[DO: wait for every service to report a tick, then Web Preview → port 8000.]

---

## 17:00 — Watching a real audit

[SCREEN: the console.]

This is the same app you just deployed to Cloud Run, running locally against local agents.

Pick the happy path scenario and hit Run, and there are four things to watch, each of which is a concept from an earlier step becoming visible.

The graph lights up as each specialist starts and finishes, with brand style, vendor clearance and deal pricing running in parallel, which is the fan-out you drove by hand in Step 5.

The MCP tool LEDs blink as the deterministic checks fire, which is the exact half of the work happening.

The report gets painted by the UI Renderer, which is A2UI in action, since the app didn't write that layout and an agent chose those components.

And the run ends with an executed contract.

Try a second scenario while you're here. The exclusivity block is the same request in North America, where a competitor holds the lock, and one branch turns red while the others still pass and no contract is issued. That's worth a few seconds of appreciation, because one branch failed, the run carried on, the other two verdicts still came back, and the vendor got a specific reason they can act on.

[DO: Ctrl+C to stop everything.]

What you just ran is the local mesh, with processes talking to each other over localhost, and the engines you deployed to Agent Runtime played no part in it. Step 8 runs the identical console against those engines, which is the only difference that matters between this and production.

---

## 20:00 — Verifying

```bash
cd ~/vibeflix-audit
source ./env.sh
./deploy/verify/step6.sh
```

---

## 20:30 — Do and don't

Let results choose their own presentation when the space of result shapes is genuinely open-ended, because hand-coding a panel per shape is a treadmill.

Keep the model to a fixed component schema, which bounds what can possibly appear on screen.

Use validate-then-fallback in a presentation layer, where a degraded panel beats a blank screen.

Keep that pattern out of a decision layer, where a degraded verdict is worse than an error.

Keep the app a thin client, because as soon as it starts doing business logic it becomes a component your governance model didn't plan for.

And check whether an identifier is derivable before you add a deployment pass for it.

---

## 22:00 — Where that leaves us

You have a working product: six agents, three tool servers, and a console where a human runs an audit and reads a result that an agent chose how to display.

It's also almost entirely ungoverned at this point. Every agent has its own identity and its own IAM, which is real, but there's no policy sitting in the traffic path, and nothing checks on a per-call basis whether a particular agent is allowed to call a particular tool.

That's the last piece, and it's the whole reason this workshop is called Guardrails. Next we add identity, registry and a deny-by-default gateway that sits in the path and refuses anything outside policy.

See you there.
