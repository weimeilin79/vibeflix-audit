"""Deterministic A2UI assembly (app-side): panels → a real A2UI v0.9 surface.

The remote UI-Render agent (its own :8004 A2A service) turns the varied reports
into `panels` ({title, status, headline, lines:[(text, resolve)]}); app.py calls
it and then uses this module to assemble the `{root, components, data}` shape the
official A2UI React renderer consumes — a flat list of catalog components
(Column / Card / Text / Divider), Text with simple Markdown. `panels_fallback` is
a rule-based summary used when the presenter agent is unreachable, so the UI keeps
working even if that instance is down.
"""


def _fmt(n) -> str:
    try:
        return f"{int(n):,}"
    except (TypeError, ValueError):
        return str(n)


def sourcing_line(sourcing: dict) -> str:
    s = sourcing or {}
    st = s.get("status")
    if st == "auto_finalized":
        return f"📦 **Sourcing:** within vendor cap ({_fmt(s.get('volume'))} ≤ {_fmt(s.get('cap'))} units)."
    if st == "split_addendum":
        return f"📦 **Sourcing:** split {_fmt(s.get('primary_units'))} primary + {_fmt(s.get('addendum_units'))} to {s.get('addendum_contract')}."
    if st == "capped":
        return f"📦 **Sourcing:** capped at {_fmt(s.get('primary_units'))}; {_fmt(s.get('cancelled_units'))} units cancelled."
    return f"📦 **Sourcing:** {st or 'pending'}."


def build_surface(panels, sourcing, market, volume) -> dict:
    """Assemble an A2UI v0.9 static surface from panels + the sourcing outcome."""
    comps = []

    def add(cid, comp):
        comps.append({"id": cid, "component": comp})
        return cid

    def text(cid, s, hint=None):
        node = {"text": {"literalString": s}}
        if hint:
            node["usageHint"] = hint
        return add(cid, {"Text": node})

    n = len(panels)
    root_kids = [text("hdr", f"**Orchestrator dispatched {n} compliance workflow{'s' if n != 1 else ''}** — market: {market} · volume: {_fmt(volume)} units", "h4")]

    for idx, p in enumerate(panels):
        col_kids = [
            text(f"t{idx}", f"{p['title']} — **{str(p['status']).upper()}**", "h5"),
            text(f"h{idx}", p["headline"]),
        ]
        for j, (line, resolve) in enumerate(p.get("lines", [])):
            col_kids.append(text(f"l{idx}_{j}", line))
            if resolve:
                col_kids.append(text(f"r{idx}_{j}", f"↳ *how to resolve:* {resolve}", "caption"))
        add(f"col{idx}", {"Column": {"children": {"explicitList": col_kids}}})
        root_kids.append(add(f"card{idx}", {"Card": {"child": f"col{idx}"}}))

    root_kids.append(add("div", {"Divider": {"axis": "horizontal"}}))
    root_kids.append(text("srce", sourcing_line(sourcing)))

    add("root", {"Column": {"children": {"explicitList": root_kids}}})
    return {"a2ui_version": "0.9", "root": "root", "components": comps, "data": {}}


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
    comps.append(_text_comp("srce", "📦 **Sourcing:** pending…"))
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
    """surfaceUpdate that fills panel `i` (title, headline, lines) — patched by id."""
    comps = [
        _text_comp(f"t{i}", f"{panel['title']} — **{str(panel['status']).upper()}**", "h5"),
        _text_comp(f"h{i}", panel["headline"]),
    ]
    col_kids = [f"t{i}", f"h{i}"]
    for j, (line, resolve) in enumerate(panel.get("lines", [])):
        comps.append(_text_comp(f"l{i}_{j}", line))
        col_kids.append(f"l{i}_{j}")
        if resolve:
            comps.append(_text_comp(f"r{i}_{j}", f"↳ *how to resolve:* {resolve}", "caption"))
            col_kids.append(f"r{i}_{j}")
    comps.append({"id": f"col{i}", "component": {"Column": {"children": {"explicitList": col_kids}}}})
    return {"surfaceUpdate": {"surfaceId": _SURFACE, "components": comps}}


def stream_sourcing(sourcing):
    """surfaceUpdate that fills the sourcing line."""
    return {"surfaceUpdate": {"surfaceId": _SURFACE, "components": [_text_comp("srce", sourcing_line(sourcing))]}}


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

    line("fin_srce", sourcing_line(entry.get("sourcing") or {}))

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
    """Deterministic, REPORT-AGNOSTIC summary — used when the presenter LLM is
    unavailable. Works for any set/shape of reports (findings / issues / message)."""
    out = []
    for key, report in (reports or {}).items():
        report = report or {}
        status = report.get("status", "unknown")
        lines = []
        for item in (report.get("findings") or []) + (report.get("issues") or []):
            if not isinstance(item, dict):
                continue
            desc = item.get("description") or item.get("issue_type") or item.get("word") or "Issue"
            icon = "⛔" if item.get("severity") == "critical" else "⚠️"
            sug = item.get("suggestions") or []
            out_resolve = f"Try: {', '.join(sug)}" if sug else ""
            lines.append((f"{icon} {desc}", out_resolve))
        headline = report.get("message") or report.get("question") or (
            f"{len(lines)} issue(s) found." if lines else "No issues found."
        )
        out.append({"title": _title_for(key, report), "status": status, "headline": headline, "lines": lines})
    return out
