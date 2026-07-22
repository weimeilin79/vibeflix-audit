# Step 6 — UI Renderer, A2UI, and the Frontend

You have a working brain — five agents that reason and a coordinator that runs them. Now you'll
give it a face. This step deploys the **console app** (the frontend + the shared task store) and
introduces the agent that generates the UI: the **UI Renderer**, speaking **A2UI**.

## 💡 Concept — A2UI: the UI is generated, not hand-built

A normal app has **static forms**: a developer decides in advance "show a text box here, a table
there." But an audit's result is *not* fixed — one run flags a brand issue, another blocks on
exclusivity, another needs a safety-cert ID from the user. Hand-coding a panel for every possible
shape is a losing battle.

**A2UI (Agent-to-User Interface)** flips it: an **agent generates the UI** based on what the
backend agents actually produced. The result decides the interface, not the other way around.

## 📝 Look — the UI Renderer is just another agent

Open `agents/ui_renderer/agent.py`. Its docstring says it plainly:

> *"The orchestrator … returns raw domain reports. This agent turns those (varied,
> non-deterministic) reports into user-friendly panels. It's served over A2A."*

Two things worth noticing:

- It's an **independent A2A agent**, exactly like the domain agents — its own engine, called over
  A2A. The app talks to it the same way it talks to the orchestrator.
- Its **rendering procedure is a Skill** (`skills/render-a2ui/SKILL.md`) — same pattern as
  `deal_pricing`. It has **no tools** and an `output_schema`, so it uses the model's native
  structured output to emit UI components.

## 💡 Concept — the app is a thin client to *two* agents

Open `agents/app.py`. The app is deliberately a **thin client** — it contains no audit logic. For
each request it makes two A2A calls:

```
browser ──► app ──A2A──► orchestrator   (run the audit → raw reports)
                └──A2A──► ui_renderer    (turn the reports into A2UI panels)
```

The app then assembles the A2UI surface and streams it to the browser. Because the orchestrator
is a *separate* agent (not imported into the app), the app calling it over A2A is what puts it on
the same governed footing as every other hop — which matters in Step 7.

The app also hosts the **shared A2A task store** you met in Step 5 (`/api/taskstore/*`, backed by
Firestore) and the single Pub/Sub telemetry consumer — which is why it must run as **exactly one
instance**.

## 💻 Run — deploy the UI Renderer (the 6th agent)

The app calls the UI Renderer, so deploy it first, and grant its access like any other agent:

```bash
.venv/bin/python deploy/deploy_agents_a2a.py ui_renderer
./deploy/grant_agent_access.sh ui-renderer
```

## 💻 Run — the app's identity

The app runs as its own service account with its own least-privilege IAM (and it needs the
telemetry subscription it consumes). Set that up:

```bash
./deploy/setup_app_iam.sh
```

## 💻 Run — build & deploy the app

```bash
./deploy/deploy_app.sh
```

It builds the frontend + API image, auto-resolves the engine A2A URLs and three MCP URLs, and
deploys `vibeflix-app` to Cloud Run pinned to a single instance.

## 💻 Run — the circular dependency: redeploy the engines (pass 2)

Here's a subtlety worth understanding. The engines need the app's URL (for `TASK_STORE_URL`), but
the app needed the engines' URLs first — a genuine **circular dependency**. The fix is to deploy
the engines **twice**, with the app in between. You've done pass 1 (Steps 2–5) and just deployed
the app; now do **pass 2** so the engines pick up the task-store URL:

```bash
.venv/bin/python deploy/deploy_agents_a2a.py        # no arg = redeploy all engines (pass 2)
```

Skip this and the engines log `[task-store] … falling back to the per-replica store`, and you're
back to the 404 storm from Step 5.

## 👀 Verify

```bash
./deploy/verify/step6.sh
```

It confirms the app is deployed and **pinned 1/1**. Then open the app in your browser:

```bash
gcloud run services describe vibeflix-app --region "$REGION" --format 'value(status.url)'
```

> 👀 You'll see the **Live Compliance Audit** console. Don't run a full flow yet — the access
> controls aren't in place. That's Step 7. Then in Step 8 you'll run the scenarios and watch the
> A2UI panels build themselves from each run's results.

## 💡 What you learned

- **A2UI** generates the interface from the agents' output, so you don't hand-build a static form
  for every outcome.
- The **UI Renderer** is just another A2A agent — the app calls it alongside the orchestrator.
- The app is a **thin client** and the host of the shared task store — hence single-instance — and
  the engine ↔ app **circular dependency** is resolved by deploying the engines twice.

**Next:** [Step 7 — Identity, Gateway & Registry →](./07-identity-gateway-registry.md)
