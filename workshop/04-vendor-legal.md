# Step 4 — Vendor Clearance + Legal

Two agents this step, because they work as a pair: `vendor_clearance` checks a vendor is
allowed to make the product, and when a *new* vendor/category is onboarded it hands the deal
off to an independent `legal` agent to clear the paperwork and execute the contract. Building
them teaches three things: **RAG**, **agent-to-agent (A2A) handoff**, and **human-in-the-loop**.

## 💡 Concept — Legal, RAG, and the tribal-knowledge problem

Most of Vibeflix's departments have a written process. Legal doesn't. Because of *when* it was
built, the real end-to-end legal workflow was never documented — it survives as **tribal
knowledge** in a handful of scattered, contradictory files left behind by people who've moved
on. Look in `resource/legal/docs/`:

- `legal-stuff-dont-lose-this.txt` — a departing engineer's handoff dump: *"Nobody ever wrote
  down the real end-to-end legal workflow, so here it is from memory before it walks out the
  door with me."*
- `slack-export-licensing-ops.txt` — the process reconstructed live in chat.
- `royalty-rate-card.md` marked **Version 3** (*"Version 2 is still floating around in email —
  ignore it"*), and a **2019 SOP that is wrong** about the insurance amount.

You *cannot* hard-code a process nobody agrees on. So the legal agent **reconstructs** it with
**RAG (Retrieval-Augmented Generation)**: instead of baking rules into the prompt, it
*retrieves* the relevant scraps from those docs at run time and reasons over them.

> **RAG in one line:** give the model a *search tool* over your documents, so it pulls in the
> exact facts it needs instead of relying on what it happened to memorize.

## 📝 Look — the retrieval tool

Open `agents/legal/legal_kb.py`. It exposes one FunctionTool, `search_legal_docs`, with two
backends:

- **`RAG_CORPUS` set** → Vertex AI **RAG Engine** (`:retrieveContexts`) over a corpus built from
  those docs (you'll build it below);
- **otherwise** → a self-contained local keyword retriever — so the agent works with zero cloud
  setup while you develop.

In `agents/legal/agent.py`, `search_legal_docs` sits alongside the legal *workflow* tools
(`draft_license_amendment`, `verify_certifications`, `assign_customs_hs_code`,
`verify_liability_insurance`, …) and the one real side effect — `upsert_contract` (an MCP tool)
that persists the executed contract. The agent uses RAG to figure out *what the process is*,
then the tools to *do it*.

## 💡 Concept — A2A: handing off to a remote agent

`legal` is **its own deployed agent** — a separate engine with its own identity. `vendor_clearance`
doesn't import it or contain it; it **calls it over A2A** (Agent-to-Agent), the protocol for one
agent delegating to another.

The way ADK models "an agent running somewhere else that I can call" is a **remote agent**. You
hold a lightweight stand-in for the remote engine and invoke it like a local step; the call
travels over A2A to the other engine and the result comes back.

## 📝 Look — the handoff as its own step

Open `agents/vendor_clearance/agent.py`. It's a small Workflow:

```
START → clearance → legal_clearance → finalize
```

`legal_clearance` is a **distinct node** whose whole job is the handoff — it calls the legal
engine over A2A (`LEGAL_A2A_URL` points at it) with a *fresh* context and merges legal's verdict
+ contract id back in. Making the handoff its own node means it shows up as its own step in the
trace (you'll see this in Step 8's observability), and keeps each agent's reasoning isolated.

> 💡 The orchestrator (Step 5) uses ADK's `RemoteA2aAgent` construct for the same idea at scale.
> `vendor_clearance→legal` uses a direct, fresh-context A2A call on purpose — so legal doesn't
> receive vendor_clearance's whole conversation and echo it back.

## 💡 Concept — Human-in-the-loop (HITL)

Buried in that tribal knowledge is a rule that keeps breaking onboardings: a contract **cannot
execute** until a human supplies a **safety-certification ID** that lives in *no* record.
Everyone forgot it existed.

So legal implements it as **human-in-the-loop**: when it needs a value it can't find, it doesn't
guess and it doesn't hard-fail — it returns a **question** and a status like `needs_user`. That
question **propagates up** the call chain — legal → vendor_clearance (`status: needs_input`) →
orchestrator → the app → **the person who started the audit**. Their answer comes **back down**
through workflow state (`legal_safety_cert`), vendor_clearance folds it into the brief, and legal
reads it and proceeds. (If no ID is ever supplied, legal issues a provisional `PROV-…` id and
reports it — so onboarding is never silently blocked.)

## 📝 Look — the question that travels

In `agents/legal/agent.py` the instruction says: when it needs a value → status `ask_vendor` /
`needs_user` with the options stated in a **`question`** field. In
`agents/vendor_clearance/agent.py` you'll see the matching `status: "needs_input"` + `question`
on its report, and `legal_safety_cert` carried in state — that's the answer coming back down.

## 💻 Run — build legal's knowledge base, then deploy both

Legal needs its RAG corpus first. Build it from the tribal-knowledge docs:

```bash
./deploy/setup_legal_rag.sh
# It prints  RAG_CORPUS=projects/.../ragCorpora/...
# Add that line (and RAG_LOCATION=us-central1) to deploy/.env, then continue.
```

Now deploy legal, then vendor_clearance (deploy **in this order** — vendor_clearance
auto-discovers legal's A2A URL from `agent_identities.json`):

```bash
.venv/bin/python deploy/deploy_agents_a2a.py legal
.venv/bin/python deploy/deploy_agents_a2a.py vendor_clearance
```

Then grant each its own access:

```bash
./deploy/grant_agent_access.sh legal
./deploy/grant_agent_access.sh vendor-clearance
```

## 👀 Verify

```bash
./deploy/verify/step4.sh
```

It confirms both engines are deployed with agent identities. To see the handoff (and maybe the
HITL question), onboard a vendor to a new category — vendor_clearance will hand off to legal:

```bash
ENGINE=$(jq -r '.["vibeflix-vendor-clearance"].engine' deploy/agent_identities.json)
agents-cli run --url "$ENGINE" --mode adk \
  "Onboard vendor VND-1008 for grogu vinyl figures in NA."
```

> 👀 Watch for vendor_clearance to reach `legal_clearance`, legal to reconstruct its steps via
> RAG, and — if a safety-cert ID is needed — a `needs_input` status with a **question** bubbling
> back up. That's HITL. The full round-trip (answer coming back down from a real user) comes
> together once the app is in place (Step 6).

## 💡 What you learned

- **RAG** lets an agent reconstruct an undocumented process by *retrieving* facts instead of
  memorizing them.
- **A2A** lets one agent hand off to another independent agent as a **remote agent**.
- **HITL** is a question that propagates up to a human and an answer that flows back down —
  without hard-failing the run.

**Next:** [Step 5 — The Orchestrator →](./05-orchestrator.md)
