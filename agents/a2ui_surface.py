"""Deterministic A2UI assembly (app-side): the audit surface + panel slotting.

The remote UI-Render agent (its own :8004 A2A service) RENDERS the varied reports: it emits
A2UI itself, which app.py validates against the spec (`vibeflix_common.agent.a2ui_format`, backed by
the official a2ui-agent-sdk) and hands here as `{root, components}`. This module owns only the
parts that are the APP's business, not the agent's:

  * the surface scaffold — header, one pending card slot per workflow, divider, the closing
    report line, and the reserved `final` slot (`stream_initial`);
  * slotting an agent panel into position i, namespacing its ids (`stream_panel`);
  * the app's own deterministic content: the closing report line and the final clearance
    report, which are assembled from mesh state, not from an LLM;
  * `panels_fallback`, the rule-based summary used when the presenter agent is unreachable —
    so the UI keeps working even if that instance is down.

The wire uses the message names `surfaceUpdate` / `beginRendering` and `{"id", "component"}`
components: A2UI v0.8, which is what `@a2ui/react@0.10` renders (the protocol's current
release renamed them to updateComponents / createSurface). Everything streamed from here is
incremental — the renderer patches components into the live surface by id.
"""

from vibeflix_common.agent.a2ui_format import rewrite_ids


def _fmt(n) -> str:
    try:
        return f"{int(n):,}"
    except (TypeError, ValueError):
        return str(n)


def report_line(sourcing: dict) -> str:
    """The closing line of the audit report — how the run was finalized (including
    the production-volume-vs-vendor-cap outcome)."""
    s = sourcing or {}
    st = s.get("status")
    if st == "auto_finalized":
        return f"🧾 **Report finalized** — production volume {_fmt(s.get('volume'))} within the vendor cap ({_fmt(s.get('cap'))} units)."
    if st == "split_addendum":
        return f"🧾 **Report finalized** — volume split: {_fmt(s.get('primary_units'))} primary + {_fmt(s.get('addendum_units'))} units to addendum {s.get('addendum_contract')}."
    if st == "capped":
        return f"🧾 **Report finalized** — capped at {_fmt(s.get('primary_units'))} units; {_fmt(s.get('cancelled_units'))} cancelled."
    if st == "needs_choice":
        return "🧾 **Report:** awaiting a production-volume sourcing decision."
    return f"🧾 **Report:** {st or 'pending'}."


# Emoji hints for inferring a title from a workflow name (best-effort, generic).
_EMOJI = [
    ("brand", "🎨"), ("style", "🎨"), ("design", "🎨"),
    ("ip", "⚖️"), ("legal", "⚖️"), ("counsel", "⚖️"), ("market", "⚖️"),
    ("story", "🎬"), ("lore", "🎬"), ("canon", "🎬"),
    ("secur", "🔒"), ("pric", "💰"), ("cost", "💰"), ("sourc", "📦"),
]


def _title_for(key: str, report: dict) -> str:
    """Infer a friendly '<emoji> <Name>' title from the report's agent/key."""
    return title_from_name(report.get("agent") or key or "workflow")


def title_from_name(name: str) -> str:
    """A friendly '<emoji> <Name>' pending title derived from a workflow/agent name —
    generic, so a newly-added workflow gets a title with no code change."""
    words = (name or "workflow").replace("_", " ")
    for drop in (" compliance", " agent", " report", " audit", " workflow"):
        words = words.replace(drop, "")
    emoji = next((e for token, e in _EMOJI if token in (name or "").lower()), "📋")
    return f"{emoji} {words.strip().title()}"


# ---------------------------------------------------------------------------
# Streaming (A2UI v0.8): incremental surfaceUpdate messages patched by id, so
# panels can start "pending" and fill in live as each workflow returns.
# ---------------------------------------------------------------------------
_SURFACE = "audit"


def _text_comp(cid, s, hint=None):
    node = {"text": {"literalString": s}}
    if hint:
        node["usageHint"] = hint
    return {"id": cid, "component": {"Text": node}}


