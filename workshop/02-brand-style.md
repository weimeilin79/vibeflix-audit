# Step 2 — The Brand Style Agent

Your first agent. It looks at a product mock-up and decides whether it follows Vibeflix's brand
rules. Building it teaches the single most important idea in agent design: **which work should
the model do, and which work should it *not* do.**

## 💡 Concept — deterministic vs non-deterministic work

Two kinds of work happen in a brand review:

- **Non-deterministic** — *looking at the mock-up* and reading what's on it: the printed text,
  the product medium. This is judgment. Ask two people (or run a model twice) and you might get
  slightly different words. It's fuzzy, and it's exactly what a language model with **vision** is
  good at.
- **Deterministic** — *checking those facts against the rules*: "is this font on the approved
  list?", "is this medium allowed?". Given the same inputs, the answer is always the same. It's
  a lookup, and a model should **never** be the thing that decides it — it would occasionally
  make the answer up.

### The "intern" story

This is how the work used to happen at Vibeflix, and it's the whole lesson in one picture:

```
  BEFORE (manual)                          NOW (agent + MCP)
  ┌───────────────────────────┐            ┌───────────────────────────┐
  │ a coordinator/intern:     │            │ the AGENT (model + vision):│
  │  • eyeballs the mock-up    │  ───────►  │  • reads text + medium     │  ← non-deterministic
  │  • TYPES the text + medium │            │    from the image itself   │
  │    into the check tool     │            │  • calls the check tool    │
  └─────────────┬─────────────┘            └─────────────┬─────────────┘
                │ runs                                    │ calls (automated)
                ▼                                         ▼
  ┌───────────────────────────┐            ┌───────────────────────────┐
  │ the verification checks    │  (same)    │ the MCP server            │  ← deterministic
  │ (typography, medium, …)    │  ═══════►  │  run_brand_audit(...)      │
  └───────────────────────────┘            └───────────────────────────┘
```

The **deterministic checks already existed** — they were the intern's verification tool. Today
that tool *is the MCP server*. The only thing the intern actually added was **reading the image
and typing the inputs**. Connect an agent to the MCP, and the agent's vision does that reading
automatically. **Same deterministic tool; a model, not a human, feeds it.**

## 📝 Look — the tool signature *is* the intern's form

Open `mcp_servers/mcp_brand_style/server.py` and find the one tool it exposes:

```python
@mcp.tool()
def run_brand_audit(text: str, medium: str, image_uri: str) -> str:
    """... The agent extracts the inputs and calls this once — it does NOT
    orchestrate the individual checks."""
```

Those three parameters — `text`, `medium`, `image_uri` — **are the intern's form.** Everything
inside `run_brand_audit` (the typography check, the approved-medium check, the asset-source
gate) is pure deterministic Python. No model, no guessing.

Now open `agents/brand_style/agent.py`. Its docstring states the division plainly:

> *"The agent does the EXTRACTION (reading the artwork's printed text and product medium, using
> its own multimodal vision); the MCP server is the deterministic auditor."*

So the model's *only* job is to turn a picture into the three inputs. The verdict is the
tool's.

> 💡 **Reinforcement (optional):** the code has three guardrails that all say *"keep the
> deterministic stuff out of the model's hands"* — `require_image_before_model` (no image →
> refuse *before* calling the model, so it can't invent an extraction), the **asset-source
> gate** inside the tool (unapproved image → `rejected`, stop), and `tool_guard` (if the MCP
> didn't load, the agent refuses rather than answering blind). Mention one, skip the rest.

## 💻 Run — build & deploy brand_style

The deploy script finds the MCP server URLs for you, so deploying your first agent is a single
command:

```bash
.venv/bin/python deploy/deploy_agents_a2a.py brand_style
```

This packages the agent folder, deploys it to **Agent Runtime** as its own engine that serves
A2A automatically, and turns on its **agent identity**. (Re-running `brand_style` updates the
same engine — it never duplicates.) A deploy takes a few minutes.

## 💻 Run — grant the agent its own access

The engine exists now, but with no permissions. Grant it exactly what it needs — project roles on
**its own identity**, and the ability to reach the IAM-gated MCP servers:

```bash
./deploy/grant_agent_access.sh brand-style
```

This is **least privilege in action**: each agent grants its *own* access as it's deployed, keyed
to its *own* principal — no blanket "any agent can do anything." (Step 7 layers the gateway
governance on top of this.)

## 👀 Verify — the agent extracts, then the tool decides

```bash
./deploy/verify/step2.sh
```

It confirms the `brand_style` engine is deployed **with an agent identity**. To watch it
actually work, talk to it directly — point it at the default mock-up and see it read the image,
then call the deterministic tool:

```bash
ENGINE=$(jq -r '.["vibeflix-brand-style"].engine' deploy/agent_identities.json)
agents-cli run --url "$ENGINE" --mode adk \
  "Audit this mock-up. image: gs://${REQUEST_IMAGE_BUCKET:-$PROJECT-request-image}/vendor_request_refine.png, character: grogu, market: NA"
```

> 👀 In the reply you should see the agent report the **text and medium it read from the
> image** (the non-deterministic part) and a **status** — `compliant`, `flagged`, or
> `rejected` — that came from `run_brand_audit` (the deterministic part). Try a bad image link
> and watch the **asset-source gate** reject it *before* any content check runs.

## 💡 What you learned

- Tools live in an MCP server; the agent calls them.
- The model does the **fuzzy** work (understand the image); the MCP does the **exact** work
  (apply the rules) — and you deliberately keep the model *out* of the rule-deciding.
- An ADK agent is deployed as its own A2A-serving engine with its own identity.

**Next:** [Step 3 — The Deal Pricing agent →](./03-deal-pricing.md)
