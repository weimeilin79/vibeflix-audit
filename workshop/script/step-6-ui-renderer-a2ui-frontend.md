# Step 6 — UI Renderer, A2UI, and the Frontend

**Target runtime:** 14–17 min · **Lab section:** `UI Renderer, A2UI, and the Frontend`

---

## 00:00 — Cold open

[SCREEN: three audit results side by side — a clean pass, a blocked exclusivity conflict, a question waiting for an answer.]

Three audits, three different results. A clean report, a blocked deal with a conflicting contract to display, and a question waiting for a human.

How many React components cover that? Down the conventional path it's one per shape you can think of, plus a fallback for the ones you couldn't, plus a new one every time an agent learns to say something new. It gets worse as the system gets more capable.

---

## 01:00 — A2UI

A2UI turns that around. The result decides the interface. An agent looks at what the backend produced and emits a description of the UI to draw, and the frontend renders what it's handed.

The renderer works from a fixed schema of components. A card, a table, a badge, a question with options. The frontend draws those and nothing else, so the schema bounds the space of possible interfaces, and the model's job is choosing which components to use and what goes in them.

---

## 02:00 — The renderer is another agent

[SCREEN: the ui_renderer folder.]

It's an independent A2A agent with its own engine, and the app talks to it the way it talks to the orchestrator. It's a peer in the mesh.

Its rendering procedure is a Skill, the same pattern as deal pricing. It has no tools, and its instruction carries the A2UI component schema, so it emits the real wire format.

The model call has no output schema attached, because A2UI blocks are a text format. Reliability comes from validating and falling back instead. The renderer emits a panel, the app parses it, and when it fails to validate the app heals what it can and falls back to a plain rendering, so the user always gets something.

That's right for a presentation layer, where a malformed panel degrading into a plain report is a good outcome. Pricing works the opposite way, because a malformed answer there has to fail loudly. Where you put a fallback depends on whether being approximately right is acceptable.

---

## 03:30 — The app is a thin client

[SCREEN: browser → app → orchestrator, and app → ui_renderer.]

The app runs the audit by calling the orchestrator over A2A, turns reports into panels by calling the renderer over A2A, and hosts the shared task store the engines read and write.

Every workflow runs somewhere else, so the app stays a thin client plus one piece of shared infrastructure. That's why it runs pinned to a single instance, since it holds state everything else depends on.

---

## 04:30 — Deploying the renderer

```bash
cd ~/vibeflix-audit
source ./env.sh
python deploy/deploy_agents_a2a.py ui_renderer
python deploy/collect_agent_identities.py
./deploy/grant_agent_access.sh ui-renderer
```

The sixth and final agent.

[DO: start it, then jump ahead to the local console run.]

---

## 05:30 — The app's identity

```bash
cd ~/vibeflix-audit
source ./env.sh
./deploy/setup_app_iam.sh
```

The app runs as its own service account with its own least-privilege IAM, on the same principle as every agent.

It calls the engines over A2A. It reads and writes shared task state, and missing that one causes task-store reads to fail and audits to hang. It reads the Firestore data it serves, resolves engine URLs from the registry, stores uploaded mock-ups, and publishes its own events while consuming the telemetry subscription.

---

## 06:30 — Deploying the app

```bash
cd ~/vibeflix-audit
source ./env.sh
./deploy/deploy_app.sh
```

It builds the frontend and API image, auto-resolves the engine A2A URLs and the three MCP URLs, and deploys to Cloud Run pinned to one instance.

---

## 07:00 — The circular dependency

The engines need the app's URL for the task store, and the app needed the engines' URLs before it could deploy.

The obvious resolution is a second pass. Deploy the engines, deploy the app, redeploy all six engines so they learn the URL. This workshop used to do exactly that.

None of it is necessary, because the URL is computable before the app exists. Cloud Run serves every service at two addresses. One is the hashed form that `describe` reports. The other is deterministic, built from the service name, project number and region. Both are live, and the second one is derivable from what you already know.

So the deploy script computes it during the first pass and the engines are wired from the start. The value is read at run time, so pointing at a service that doesn't exist yet does no harm, and it only has to be running before you execute an audit.

When two components need each other's addresses, check whether one is derivable before adding a deployment pass. Engine ids are assigned randomly by Agent Runtime and can't be predicted, which is why Step 4 needs deploy-collect-deploy and this one doesn't.

If the engines ever log that they're falling back to the per-replica store, this wiring has failed and you're back in the 404 storm from Step 5. Redeploy the engines.

---

## 09:00 — Running the whole product locally

```bash
cd ~/vibeflix-audit
source ./env.sh
./run_local.sh console
```

This starts the same processes the mesh command has started since Step 4, from your virtual environment, plus the orchestrator and the console app. There's also an `up` command that runs the identical stack in containers, which builds seven images first.

It needs application-default credentials, because the agents call Gemini from your machine.

Sourcing the env file matters here, because it exports the Firestore database name. With it, the MCP servers read the registries you seeded in Step 1 instead of their fallback data.

[DO: wait for every service to report a tick, then Web Preview → port 8000.]

---

## 10:30 — Watching a real audit

[SCREEN: the console.]

Same app you deployed to Cloud Run, running locally against local agents.

Pick the happy path and hit Run. Four things to watch.

The graph lights up as each specialist starts and finishes, with all three running in parallel.

The MCP tool LEDs blink as the deterministic checks fire.

The report gets painted by the UI Renderer, so an agent chose those components.

And the run ends with an executed contract.

Try the exclusivity block too. It's the same request in North America, where a competitor holds the lock. One branch turns red while the others pass, and no contract is issued. The run carried on, the other two verdicts came back, and the vendor got a specific reason.

[DO: Ctrl+C to stop everything.]

That was the local mesh, with processes talking over localhost. The engines you deployed to Agent Runtime played no part in it. Step 8 runs the identical console against those.

---

## 12:30 — Verify

```bash
cd ~/vibeflix-audit
source ./env.sh
./deploy/verify/step6.sh
```

---

## 13:00 — Do and don't

Let results choose their own presentation when result shapes are open-ended.

Keep the model to a fixed component schema, which bounds what can appear on screen.

Use validate-then-fallback in a presentation layer, where a degraded panel beats a blank screen.

Keep that pattern out of a decision layer, where a degraded verdict is worse than an error.

Keep the app a thin client.

Check whether an identifier is derivable before adding a deployment pass for it.

---

## 14:00 — Where that leaves us

Six agents, three tool servers, and a console where a human runs an audit and reads a result an agent chose how to display.

Every agent has its own identity and its own IAM, and no policy sits in the traffic path. Nothing checks, per call, whether a particular agent may call a particular tool.

Next comes identity, the registry, and a deny-by-default gateway that refuses anything outside policy.

See you there.