def stream_initial(titles, market, volume, reused=0):
    """Initial surface: header + one PENDING card per SHOWN workflow (the ones being
    run this pass) + divider + a pending sourcing line. `reused` = how many workflows
    were reused unchanged (not shown as panels, just noted in the header — their result
    is already on the previous run's surface). Returns [surfaceUpdate, beginRendering]."""
    n = len(titles)
    if reused:
        head = (f"**Orchestrator: re-running {n} workflow{'s' if n != 1 else ''}, "
                f"reusing {reused} unchanged** — market: {market} · volume: {_fmt(volume)} units")
    else:
        head = (f"**Orchestrator dispatched {n} compliance workflow{'s' if n != 1 else ''}** "
                f"— market: {market} · volume: {_fmt(volume)} units")
    comps = [_text_comp("hdr", head, "h4")]
    root_kids = ["hdr"]
    for i, title in enumerate(titles):
        comps.append(_text_comp(f"t{i}", f"⏳ {title} — running…", "h5"))
        comps.append({"id": f"col{i}", "component": {"Column": {"children": {"explicitList": [f"t{i}"]}}}})
        comps.append({"id": f"card{i}", "component": {"Card": {"child": f"col{i}"}}})
        root_kids.append(f"card{i}")
    comps.append({"id": "div", "component": {"Divider": {"axis": "horizontal"}}})
    comps.append(_text_comp("srce", "🧾 **Report:** assembling…"))
    # Empty slot the final clearance report fills on a fully-passed run. Reserved up
    # front because a later surfaceUpdate must be SELF-CONTAINED — it can only reference
    # component ids it (re)defines itself, so the root is never re-sent.
    comps.append({"id": "final", "component": {"Column": {"children": {"explicitList": []}}}})
    root_kids += ["div", "srce", "final"]
    comps.append({"id": "root", "component": {"Column": {"children": {"explicitList": root_kids}}}})
    return [
        {"surfaceUpdate": {"surfaceId": _SURFACE, "components": comps}},
        {"beginRendering": {"surfaceId": _SURFACE, "root": "root"}},
    ]


def stream_panel(i, panel):
    """surfaceUpdate that fills panel slot `i` with the AGENT-EMITTED A2UI.

    `panel` is `{root, components}` — components already in WIRE form, straight from the
    ui_renderer (parsed and validated against the spec by `vibeflix_common.agent.a2ui_format`) or
    from `panels_fallback`. The app does NOT build the layout; it only slots the panel into
    position i: the panel takes the id `card{i}` (which the surface's root Column already
    lists) and every other id is namespaced `p{i}_…` so panels can't collide on the generic
    ids an LLM picks (`card`, `col`, `t1`). `rewrite_ids` remaps the component ids AND the
    references between them, using the catalog to know which fields hold references.

    The slot is always a **Card**, and exactly one deep — that's the surface's own layout
    decision, made when `stream_initial` drew the pending placeholder. What arrives varies:
    the panel may be rooted in its Card (take the slot id directly), in a Column wrapping that
    Card (descend to it, drop the wrapper), or in a Column with no Card at all (wrap it). All
    three then render identically to every other panel — no bare panel, no card-inside-a-card.
    """
    root = panel.get("root")
    components = [c for c in (panel.get("components") or []) if isinstance(c, dict)]
    slot = f"card{i}"
    card, wrappers = _panel_card(root, {c.get("id"): c for c in components})

    def nid(x):
        return slot if (card and x and x == card) else f"p{i}_{x}"

    comps = rewrite_ids([c for c in components if c.get("id") not in wrappers], nid)
    if not card:
        comps.append({"id": slot, "component": {"Card": {"child": nid(root)}}})
    return {"surfaceUpdate": {"surfaceId": _SURFACE, "components": comps}}


def _panel_card(root, by_id):
    """(the panel's own Card, the wrapper ids above it) — descending from `root`.

    Returns `(None, set())` when the panel has no Card at its top, so the caller wraps it.
    Only SINGLE-child Columns are descended through: a Column with several children is real
    layout the agent chose, not a wrapper, and must be kept. `node not in wrappers` also makes
    the descent cycle-proof — the SDK validator rejects recursive components, but the app's own
    fallback panels never go through it."""
    node, wrappers = root, set()
    while node and node in by_id and node not in wrappers:
        component = by_id[node].get("component") or {}
        if "Card" in component:
            return node, wrappers
        children = ((component.get("Column") or {}).get("children") or {}).get("explicitList")
        if not (isinstance(children, list) and len(children) == 1):
            return None, set()
        wrappers.add(node)
        node = children[0]
    return None, set()


def stream_report_line(sourcing):
    """surfaceUpdate that fills the closing report line (the `srce` slot)."""
    return {"surfaceUpdate": {"surfaceId": _SURFACE, "components": [_text_comp("srce", report_line(sourcing))]}}


