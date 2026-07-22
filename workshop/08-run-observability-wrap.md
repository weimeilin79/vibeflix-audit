# Step 8 — Run the Flows, Observability & Wrap-up

Everything is built and secured. Time to *use* it — run real audits, watch the mesh light up, and
see the whole distributed system through the observability tools. Then we wrap up.

## 💻 Run — the four scenarios

Open the console and grab its URL:

```bash
gcloud run services describe vibeflix-app --region "$REGION" --format 'value(status.url)'
```

The console has a **scenario picker** above the chat box. Run each one and watch the mesh work:

| | Scenario | What it exercises |
|---|---|---|
| ✅ | **Happy path** | a clean vendor + product clears brand, pricing, and vendor checks |
| ⛔ | **Exclusivity block** | an exclusive partner holds the territory → `vendor_clearance` blocks it |
| 🆕 | **Onboard new vendor** | a brand-new vendor/category → the **A2A handoff to legal** + the **human-in-the-loop** question (it asks you for one thing — the HQ location) |
| 📦 | **Over volume cap** | projected volume exceeds the SKU cap → flagged |

> 👀 As each runs, the **live graph** animates: nodes light as agents start, tool **LEDs** blink as
> MCP tools fire, and the **A2UI panels** assemble from each run's actual results. The *Onboard*
> flow is the one to watch closely — it pauses to ask you a question (HITL) and only finishes the
> contract once you answer.

## 💡 Concept — observability: three views of one run

The mesh has been emitting telemetry the whole time (it's on by default — every engine deploy set
`GOOGLE_CLOUD_AGENT_ENGINE_ENABLE_TELEMETRY=true`). Here's where to see it:

1. **The live graph (in the app).** Agents publish fine-grained events to a **Pub/Sub** topic; the
   app relays them to the console, which animates the Workflow graph in real time. This is
   telemetry as a *product feature*, not just debugging.
2. **Cloud Trace.** Every request is one **distributed trace** whose spans stitch across A2A hops
   *and* MCP tool calls — so a single audit shows the orchestrator → the three specialists → their
   MCP tools, with timing, in one waterfall. Console → **Trace → Trace explorer**.
3. **Application Topology.** Console → **Agent Platform → Topology** shows the mesh as a graph of
   nodes — agents and MCP servers — discovered from the aggregated traces. It's the architecture
   diagram from Step 0, drawn from real traffic.

> 💡 The MCP servers appear as their own topology nodes because they export OpenTelemetry spans.
> New deploys get this automatically; to retrofit already-running engines, there's
> `./deploy/enable_otel.sh`.

## 👀 Verify

```bash
./deploy/verify/step8.sh
```

It confirms all six engines have **telemetry on**, **trace propagation on**, and the **shared task
store wired** — the three flags a deploy can silently drop that would leave you blind or slow.

## 🎉 What you built

A **ten-service, distributed, secured multi-agent system**:

- **3 MCP tool servers** — deterministic, IAM-gated (Step 1)
- **6 agents** — brand, pricing, vendor, legal, orchestrator, UI renderer (Steps 2–6)
- **1 console app** — thin client + shared task store (Step 6)
- governed by **Agent Identity + Gateway + Registry** (Step 7)
- observable end-to-end via **Trace + live telemetry + Topology** (Step 8)

And the concepts behind them: **MCP**, **deterministic vs non-deterministic** work, **Skills**,
**loop-engineering**, **RAG**, **A2A handoff**, **human-in-the-loop**, the **ADK graph** and
**fan-out**, the **shared task store**, **A2UI**, and **enterprise governance**.

## 🧹 Teardown

When you're completely done, one script removes everything so you don't leave anything running:

```bash
./deploy/destroy.sh              # delete the workshop's resources, keep the project
# — or —
./deploy/destroy.sh --project    # delete the WHOLE project (fastest, cleanest)
```

It asks you to type the project id to confirm, then removes the 6 engines, the app + 3 MCP Cloud
Run services, the gateway + registry entries, the Terraform-managed infra (Artifact Registry +
topic), the buckets, Firestore, Pub/Sub, and the service accounts. It's best-effort and re-runnable.

> **Destructive and irreversible** — run it only when you're finished. (The "never delete an
> engine" rule from Step 7 is about *redeploys*; at teardown, deleting is exactly what you want.)

## Where to go next

- Re-read any agent's code now that you know the concepts — `agents/<name>/agent.py`.
- The deeper design docs: [`docs/`](../docs/) (story, architecture, the shared library).
- The full operational runbook: [`deploy/docs/instruction-sre.md`](../deploy/docs/instruction-sre.md).

**🎉 Congratulations — you've built and shipped an enterprise multi-agent mesh on Google Cloud.**
