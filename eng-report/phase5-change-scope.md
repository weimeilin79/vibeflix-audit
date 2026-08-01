# Phase 5 — Native HITL Change Scope (for review)

**Date:** 2026-07-31 · **Status:** proposed, building touch-point #1
**Goal:** replace the report-status `needs_user` + whole-audit-resubmit HITL with real ADK
`input_required` park/resume, over the **poll** transport (native `RemoteA2aAgent` can't poll long
jobs — see `a2a-native-transport-findings.md`). Platform-side park/resume is de-risked (see memory
`hitl-park-resume-spike`; exact wire format captured there).

---

## Design fork — chosen: **Option B**

The human decision is at the leaf (**legal**). How the pause propagates up is the choice:

- **Option B (CHOSEN):** legal genuinely parks in `INPUT_REQUIRED` (real ADK HITL). vendor_clearance
  detects the park and carries the question **+ a resume-handle** (legal's `task_id`/`context_id`/
  `call id`) up in its report, as `needs_input` bubbles today. On the human answer, vendor_clearance
  resumes legal's still-parked task with the function-response and continues to the contract. Only
  legal truly parks; outer hops complete-and-resume as now.
  *Pro:* real ADK HITL where it matters; modest change; reuses the working propagation path.
  *Con:* outer invocation isn't held open (still a resubmit above legal).

- **Option A (rejected as too heavy):** every hop parks its own task and remembers its child's ids
  (whole chain pauses in place). Maximal correctness, much more code + durable child-id state + a
  resume chain at every hop.

---

## Touch-points (Option B)

**1. `agents/legal/agent.py`** — the real park.
- Add `request_operator_input(question, needs)` wrapped in `LongRunningFunctionTool`.
- Instruction change: when legal needs a *user* value (today's `needs_user`), CALL the tool instead
  of returning `status:"needs_user"`. Keep `ask_vendor` (liaison), `done`, `answer` unchanged.
- Effect: legal parks in `TASK_STATE_INPUT_REQUIRED`.

**2. `packages/vibeflix-common/vibeflix_common/a2a_engine.py`** — poll transport learns park/resume.
- In the poll loop, recognize `TASK_STATE_INPUT_REQUIRED` as a distinct outcome: extract the pending
  function-call DataPart (`name`,`id`,`args`) + `task_id` + `context_id`; return a structured
  "parked" payload (not plain text).
- Add `a2a_engine_resume(base, task_id, context_id, name, call_id, response)` — `message:send` with
  the function-response DataPart to the same task, poll to terminal.

**3. `agents/vendor_clearance/agent.py`** — detect, propagate, resume.
- `_call_legal_cloud`: detect the parked payload.
- Flow B: build the `needs_input` report carrying the **resume-handle** (legal ids + call name/id) so
  it survives up to the app.
- On resume (re-invoked with answer + handle): call `a2a_engine_resume(legal, …, answer)`, then
  continue (merge contract).
- Flow A (liaison auto-answer) unchanged.

**4. `agents/orchestrator/agent.py`** — pass-through.
- Ensure the resume-handle survives in the aggregate as `needs_input` bubbles up (dispatch +
  contract_finalize); route answer + handle back down on resume. Minimal.

**5. `agents/app.py`** — hold handle + resume.
- `_collect_or_complete`: capture the resume-handle into the pending session when surfacing
  `input_required`.
- Resume endpoint: pass answer + handle down so vendor_clearance resumes the parked legal task
  (replaces the blind whole-audit resubmit for this case).

**6. Phase 6 (separate):** move pending state (now incl. resume-handle) `_SESSIONS` → Firestore.

---

## Risks to validate
1. **Real legal resumes to completion** — after the human answers, real legal must continue its
   multi-step flow and EXECUTE the contract (not just reach `COMPLETED` empty). **Validated first**,
   before wiring #2–#5.
2. **LLM reliably calls the tool** when it needs the user (vs narrating). Instruction-driven.
3. **Parked-task lifetime** — human may take minutes/hours; confirm the task persists + stays
   resumable.

## Unchanged
Flow A liaison auto-answer; poll transport for all request/response; dispatch/finalize structure.

---

## CONCLUSION (2026-07-31) — native HITL investigated, NOT adopted

- **risk-1 (legal leaf) ✅** — a direct root `LlmAgent` (legal) with a `LongRunningFunctionTool`
  parks in `INPUT_REQUIRED` and resumes to execute the contract (`LC-928738`). Native park/resume
  works when the HITL leaf is a plain LlmAgent.
- **risk-1b (vendor_clearance new-vendor) ❌** — the real product HITL is new-vendor onboarding,
  which lives in vendor_clearance's **skill-driven reasoner run via `ctx.run_node`** inside a
  Workflow. There the LLM only sees the SkillToolset's **management** tools
  (`list_skills/load_skill/load_skill_resource/run_skill_script`); domain tools run *inside* the
  skill, so a direct long-running call fails: `Tool 'request_operator_input' not found`. Native
  park does not apply to a skill-reasoner-in-a-Workflow-sub-node.
- **Decision (user):** keep provisional-cert generation in legal (no human moment there) and keep
  the existing **report-based `needs_input` + re-submit** HITL for new-vendor (it already works).
  **Native HITL is not built into the mesh.**
- **State:** all native-HITL experiment code reverted (legal tool+skill, vendor_clearance
  tool+skill, vendor_clearance resumability) and redeployed clean. `remote_agent.py` remains
  dormant. **Phase 6** (move the app's `_SESSIONS` → Firestore) is still worthwhile — it makes the
  retained report-based HITL survive an app restart.