def stream_final_report(entry):
    """surfaceUpdate filling the reserved `final` slot with the FINAL clearance report +
    executed contract (shown when every workflow passed). Self-contained: every id it
    references is (re)defined in this same update — the root is never touched.
    `entry` is the audit-history record: {inputs, reports, sourcing, contract, ...}."""
    inputs = entry.get("inputs") or {}
    reports = entry.get("reports") or {}
    contract = entry.get("contract") or {}

    comps = [_text_comp("fin_t", "📜 **Final Clearance Report** — all workflows passed", "h4")]
    kids = ["fin_t"]

    def line(cid, s, hint=None):
        comps.append(_text_comp(cid, s, hint))
        kids.append(cid)

    subject = " · ".join(str(v) for v in (
        inputs.get("character"), inputs.get("product_category"), inputs.get("medium"),
        inputs.get("vendor"), inputs.get("target_market"),
        f"{_fmt(inputs.get('volume'))} units" if inputs.get("volume") else None) if v)
    line("fin_sub", subject or "—", "caption")

    for i, (name, report) in enumerate(sorted(reports.items())):
        line(f"fin_w{i}", f"✅ {title_from_name(name)} — **{str((report or {}).get('status', '')).upper()}**")

    line("fin_srce", report_line(entry.get("sourcing") or {}))

    if contract:
        line("fin_ct", "**Executed licensing contract**", "h5")
        rows = [
            ("Contract", contract.get("contract_id")),
            ("Status", contract.get("status")),
            ("Vendor", contract.get("vendor_id")),
            ("Character", contract.get("character_id")),
            ("Category", contract.get("category")),
            ("Territory", contract.get("territory")),
            ("Royalty", f"{contract.get('royalty_pct')}%" if contract.get("royalty_pct") is not None else None),
            ("Volume", f"{_fmt(contract.get('production_volume'))} units" if contract.get("production_volume") else None),
            ("Safety cert", contract.get("safety_cert_id")),
            ("HS code", contract.get("hs_code")),
            ("Amendment", contract.get("amendment_id")),
        ]
        detail = " · ".join(f"{k}: **{v}**" for k, v in rows if v not in (None, ""))
        line("fin_cd", detail)

    line("fin_hist", "🗂 Saved to **Audit History** (see the Audit History tab).", "caption")

    comps.append({"id": "fin_col", "component": {"Column": {"children": {"explicitList": kids}}}})
    comps.append({"id": "fin_card", "component": {"Card": {"child": "fin_col"}}})
    comps.append({"id": "final", "component": {"Column": {"children": {"explicitList": ["fin_card"]}}}})
    return {"surfaceUpdate": {"surfaceId": _SURFACE, "components": comps}}


def panels_fallback(reports: dict):
    """Deterministic, REPORT-AGNOSTIC A2UI panels — the safety net when the presenter LLM is
    unavailable. Emits the SAME `{root, components}` wire shape the agent does, so the app
    slots it identically. Works for any set/shape of reports (findings / issues / message)."""
    out = []
    for key, report in (reports or {}).items():
        report = report or {}
        status = report.get("status", "unknown")
        comps = []

        def text(cid, s, hint=None):
            comps.append(_text_comp(cid, s, hint))
            return cid

        col_kids = [text("t", f"{_title_for(key, report)} — **{str(status).upper()}**", "h5")]
        issues = []
        for item in (report.get("findings") or []) + (report.get("issues") or []):
            if not isinstance(item, dict):
                continue
            desc = item.get("description") or item.get("issue_type") or item.get("word") or "Issue"
            icon = "⛔" if item.get("severity") == "critical" else "⚠️"
            sug = item.get("suggestions") or []
            issues.append((f"{icon} {desc}", f"Try: {', '.join(sug)}" if sug else ""))
        headline = report.get("message") or report.get("question") or (
            f"{len(issues)} issue(s) found." if issues else "No issues found.")
        col_kids.append(text("h", headline))
        for j, (line, resolve) in enumerate(issues):
            col_kids.append(text(f"l{j}", line))
            if resolve:
                col_kids.append(text(f"r{j}", f"↳ *how to resolve:* {resolve}", "caption"))
        comps.append({"id": "col", "component": {"Column": {"children": {"explicitList": col_kids}}}})
        comps.append({"id": "card", "component": {"Card": {"child": "col"}}})
        out.append({"root": "card", "components": comps})
    return out
