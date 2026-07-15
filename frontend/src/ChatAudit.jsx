import React, { useState, useRef, useEffect } from 'react';
import { Send, Satellite, RotateCcw, CheckCircle, AlertTriangle, HelpCircle, Lock, Upload, Share2 } from 'lucide-react';
import { A2UIProvider, A2UIRenderer, useA2UI } from '@a2ui/react';
import { injectStyles } from '@a2ui/react/styles';

// Inject the A2UI renderer's structural + component styles once (CSS-in-JS).
injectStyles();

// Talks to the real ADK orchestrator (app.py). Same origin in prod; override for dev.
const API_BASE = import.meta.env.VITE_API_URL || '';
// Mirrors the licensing registry's territory vocabulary (mcp_licensing _TERRITORIES) —
// vendors, exclusivity contracts, and trademark records are keyed on these.
const MARKETS = ['North America', 'Europe', 'Asia-Pacific', 'Latin America', 'Middle East & Africa'];

// The backend STREAMS incremental A2UI surfaceUpdate messages (plan → per-agent
// fills → closing report line) and @a2ui/react patches the surface in place, so panels fill in
// live. Each audit RUN targets its OWN surface id (`audit-<n>`), so a re-run (e.g.
// after supplying the medium) appends a fresh result below instead of overwriting
// the first — the transcript reads as a conversation.

// Retarget a streamed message to a specific surface id (backend always emits "audit").
function retarget(msg, surfaceId) {
  const key = Object.keys(msg)[0]; // "surfaceUpdate" | "beginRendering"
  return { [key]: { ...msg[key], surfaceId } };
}

// Invisible: exposes processMessages (must be inside <A2UIProvider>) via a ref.
function A2UIBridge({ pmRef }) {
  const { processMessages } = useA2UI();
  useEffect(() => { pmRef.current = processMessages; }, [processMessages, pmRef]);
  return null;
}

// One run's rendered surface — a distinct transcript entry per audit run.
function SurfaceCard({ surfaceId }) {
  return (
    <div className="a2ui-host" style={{ background: 'var(--bg-secondary)', border: '1px solid var(--glass-border)', borderRadius: '0.5rem', padding: '0.6rem' }}>
      <A2UIRenderer surfaceId={surfaceId}
        fallback={<span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>waiting for the orchestrator…</span>} />
    </div>
  );
}

// ---- Dynamic input dock: renders whatever fields the backend asked for ----
// Canonical product-category + printed-medium options for the pickers. valid:false items
// render RED and are NOT approved — pick one to intentionally trigger a flag workflow.
const CATEGORY_OPTIONS = [
  { label: 'Vinyl Figures', valid: true }, { label: 'Action Figures', valid: true },
  { label: 'Blind Box', valid: true }, { label: 'Resin Statues', valid: true },
  { label: 'Premium Collectibles', valid: true }, { label: 'Sofubi', valid: true },
  { label: 'Novelty', valid: true }, { label: 'Plush', valid: true },
  { label: 'Apparel', valid: true }, { label: 'Accessories', valid: true },
  { label: 'Stationery', valid: true }, { label: 'Homeware', valid: true },
  { label: 'Food & Beverage', valid: false }, { label: 'Cosmetics', valid: false },
  { label: 'Footwear', valid: false },
];
const MEDIA_OPTIONS = [
  { label: 'figures', valid: true }, { label: 'vinyl figures', valid: true },
  { label: 'vinyl figure box', valid: true }, { label: 'poster', valid: true },
  { label: 'trading card', valid: true }, { label: 'apparel tag', valid: true },
  { label: 'sticker sheet', valid: true }, { label: 'art print', valid: true },
  { label: 'enamel pin card', valid: true }, { label: 'mug wrap', valid: true },
  { label: 'T-shirt', valid: true }, { label: 'book cover', valid: true },
  { label: 'backpack', valid: true }, { label: 'lunchbox', valid: true },
  { label: 'water bottle', valid: true }, { label: 'phone case', valid: true },
  { label: 'hat', valid: true }, { label: 'hoodie', valid: true },
  { label: 'shot glass', valid: false }, { label: 'ashtray', valid: false },
  { label: 'beer stein', valid: false }, { label: 'vape wrap', valid: false },
];

// Field title: same size as the input text, main (black) color — obvious, not muted.
// Module-scope (NOT inside the component) so React keeps the subtree mounted across
// re-renders — an inline component type would remount and drop input focus per keystroke.
const LABEL_STYLE = { fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-main)' };
function Field({ label, children }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem', minWidth: 0 }}>
      <label style={LABEL_STYLE}>{label}</label>
      {children}
    </div>
  );
}

// Combobox: pick from the list OR type free text. Invalid options render red.
function Combo({ value, onChange, options, placeholder }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  useEffect(() => {
    const h = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener('mousedown', h);
    return () => document.removeEventListener('mousedown', h);
  }, []);
  const q = (value || '').toLowerCase();
  const shown = options.filter((o) => o.label.toLowerCase().includes(q));
  return (
    <div ref={ref} style={{ position: 'relative' }}>
      <input className="top-textarea" placeholder={placeholder} value={value}
        onChange={(e) => onChange(e.target.value)} onFocus={() => setOpen(true)} style={{ width: '100%' }} />
      {open && shown.length > 0 && (
        <div style={{ position: 'absolute', zIndex: 30, top: '100%', left: 0, right: 0, maxHeight: '170px', overflowY: 'auto', background: 'var(--bg-card)', border: '1px solid var(--glass-border)', borderRadius: '4px', marginTop: '2px', boxShadow: '0 4px 12px rgba(0,0,0,0.25)' }}>
          {shown.map((o) => (
            <div key={o.label} onMouseDown={() => { onChange(o.label); setOpen(false); }}
              style={{ padding: '0.3rem 0.55rem', fontSize: '0.72rem', cursor: 'pointer', color: o.valid ? 'var(--text-main)' : 'var(--color-danger)' }}
              title={o.valid ? 'Approved' : 'Not on the approved list — will trigger a flag'}>
              {o.valid ? '' : '⚠️ '}{o.label}{o.valid ? '' : ' — not approved'}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function FieldDock({ fields, onSubmit, busy, defaults = {}, formId, hideSubmit = false }) {
  const [values, setValues] = useState(() =>
    Object.fromEntries(fields.map((f) => [
      f.name,
      defaults[f.name] || f.value || (f.type === 'select' ? (f.options?.[0]?.value ?? '') : ''),
    ]))
  );
  const set = (name, v) => setValues((prev) => ({ ...prev, [name]: v }));
  const ready = fields.every((f) => !f.required || String(values[f.name] ?? '').trim() !== '');
  return (
    <form id={formId} onSubmit={(e) => { e.preventDefault(); if (ready && !busy) onSubmit(values); }}
      style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', width: '100%' }}>
      {fields.map((f) => (
        <div key={f.name} style={{ display: 'flex', flexDirection: 'column', gap: '0.2rem' }}>
          {/* These are the fields the mesh is WAITING on — make them unmissable. */}
          <label style={{ fontSize: '0.85rem', fontWeight: 700, color: 'var(--text-main)' }}>⚠️ {f.label}{f.required ? ' *' : ''}</label>
          {f.type === 'select' ? (
            <select className="top-textarea" value={values[f.name]} onChange={(e) => set(f.name, e.target.value)}>
              {(f.options || []).map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
          ) : f.type === 'textarea' ? (
            <textarea className="top-textarea" rows={3} placeholder={f.placeholder || ''}
              value={values[f.name]} onChange={(e) => set(f.name, e.target.value)} style={{ resize: 'vertical' }} />
          ) : (
            <input className="top-textarea" type={f.type === 'number' ? 'number' : 'text'}
              placeholder={f.placeholder || ''} value={values[f.name]} onChange={(e) => set(f.name, e.target.value)} />
          )}
        </div>
      ))}
      {!hideSubmit && (
        <button type="submit" className="preset-btn primary" disabled={!ready || busy} style={{ alignSelf: 'flex-start' }}>
          <Send size={13} style={{ marginRight: '4px', verticalAlign: 'middle' }} />
          {busy ? 'Sending…' : 'Submit answer'}
        </button>
      )}
    </form>
  );
}

// ---- Chat bubble ----
function Bubble({ msg }) {
  if (msg.role === 'user') {
    return (
      <div style={{ alignSelf: 'flex-end', maxWidth: '80%', background: 'var(--accent-blue)', color: '#fff', padding: '0.5rem 0.75rem', borderRadius: '0.6rem 0.6rem 0.15rem 0.6rem', fontSize: '0.78rem' }}>
        {msg.text}
      </div>
    );
  }
  const isSystem = msg.role === 'system';
  return (
    <div style={{ alignSelf: 'flex-start', maxWidth: '92%', background: 'var(--bg-secondary)', border: `1px solid ${isSystem ? 'var(--color-warning)' : 'var(--glass-border)'}`, padding: '0.55rem 0.75rem', borderRadius: '0.6rem 0.6rem 0.6rem 0.15rem', fontSize: '0.78rem' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', fontSize: '0.68rem', color: 'var(--text-muted)', marginBottom: msg.text ? '0.35rem' : 0 }}>
        <Satellite size={11} /> {isSystem ? 'System' : 'Orchestrator'}
      </div>
      {msg.text && <div style={{ whiteSpace: 'pre-wrap' }}>{msg.text}</div>}
    </div>
  );
}

// ---- Per-component mesh status (agents + their MCP servers) ----
const shortMcp = (name) => name.replace(/^MCP_/, '').replace(/_URL$/, '').toLowerCase();
function MeshStatus({ components }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
      {components.map((c) => (
        <div key={c.name} style={{ background: 'var(--bg-secondary)', border: `1px solid ${c.ok ? 'var(--glass-border)' : 'var(--color-danger)'}`, borderRadius: '0.4rem', padding: '0.4rem 0.6rem' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.78rem', fontWeight: 700 }}>
            <span>{c.ok ? '🟢' : '🔴'} {c.label}</span>
            <span style={{ color: c.ok ? 'var(--color-success)' : 'var(--color-danger)', fontWeight: 400, fontSize: '0.7rem' }}>
              {c.reachable ? (c.ok ? 'healthy' : 'degraded') : 'unreachable'}
            </span>
          </div>
          {c.error && <div style={{ fontSize: '0.68rem', color: 'var(--color-danger)', marginTop: '0.2rem' }}>{c.error}</div>}
          {(c.mcp || []).length > 0 && (
            <div style={{ marginTop: '0.3rem', display: 'flex', flexWrap: 'wrap', gap: '0.3rem' }}>
              {c.mcp.map((m) => (
                <span key={m.name} title={m.detail} style={{ fontSize: '0.66rem', padding: '0.15rem 0.4rem', borderRadius: '0.25rem', background: 'var(--bg-tertiary)', color: m.ok ? 'var(--text-muted)' : 'var(--color-danger)', border: `1px solid ${m.ok ? 'var(--glass-border)' : 'var(--color-danger)'}` }}>
                  {m.ok ? '✅' : '❌'} {shortMcp(m.name)} · {m.detail}
                </span>
              ))}
            </div>
          )}
          {c.reachable && (c.mcp || []).length === 0 && !c.error && (
            <div style={{ fontSize: '0.66rem', color: 'var(--text-muted)', marginTop: '0.2rem' }}>no MCP dependencies</div>
          )}
        </div>
      ))}
    </div>
  );
}

// ---- Live workflow graph (right pane): nodes light up + show status as the run goes ----
const WF_STATUS = {
  running:     { fill: '#15304f', border: '#4a9eff', dot: '#4a9eff', label: 'running' },
  cleared:     { fill: '#123726', border: '#3ddc84', dot: '#3ddc84', label: 'cleared' },
  compliant:   { fill: '#123726', border: '#3ddc84', dot: '#3ddc84', label: 'compliant' },
  done:        { fill: '#123726', border: '#3ddc84', dot: '#3ddc84', label: 'done' },
  rejected:    { fill: '#3a2f12', border: '#ffc24a', dot: '#ffc24a', label: 'rejected' },
  blocked:     { fill: '#3a1717', border: '#ff5c5c', dot: '#ff5c5c', label: 'blocked' },
  failed:      { fill: '#2e1420', border: '#ff6b9d', dot: '#ff6b9d', label: 'failed' },
  needs_input: { fill: '#3a2f12', border: '#ffc24a', dot: '#ffc24a', label: 'needs input' },
  awaiting:    { fill: '#3a2f12', border: '#ffc24a', dot: '#ffc24a', label: 'awaiting input' },
  flagged:     { fill: '#3a2f12', border: '#ffc24a', dot: '#ffc24a', label: 'flagged' },
  unverified:  { fill: '#3a2f12', border: '#ffc24a', dot: '#ffc24a', label: 'unverified' },
  escalated:   { fill: '#2a2140', border: '#a98bff', dot: '#a98bff', label: 'escalated ⏫' },
  reused:      { fill: '#1c1c1c', border: '#3a3a3a', dot: '#666', label: 'reused' },
  pending:     { fill: '#1c1c1c', border: '#3a3a3a', dot: '#777', label: 'queued' },
};

// Statuses a workflow can be in that the operator may want to escalate (can't be cleared
// by editing inputs). Gates the "raise exception request" control.
const ESCALATABLE = new Set(['flagged', 'unverified', 'blocked', 'needs_input', 'failed']);

// Requested-field tokens already covered by the standard inputs — filtered out of the
// FieldDock in the combined-edit view so they aren't shown twice (their values still flow
// through submitFields from the standard inputs' state).
const STD_TOKENS = new Set(['image', 'image_uri', 'medium', 'character', 'vendor', 'market', 'target_market', 'volume', 'category', 'product_category']);

function WorkflowGraph({ graph, components, mcpTools, toolLights }) {
  const nodes = graph ? Object.values(graph) : [];
  if (!nodes.length) {
    return <div style={{ padding: '1.2rem 0.6rem', fontSize: '0.72rem', color: 'var(--text-muted)', textAlign: 'center', lineHeight: 1.5 }}>
      Run an audit — the workflow graph builds here, lighting up each agent as it runs.
    </div>;
  }
  const W = 760, NW = 224, NH = 60;                 // 2× type on a wider canvas
  const BOX_HDR = 22, ROW_H = 16, BOX_PAD = 6, BOX_GAP = 12, STACK_DY = 14;

  // MCP servers each agent talks to — from the live readiness probe (/api/ready),
  // so the topology isn't hardcoded and each server box carries real health. The
  // private legal agent isn't in readiness; it writes contracts via mcp_licensing,
  // so it reuses that server's entry from its parent's list (box only, no tools —
  // the licensing tools are already boxed under Vendor Clearance).
  const chipLabel = (m) => (m.name || '').replace(/^MCP_/, '').replace(/_URL$/, '').toLowerCase();
  const mcpFor = (n) => {
    const comp = (components || []).find((c) => (n.id || '').startsWith(c.name));
    if (comp) return comp.mcp || [];
    if (n.id === 'legal') {
      const lic = (components || []).flatMap((c) => c.mcp || []).find((m) => (m.name || '').includes('LICENSING'));
      return lic ? [lic] : [];
    }
    return [];
  };
  const toolsOf = (m) => (((mcpTools || {})[chipLabel(m)] || {}).tools || []);
  const stepsOf = (m) => (((mcpTools || {})[chipLabel(m)] || {}).steps || {});
  // Row count for a server box: one row per tool + one per declared pipeline step.
  const rowCount = (m) => toolsOf(m).reduce((n, t) => n + 1 + ((stepsOf(m)[t] || []).length), 0);

  const root = nodes.find((n) => !n.parent);
  const l1 = nodes.filter((n) => root && n.parent === root.id);
  const l2 = nodes.filter((n) => n.parent && (!root || n.parent !== root.id));
  const l1Y = 116;
  const pos = {};
  if (root) pos[root.id] = { x: (W - NW) / 2, y: 14 };
  const gap = 24;
  const total = l1.length * NW + Math.max(0, l1.length - 1) * gap;
  const x0 = Math.max(8, (W - total) / 2);
  l1.forEach((n, i) => { pos[n.id] = { x: x0 + i * (NW + gap), y: l1Y }; });
  // l2 (legal) x under its parent now; its y is set BELOW the MCP layer (computed
  // next) so the agent→MCP edges don't have to weave around it.
  l2.forEach((n) => { const p = pos[n.parent] || { x: (W - NW) / 2 }; pos[n.id] = { x: p.x, y: 0 }; });

  // ---- Shared MCP layer: each server appears ONCE, with dashed edges from every
  // agent that talks to it (no duplicate boxes). Tools live INSIDE the server box.
  const servers = {};
  [...l1, ...l2].forEach((n) => {
    mcpFor(n).forEach((m) => {
      const label = chipLabel(m);
      if (!servers[label]) servers[label] = { label, url: m.url, ok: m.ok, tools: toolsOf(m),
        steps: stepsOf(m), rows: rowCount(m), consumers: [] };
      if (!servers[label].consumers.includes(n.id)) servers[label].consumers.push(n.id);
    });
  });
  const consumerX = (s) => s.consumers.reduce((sum, id) => sum + ((pos[id]?.x ?? 0) + NW / 2), 0) / (s.consumers.length || 1);
  const serverList = Object.values(servers).sort((a, b) => consumerX(a) - consumerX(b));
  const k = serverList.length;
  const SBW = k ? Math.min(NW, (W - 16 * (k - 1) - 16) / k) : NW;
  const mcpY = l1Y + NH + 46;
  serverList.forEach((s, i) => {
    s.x = Math.max(8, (W - (k * SBW + (k - 1) * 16)) / 2) + i * (SBW + 16);
    s.h = BOX_HDR + s.rows * ROW_H + BOX_PAD;
  });
  const mcpMaxH = Math.max(40, ...serverList.map((s) => s.h));
  // Legal sits BELOW the MCP layer (its vendor→legal edge ducks behind the server
  // boxes, which paint over it — no crowding in the agent/MCP band).
  const l2Y = mcpY + mcpMaxH + 42;
  l2.forEach((n) => { pos[n.id].y = l2Y; });
  const H = l2.length ? l2Y + NH + 14 : mcpY + mcpMaxH + 14;

  const edge = (a, b, dashed) => {
    const pa = pos[a], pb = pos[b]; if (!pa || !pb) return null;
    const x1 = pa.x + NW / 2, y1 = pa.y + NH, x2 = pb.x + NW / 2, y2 = pb.y, my = (y1 + y2) / 2;
    return <path key={`${a}-${b}`} d={`M ${x1} ${y1} C ${x1} ${my}, ${x2} ${my}, ${x2} ${y2}`}
      fill="none" stroke="var(--glass-border, #444)" strokeWidth="2" strokeDasharray={dashed ? '5 5' : undefined} />;
  };

  // Dashed agent → MCP-server edge (MCP-over-HTTP), fanned across the box edge so
  // multiple consumers don't overlap. Consumers ABOVE the layer attach to the box
  // top; consumers BELOW it (legal) attach to the box bottom.
  const mcpEdge = (nodeId, s, idx) => {
    const pa = pos[nodeId]; if (!pa) return null;
    const below = pa.y > mcpY;
    const x1 = pa.x + NW / 2, y1 = below ? pa.y : pa.y + NH;
    const spread = SBW / (s.consumers.length + 1);
    const x2 = s.x + spread * (idx + 1), y2 = below ? mcpY + Math.max(40, s.h) : mcpY;
    const my = (y1 + y2) / 2;
    return <path key={`${nodeId}-${s.label}`} d={`M ${x1} ${y1} C ${x1} ${my}, ${x2} ${my}, ${x2} ${y2}`}
      fill="none" stroke="var(--glass-border, #444)" strokeWidth="1.6" strokeDasharray="4 4" />;
  };

  // One MCP-server box: header (name + health) with the server's TOOLS inside, each
  // with an activity LED. LEDs are addressable two ways:
  //   • React: the `toolLights` map — key `<mcp>/<tool>` → 'on' | 'blink'
  //     (window.vibeflixToolLight('licensing/get_vendor', 'blink') from anywhere)
  //   • DOM: every row carries data-led="<mcp>/<tool>" for direct manipulation.
  const ServerBox = ({ s }) => {
    const color = s.ok === true ? '#3ddc84' : s.ok === false ? '#ff5c5c' : '#777';
    const maxChars = Math.floor((SBW - 34) / 6.2);
    return (
      <g>
        <rect x={s.x} y={mcpY} width={SBW} height={Math.max(40, s.h)} rx="7"
          fill="var(--bg-tertiary, #1c1c1c)" stroke={color} strokeWidth="1.2" opacity="0.96" />
        <circle cx={s.x + 12} cy={mcpY + BOX_HDR / 2 + 1} r="3.5" fill={color} />
        <text x={s.x + 21} y={mcpY + BOX_HDR / 2 + 5} fontSize="12" fontWeight="700"
          fill="var(--wf-mcp-title, #174ea6)">{`mcp_${s.label}`}</text>
        <title>{`mcp_${s.label} — ${s.url || ''} (${s.ok === true ? 'ok' : s.ok === false ? 'DOWN' : 'unknown'})`}</title>
        {s.tools.length > 0 && (
          <line x1={s.x + 8} y1={mcpY + BOX_HDR} x2={s.x + SBW - 8} y2={mcpY + BOX_HDR}
            stroke="var(--glass-border, #444)" strokeWidth="0.8" />
        )}
        {(() => {
          // Flatten tools + their declared PIPELINE STEPS into rows; steps render
          // indented under their tool with their own LEDs (key `<mcp>/<tool>.<step>`).
          const rows = [];
          s.tools.forEach((t) => {
            rows.push({ key: `${s.label}/${t}`, text: t, indent: 0 });
            ((s.steps || {})[t] || []).forEach((st) =>
              rows.push({ key: `${s.label}/${t}.${st}`, text: st, indent: 1 }));
          });
          return rows.map((row, j) => {
            const ty = mcpY + BOX_HDR + 11 + j * ROW_H;
            const mode = (toolLights || {})[row.key];
            const lit = mode === 'on' || mode === 'blink';
            const ind = row.indent * 14;
            return (
              <g key={row.key} data-led={row.key}>
                {row.indent > 0 && (
                  <path d={`M ${s.x + 16} ${ty - ROW_H + 5} L ${s.x + 16} ${ty} L ${s.x + 22 + ind - 12} ${ty}`}
                    stroke="var(--glass-border, #555)" strokeWidth="0.8" fill="none" />
                )}
                <circle className={mode === 'blink' ? 'wf-led-blink' : ''}
                  cx={s.x + 14 + ind} cy={ty} r={row.indent ? 3.2 : 4}
                  fill={lit ? '#3ddc84' : 'var(--glass-border, #555)'} />
                <text x={s.x + 26 + ind} y={ty + 4} fontSize={row.indent ? 10 : 11}
                  fontWeight={lit ? 700 : 400}
                  fill={lit ? 'var(--wf-mcp-title, #174ea6)' : 'var(--text-muted, #999)'}>
                  {row.text.length > maxChars - row.indent * 2
                    ? row.text.slice(0, maxChars - row.indent * 2 - 1) + '…' : row.text}
                </text>
                <title>{`${s.label} · ${row.key.split('/')[1]}`}</title>
              </g>
            );
          });
        })()}
      </g>
    );
  };

  const NodeBox = ({ n }) => {
    const p = pos[n.id]; if (!p) return null;
    // Unknown status (a new agent's vocabulary) → neutral style but show the REAL
    // status text, never a misleading 'queued'.
    const s = WF_STATUS[n.status] || { ...WF_STATUS.pending, label: n.status || 'queued' };
    return (
      <g className={n.status === 'running' ? 'wf-running' : ''}>
        <rect x={p.x} y={p.y} width={NW} height={NH} rx="11" fill={s.fill} stroke={s.border}
          strokeWidth={n.status === 'running' ? 2.6 : 1.6} strokeDasharray={n.status === 'reused' ? '5 4' : undefined} />
        <circle cx={p.x + 18} cy={p.y + 20} r="5.5" fill={s.dot} />
        {/* Node fills are dark in BOTH themes (status colors), so the title is a
            fixed light color — theme-aware text would go black-on-dark in light mode. */}
        <text x={p.x + NW / 2} y={p.y + 26} textAnchor="middle" fontSize="16" fontWeight="700" fill="#e8eaed">{n.label}</text>
        <text x={p.x + NW / 2} y={p.y + 46} textAnchor="middle" fontSize="12" fill={s.dot}>{s.label}</text>
      </g>
    );
  };

  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" style={{ maxHeight: '100%' }}>
      {root && l1.map((n) => edge(root.id, n.id, false))}
      {/* vendor → legal is a real A2A hand-off: SOLID. Drawn before the server
          boxes so the long edge ducks behind the MCP layer. */}
      {l2.map((n) => edge(n.parent, n.id, false))}
      {serverList.flatMap((s) => s.consumers.map((id, i) => mcpEdge(id, s, i)))}
      {serverList.map((s) => <ServerBox key={s.label} s={s} />)}
      {nodes.map((n) => <NodeBox key={n.id} n={n} />)}
    </svg>
  );
}

export default function ChatAudit() {
  const [messages, setMessages] = useState([
    { role: 'system', text: 'Start an audit below. I\'ll run the multi-agent mesh and ask for anything I still need as we go.' },
  ]);
  const [phase, setPhase] = useState('start');   // start | running | awaiting | done
  const [fields, setFields] = useState(null);
  const [sessionId, setSessionId] = useState(null);
  const [busy, setBusy] = useState(false);
  // Live workflow graph (right pane): keyed by node id, driven by `graph` SSE events.
  const [graph, setGraph] = useState(null);
  // The audit this console is showing. The app mints it per run and sends it as the
  // first SSE frame; the mesh feed is filtered against it so a finished run's events
  // can't paint the current graph. Refs, not state: the mesh EventSource handler is
  // installed once and would otherwise close over a stale value.
  const runIdRef = useRef(null);
  const runActiveRef = useRef(false);

  const [imageUri, setImageUri] = useState('');
  // Set when a run ends fully passed with an executed contract — the session is final.
  const [contractId, setContractId] = useState('');
  const [market, setMarket] = useState('North America');
  const [volume, setVolume] = useState(15000);
  const [medium, setMedium] = useState('');
  const [character, setCharacter] = useState('');
  const [productCategory, setProductCategory] = useState('');
  const [vendor, setVendor] = useState('');
  const [uploading, setUploading] = useState(false);
  const [escalating, setEscalating] = useState(false);
  const [exReason, setExReason] = useState('');
  const [note, setNote] = useState('');          // question/context; submitted WITH the audit
  const [netUnitPrice, setNetUnitPrice] = useState('');  // deal pricing → deal_pricing agent
  const [agreedRate, setAgreedRate] = useState('');
  const [agreedAdvance, setAgreedAdvance] = useState('');
  const [agreedMg, setAgreedMg] = useState('');

  // Trademark/character options from the registry (mcp_licensing.list_trademarks via
  // /api/trademarks) — so the picker offers valid ids instead of free-text.
  const [characters, setCharacters] = useState([]);
  useEffect(() => {
    fetch(`${API_BASE}/api/trademarks`).then((r) => r.json())
      .then((d) => setCharacters(d.trademarks || [])).catch(() => {});
  }, []);

  // Layer-2 readiness: poll /api/ready; the console locks only when the mesh is
  // *persistently* not-ready (debounced), so a transient blip while agents are
  // busy never hides the inputs.
  const [ready, setReady] = useState(null);        // null=checking | true | false
  const [components, setComponents] = useState([]);
  // MCP tool inventory ({ licensing: [tool, ...], ... }) for the graph's tool rows.
  const [mcpTools, setMcpTools] = useState({});
  // Every LED row key the graph knows about (`<chipLabel>/<tool>` and `<…>/<tool>.<step>`).
  // The mesh handler logs an incoming LED key against this set, so "the event arrived but
  // no row matches it" is DISTINGUISHABLE from "the event never arrived".
  const ledKeysRef = useRef(new Set());
  useEffect(() => {
    const keys = new Set();
    Object.entries(mcpTools || {}).forEach(([label, v]) => {
      (v.tools || []).forEach((t) => {
        keys.add(`${label}/${t}`);
        ((v.steps || {})[t] || []).forEach((st) => keys.add(`${label}/${t}.${st}`));
      });
    });
    ledKeysRef.current = keys;
    if (keys.size) console.debug('[vibeflix] LED rows:', [...keys].join(', '));
  }, [mcpTools]);
  // Tool activity LEDs: key `<mcp>/<tool>` → 'on' | 'blink' | undefined (off).
  // Driven by the Pub/Sub live-telemetry bridge (window.vibeflixToolLight below).
  const [toolLights, setToolLights] = useState({});
  useEffect(() => {
    fetch(`${API_BASE}/api/mcp/tools`)
      .then((r) => r.json())
      .then((d) => setMcpTools(Object.fromEntries(
        Object.entries(d.servers || {}).map(([k, v]) => [k, { tools: v.tools || [], steps: v.steps || {} }]))))
      .catch(() => {});
  }, []);
  useEffect(() => {
    // Global hook for manual control too: vibeflixToolLight('licensing/get_vendor',
    // 'blink'), 'on', or null/undefined to turn it off.
    window.vibeflixToolLight = (key, mode) => setToolLights((m) => ({ ...m, [key]: mode || undefined }));
    return () => { delete window.vibeflixToolLight; };
  }, []);
  useEffect(() => {
    // Live mesh telemetry (Pub/Sub → app bridge → SSE): tool events drive the LEDs —
    // blink while the tool runs, linger solid green for a beat on completion so even
    // fast calls are visible. EventSource auto-reconnects.
    // BUILD STAMP — the single fastest way to tell whether the browser is running the
    // bundle we just shipped or a cached one. If this line is absent from the console,
    // the page is stale and NOTHING else we conclude from the UI is trustworthy.
    console.info('[vibeflix] console build: led-diag-1 · mesh filter = run_id-only');
    const timers = {};
    const litAt = { current: {} };   // key → ts of `started`, so an instant tool still blinks
    const es = new EventSource(`${API_BASE}/api/mesh/events`);
    es.onmessage = (ev) => {
      let e; try { e = JSON.parse(ev.data); } catch { return; }

      // ── Run scoping ──────────────────────────────────────────────────────────
      // The mesh bus is shared: every console receives every event from every run, and
      // events outlive their run (late delivery, Pub/Sub redelivery, a second tab). A
      // STAMPED event belongs to a known run, so render it only if that run is the one
      // on screen — this is what stops a finished audit repainting the current graph
      // (a stale event always carries its OWN, different, id).
      //
      // UNSTAMPED events (the MCP servers — they serve a tool call and have no idea
      // which audit it belongs to) are let through. Do NOT also gate them on "this tab
      // has a run in flight": that is exactly what made the tool LEDs stop lighting up.
      // They cost nothing when stale — a LED self-extinguishes (1.6s solid / 15s
      // watchdog) — and the graph, which is what run scoping is FOR, is built only from
      // stamped orchestrator events anyway.
      if (e.run_id && e.run_id !== runIdRef.current) {
        console.debug('[mesh] DROP (other run)', e.run_id, '≠', runIdRef.current, e.source, e.node || e.tool);
        return;
      }

      // The legal hand-off announces itself (node: "legal") the moment it starts —
      // materialize/update the graph node immediately instead of waiting for
      // vendor_clearance's final report to reach the audit stream.
      if (e.node === 'legal' && e.source === 'vendor_clearance') {
        const status = e.event === 'started' ? 'running'
          : e.event === 'needs_input' ? 'needs_input'
          : e.event === 'failed' ? 'blocked' : (e.status || 'cleared');
        setGraph((g) => g ? { ...g, legal: { id: 'legal', label: '⚖️ Legal Clearance',
          parent: 'vendor_clearance_agent', status } } : g);
        return;
      }
      // A WORKFLOW-NODE event from the orchestrator (no `tool`) — light that graph node
      // LIVE, and materialize it if the plan hasn't arrived yet.
      //
      // Why this is needed: the orchestrator is now an INDEPENDENT agent, reached over
      // A2A. A2A hands back its RESULT, not its internal step events — so the app can no
      // longer stream a `__plan__` + per-agent reports as they happen, and the graph
      // would sit empty until the run finished. The orchestrator publishes started/
      // completed for each agent it dispatches (vibeflix_common.telemetry), so the graph
      // builds itself from the mesh feed instead. Same mechanism the legal node above
      // already used.
      if (e.node && !e.tool && e.source === 'orchestrator') {
        const status = e.event === 'started' ? 'running'
          : e.event === 'failed' ? 'failed'
          : (e.status || 'completed');
        const label = e.node.replace(/_agent$/, '').replace(/_/g, ' ')
          .replace(/\b\w/g, (c) => c.toUpperCase());
        setGraph((g) => ({
          ...(g || {}),
          [e.node]: { ...(g?.[e.node] || { id: e.node, label }), status },
        }));
        return;
      }
      if (!e.tool) { console.debug('[mesh] ignored (no tool, not an orchestrator node)', e); return; }
      const key = `${(e.source || '').replace(/^mcp_/, '')}/${e.tool}`;
      // ⚑ LED DIAGNOSTIC. The LED only lights if this key matches a ROW key the graph
      // built from /api/mcp/tools (`<chipLabel>/<tool>`). Log both so a mismatch — or a
      // missing row — is visible instead of silently doing nothing.
      const known = ledKeysRef.current;
      console.debug(`[mesh] LED ${key} = ${e.event}`,
        known.size ? (known.has(key) ? '✓ row exists' : `✗ NO ROW — known keys: ${[...known].join(', ')}`)
                   : '(no rows yet — /api/mcp/tools not loaded or graph empty)');
      // ── MAKE THE LED VISIBLE ─────────────────────────────────────────────────────
      // These MCP tools run in MILLISECONDS, so `started` and `completed` land in the
      // same tick: React coalesced them into one render and the LED went blink→solid→off
      // in ~1.6s. It was firing correctly the whole time — you just could not SEE it.
      // So: hold the blink for a minimum, THEN linger solid. An instant tool now reads as
      // roughly BLINK_MIN + LINGER of unmistakable green.
      const BLINK_MIN = 900;    // a tool that returns instantly still visibly blinks
      const LINGER = 2600;      // then sits solid green long enough to register
      const WATCHDOG = 15000;   // a blink ALWAYS self-extinguishes (see below)
      clearTimeout(timers[key]);
      if (e.event === 'started') {
        mark('first MCP call (LED)');
        litAt.current[key] = Date.now();
        setToolLights((m) => ({ ...m, [key]: 'blink' }));
        // WATCHDOG. Pub/Sub does NOT guarantee ordering: `completed` can be delivered
        // BEFORE `started`. Without this, the late `started` re-lights a tool that has
        // already finished and nothing ever clears it — the LED stays on forever.
        timers[key] = setTimeout(
          () => setToolLights((m) => ({ ...m, [key]: undefined })), WATCHDOG);
      } else {  // completed / failed → hold the blink briefly, then solid, then off
        const elapsed = Date.now() - (litAt.current[key] || 0);
        const hold = Math.max(0, BLINK_MIN - elapsed);
        setToolLights((m) => ({ ...m, [key]: m[key] === 'blink' ? 'blink' : 'on' }));
        timers[key] = setTimeout(() => {
          setToolLights((m) => ({ ...m, [key]: 'on' }));
          timers[key] = setTimeout(
            () => setToolLights((m) => ({ ...m, [key]: undefined })), LINGER);
        }, hold);
      }
    };
    return () => { es.close(); Object.values(timers).forEach(clearTimeout); };
  }, []);
  const failsRef = useRef(0);
  useEffect(() => {
    let alive = true;
    const check = async () => {
      try {
        const res = await fetch(`${API_BASE}/api/ready`);
        const d = await res.json();
        if (!alive) return;
        setComponents(d.components || []);
        if (d.ready) { failsRef.current = 0; setReady(true); }
        else { failsRef.current += 1; if (failsRef.current >= 2) setReady(false); }
      } catch {
        if (!alive) return;
        failsRef.current += 1;
        if (failsRef.current >= 2) { setReady(false); setComponents([]); }
      }
    };
    check();
    const id = setInterval(check, 5000);
    return () => { alive = false; clearInterval(id); };
  }, []);
  const readyCount = components.filter((c) => c.ok).length;

  const scrollRef = useRef(null);
  const pmRef = useRef(null);       // A2UI processMessages, set by <A2UIBridge>
  const runSeq = useRef(0);         // monotonic run id → per-run surface id
  const runTokenRef = useRef(null); // prior-audit token → incremental re-run
  // ── Client-perceived latency timeline ────────────────────────────────────────────
  // Logs each user-visible milestone's offset from submit to the browser console
  // (filter: "[timing]"). Complements the backend Cloud Trace: it captures the
  // SSE-delivery + React-render time the server-side spans can't see, and lets us see
  // wall-clock the way the USER experiences it (submit → agents appear → first MCP LED
  // → response rendered).
  const perfRef = useRef({ t0: 0, seen: {} });
  const mark = (label) => {
    const now = (typeof performance !== 'undefined' ? performance.now() : Date.now());
    const p = perfRef.current;
    if (label === 'submit') { p.t0 = now; p.seen = {}; console.info('[timing] ───── submit (t0) ─────'); return; }
    if (!p.t0 || p.seen[label]) return;         // record only the FIRST occurrence
    p.seen[label] = now;
    console.info(`[timing] ${label.padEnd(28)} +${((now - p.t0) / 1000).toFixed(2)}s`);
  };
  useEffect(() => { const el = scrollRef.current; if (el) el.scrollTop = el.scrollHeight; }, [messages, phase]);

  const push = (m) => setMessages((prev) => [...prev, m]);

  // Stream an audit: POST /api/audit/stream and feed each SSE A2UI message to the
  // live renderer via pmRef. Each run paints its OWN surface (`audit-<n>`) as a new
  // transcript entry, so a re-run appends below instead of overwriting the last.
  const runStream = async (request, fallbackPhase) => {
    mark('submit');
    setBusy(true); setPhase('running'); setFields(null);
    // Arm the mesh filter for a NEW run: drop the previous run's id immediately (its
    // in-flight events are now stale) and accept unstamped MCP tool events again.
    // The real id arrives in the first SSE frame, below.
    runIdRef.current = null;
    runActiveRef.current = true;
    // Keep prior nodes across a re-run (only orchestrator flips to running); the plan
    // decides which workflows actually re-run — the rest keep their last state.
    setGraph((g) => ({ ...(g || {}), orchestrator: { id: 'orchestrator', label: 'Orchestrator', status: 'running' } }));
    const surfaceId = `audit-${++runSeq.current}`;
    push({ role: 'surface', surfaceId });
    try {
      const res = await fetch(`${API_BASE}/api/audit/stream`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(request),
      });
      if (!res.ok || !res.body) throw new Error(`Backend ${res.status}`);
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buf = '';
      let ended = false;
      while (!ended) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        let sep;
        while ((sep = buf.indexOf('\n\n')) >= 0) {
          const frame = buf.slice(0, sep); buf = buf.slice(sep + 2);
          const dataLine = frame.split('\n').find((l) => l.startsWith('data: '));
          if (!dataLine) continue;
          let d; try { d = JSON.parse(dataLine.slice(6)); } catch { continue; }
          if (d.event === 'run') {
            mark('run acknowledged (1st byte)');
            // The id the orchestrator will stamp on this run's mesh events.
            runIdRef.current = d.run_id;
          } else if (d.a2ui) {
            pmRef.current?.([retarget(d.a2ui, surfaceId)]);
          } else if (d.event === 'graph') {
            if (d.op === 'plan') {
              mark('agents appeared (plan)');
              setGraph((g) => {
                const next = { ...(g || {}), orchestrator: (g?.orchestrator) || { id: 'orchestrator', label: 'Orchestrator', status: 'running' } };
                for (const n of d.nodes) {
                  const prev = next[n.id];
                  // run → running; not run → keep whatever state it was left in (don't relabel "reused").
                  next[n.id] = { id: n.id, label: n.label, parent: 'orchestrator',
                    status: n.run ? 'running' : (prev?.status || 'pending') };
                }
                return next;
              });
            } else if (d.op === 'status') {
              setGraph((g) => ({
                ...(g || {}),
                [d.id]: { ...(g?.[d.id] || { id: d.id, label: d.label || d.id, parent: d.parent }), status: d.status, ...(d.parent ? { parent: d.parent } : {}), ...(d.label ? { label: d.label } : {}) },
              }));
            }
          } else if (d.event === 'note_response') {
            push({ role: 'agent', text: d.text });
          } else if (d.event === 'done') {
            mark('response received (done)');
            if (typeof requestAnimationFrame !== 'undefined') requestAnimationFrame(() => mark('rendered (paint)'));
            if (d.run_token) runTokenRef.current = d.run_token;
            // The sourcing decision changed the effective volume (cap/split) — sync
            // the form to the REAL number so re-submits don't re-trip the cap gate.
            if (d.capped_volume) {
              setVolume(d.capped_volume);
              push({ role: 'system', text: `📦 Production volume updated to ${Number(d.capped_volume).toLocaleString()} units per your sourcing decision.` });
            }
            setGraph((g) => g ? { ...g, orchestrator: { ...g.orchestrator, status: 'done' } } : g);
            // Fully passed (contract executed / all cleared) → the session is FINAL:
            // re-submitting is disabled; only New starts another audit.
            if (d.passed) { setContractId(d.contract_id || ''); setPhase('complete'); }
            else setPhase('done');
            ended = true;
          } else if (d.event === 'input_required') {
            if (d.run_token) runTokenRef.current = d.run_token;
            setGraph((g) => g ? { ...g, orchestrator: { ...g.orchestrator, status: 'awaiting' } } : g);
            push({ role: 'agent', text: d.prompt }); setFields(d.fields); setPhase('awaiting'); ended = true;
          } else if (d.event === 'error') {
            push({ role: 'system', text: `Error: ${d.message}` }); setPhase('done'); ended = true;
          }
        }
      }
    } catch (e) {
      push({ role: 'system', text: `Stream failed: ${e.message} (is the mesh running?)` });
      setPhase(fallbackPhase);
    } finally {
      setBusy(false);
      // Run is over (done / awaiting input / error): stop accepting unstamped tool
      // events. Keep runIdRef so this run's own trailing events still land.
      runActiveRef.current = false;
    }
  };

  // run_token threads the prior audit so the orchestrator re-runs only affected
  // workflows. Carried on every submit in a session; cleared by "New".
  const startAudit = () => {
    push({ role: 'user', text: `Audit ${imageUri}\n${character ? `${character} · ` : ''}${market} · ${Number(volume).toLocaleString()} units${medium ? ` · medium: ${medium}` : ''}${note ? `\n💬 ${note}` : ''}` });
    runStream({ image_uri: imageUri, target_market: market, volume: Number(volume), character, product_category: productCategory, vendor, medium, note, net_unit_price: Number(netUnitPrice) || 0, agreed_royalty_rate: (Number(agreedRate) || 0) / 100, agreed_advance: Number(agreedAdvance) || 0, agreed_mg: Number(agreedMg) || 0, run_token: runTokenRef.current }, 'start');
    setNote('');
  };
  const submitFields = (values) => {
    // Streaming resume = re-stream with the collected fields merged into the request.
    // The field `name`s match the request keys, so merge them generically + persist.
    if (values.image_uri) setImageUri(values.image_uri);
    if (values.medium !== undefined) setMedium(values.medium);
    if (values.character) setCharacter(values.character);
    if (values.product_category) setProductCategory(values.product_category);
    if (values.vendor) setVendor(values.vendor);
    if (values.target_market) setMarket(values.target_market);
    push({ role: 'user', text: [Object.entries(values).map(([k, v]) => `${k} = ${v}`).join('\n'), note ? `💬 ${note}` : ''].filter(Boolean).join('\n') });
    runStream({
      // Spread FIRST so every asked-field token (sourcing_choice, legal_safety_cert,
      // future tokens) reaches the backend; the explicit keys below override.
      ...values,
      image_uri: values.image_uri || imageUri,
      target_market: values.target_market || market,
      volume: Number(volume),
      character: values.character || character,
      product_category: values.product_category || productCategory,
      vendor: values.vendor || vendor,
      new_vendor: values.new_vendor || '',
      add_category_approved: values.add_category_approved || '',
      medium: values.medium ?? medium,
      note,
      net_unit_price: Number(netUnitPrice) || 0,
      agreed_royalty_rate: (Number(agreedRate) || 0) / 100,
      agreed_advance: Number(agreedAdvance) || 0,
      agreed_mg: Number(agreedMg) || 0,
      run_token: runTokenRef.current,
    }, 'awaiting');
    setNote('');
  };
  // Mocked exception/escalation: POST the flagged workflows to /api/escalate, show the
  // returned ticket, and mark those nodes 'escalated' on the graph.
  const raiseException = async () => {
    const g = graph || {};
    const wfs = Object.entries(g)
      .filter(([id, n]) => id !== 'orchestrator' && ESCALATABLE.has(n.status))
      .map(([, n]) => n.label || n.id);
    setEscalating(true);
    try {
      const res = await fetch(`${API_BASE}/api/escalate`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ workflows: wfs, reason: exReason, run_token: runTokenRef.current }),
      });
      const d = await res.json();
      push({ role: 'system', text: `⏫ ${d.message || 'Request escalated.'}` });
      setGraph((cur) => {
        if (!cur) return cur;
        const next = { ...cur };
        for (const [id, n] of Object.entries(next)) {
          if (id !== 'orchestrator' && ESCALATABLE.has(n.status)) next[id] = { ...n, status: 'escalated' };
        }
        return next;
      });
      setExReason('');
    } catch (e) {
      push({ role: 'system', text: `Escalation failed: ${e.message}` });
    } finally {
      setEscalating(false);
    }
  };
  // Standard audit inputs, bound to state — shared by the full form AND the "answer a
  // request" view so earlier inputs can be edited together with whatever the mesh asked for.
  const standardInputs = () => (
    <>
      <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr 1fr', gap: '0.5rem' }}>
        <Field label="🖼 Mockup image — upload goes to gs://vibeflix-request-image">
          <div style={{ display: 'flex', gap: '0.4rem', alignItems: 'stretch' }}>
            <input className="top-textarea" style={{ flex: 1, minWidth: 0 }} placeholder="Enter your Cloud Storage URI gs://vibeflix-request-image/YOUR_IMAGE" value={imageUri} onChange={(e) => setImageUri(e.target.value)} />
            <label className="preset-btn" style={{ cursor: uploading ? 'wait' : 'pointer', fontSize: '0.75rem', whiteSpace: 'nowrap', display: 'flex', alignItems: 'center' }}>
              <Upload size={12} style={{ marginRight: '4px', verticalAlign: 'middle' }} />
              {uploading ? 'Uploading…' : 'Upload image'}
              <input type="file" accept="image/*" style={{ display: 'none' }} disabled={uploading}
                onChange={(e) => { uploadImage(e.target.files?.[0]); e.target.value = ''; }} />
            </label>
          </div>
        </Field>
        <Field label="🌍 Operating region">
          <select className="top-textarea" value={market} onChange={(e) => setMarket(e.target.value)}>
            {MARKETS.map((m) => <option key={m} value={m}>{m}</option>)}
          </select>
        </Field>
        <Field label="📦 Volume (units)">
          <input className="top-textarea" type="number" placeholder="e.g. 1000" value={volume} onChange={(e) => setVolume(e.target.value)} />
        </Field>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.5rem' }}>
        <Field label="🧸 Character / trademark">
          <select className="top-textarea" value={character} onChange={(e) => setCharacter(e.target.value)}>
            <option value="">(blank → agent asks)</option>
            {characters.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}
          </select>
        </Field>
        <Field label="🏭 Manufacturing vendor">
          <input className="top-textarea" placeholder="id (VND-1001) or name — blank → agent asks" value={vendor} onChange={(e) => setVendor(e.target.value)} />
        </Field>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.5rem' }}>
        <Field label="🗂 Product category">
          <Combo value={productCategory} onChange={setProductCategory} options={CATEGORY_OPTIONS}
            placeholder="Pick or type — blank → agent asks" />
        </Field>
        <Field label="🎨 Product medium">
          <Combo value={medium} onChange={setMedium} options={MEDIA_OPTIONS}
            placeholder="Blank → auto-detected from the image; pick/type to override" />
        </Field>
      </div>
      <Field label="💰 Deal pricing — agreed total consideration (audited vs the rate card)">
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr 1fr', gap: '0.4rem' }}>
          <input className="top-textarea" type="number" step="0.01" placeholder="Net $/unit" value={netUnitPrice} onChange={(e) => setNetUnitPrice(e.target.value)} title="Wholesale price per unit ($) — the royalty basis" />
          <input className="top-textarea" type="number" step="0.1" placeholder="Royalty %" value={agreedRate} onChange={(e) => setAgreedRate(e.target.value)} title="Agreed royalty rate (%)" />
          <input className="top-textarea" type="number" placeholder="Advance $" value={agreedAdvance} onChange={(e) => setAgreedAdvance(e.target.value)} title="Agreed advance ($)" />
          <input className="top-textarea" type="number" placeholder="Min guar. $" value={agreedMg} onChange={(e) => setAgreedMg(e.target.value)} title="Agreed minimum guarantee ($)" />
        </div>
      </Field>
      <Field label="💬 Question or extra context">
        <textarea className="top-textarea" rows={1} placeholder="Optional — e.g. treat the T-Shirt medium as pre-approved · or: why was the vendor blocked?"
          value={note} onChange={(e) => setNote(e.target.value)} style={{ fontSize: '0.8rem', resize: 'vertical' }} />
      </Field>
    </>
  );
  const reset = () => {
    runTokenRef.current = null;
    setMessages([{ role: 'system', text: 'New session. Start an audit below.' }]);
    setFields(null); setSessionId(null); setPhase('start'); setGraph(null); setContractId('');
    // Blank graph ⇒ no run to scope to: reject every mesh event until the next run
    // starts, so a finished audit's trailing events can't repopulate an empty graph.
    runIdRef.current = null; runActiveRef.current = false;
    setNote(''); setNetUnitPrice(''); setAgreedRate(''); setAgreedAdvance(''); setAgreedMg('');
  };
  const uploadImage = async (fileObj) => {
    if (!fileObj) return;
    setUploading(true);
    try {
      const fd = new FormData();
      fd.append('file', fileObj);
      const res = await fetch(`${API_BASE}/api/upload`, { method: 'POST', body: fd });
      if (!res.ok) throw new Error(`${res.status}: ${(await res.text()).slice(0, 140)}`);
      const d = await res.json();
      setImageUri(d.image_uri);
      push({ role: 'system', text: `📎 Uploaded "${fileObj.name}" → ${d.image_uri}` });
    } catch (e) {
      push({ role: 'system', text: `Upload failed: ${e.message}` });
    } finally { setUploading(false); }
  };

  const StatusIcon = (phase === 'done' || phase === 'complete') ? CheckCircle : phase === 'awaiting' ? HelpCircle : phase === 'running' ? Satellite : AlertTriangle;

  return (
    <A2UIProvider>
    <div style={{ display: 'flex', height: '100%', width: '100%', minHeight: 0, gap: '0.6rem' }}>
    <div style={{ display: 'flex', flexDirection: 'column', flex: 1, minWidth: 0, minHeight: 0, gap: '0.6rem' }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <h3 className="panel-title" style={{ margin: 0, fontSize: '0.95rem', display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
          <StatusIcon size={16} style={{ color: 'var(--accent-purple)' }} /> Live Compliance Audit
        </h3>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <span style={{ fontSize: '0.7rem', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '0.3rem',
            color: ready ? 'var(--color-success)' : ready === false ? 'var(--color-danger)' : 'var(--text-muted)' }}>
            ● {ready === null ? 'checking mesh…' : ready ? 'mesh ready' : `mesh not ready · ${readyCount}/${components.length || 3}`}
          </span>
          <button className="preset-btn" onClick={reset} disabled={busy} title="Start a new audit conversation">
            <RotateCcw size={12} style={{ marginRight: '3px', verticalAlign: 'middle' }} /> New
          </button>
        </div>
      </div>

      {/* Chat transcript — the active input is drawn INLINE, as the last turn */}
      <div ref={scrollRef} className="canvas-panel" style={{ flex: 1, minHeight: 0, overflowY: 'auto', padding: '0.9rem', display: 'flex', flexDirection: 'column', alignItems: 'stretch', justifyContent: 'flex-start', gap: '0.6rem' }}>
        {/* Exposes processMessages to the SSE loop; renders nothing itself. */}
        <A2UIBridge pmRef={pmRef} />

        {/* Each run's streamed A2UI surface is its own transcript entry. */}
        {messages.map((m, i) => m.role === 'surface'
          ? <SurfaceCard key={i} surfaceId={m.surfaceId} />
          : <Bubble key={i} msg={m} />)}

        {phase === 'running' ? (
          <div style={{ alignSelf: 'flex-start', fontSize: '0.72rem', color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
            <Satellite size={12} className="spin" /> orchestrator running the agent mesh…
          </div>
        ) : (
          <div style={{ alignSelf: 'flex-end', width: '94%', background: 'var(--bg-tertiary)', border: '1px dashed var(--accent-blue)', borderRadius: '0.6rem 0.6rem 0.15rem 0.6rem', padding: '0.6rem 0.7rem' }}>
            <div style={{ fontSize: '0.6rem', color: 'var(--text-muted)', marginBottom: '0.4rem', textAlign: 'right', textTransform: 'uppercase', letterSpacing: '0.06em' }}>your input</div>
            {ready !== true ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.6rem' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', fontSize: '0.8rem', fontWeight: 700, color: ready === false ? 'var(--color-danger)' : 'var(--text-muted)' }}>
                  <Lock size={14} /> {ready === null ? 'Checking mesh health…' : 'Console locked — waiting for the mesh to come up'}
                </div>
                <MeshStatus components={components} />
              </div>
            ) : phase === 'complete' ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', fontSize: '0.9rem', fontWeight: 700, color: 'var(--color-success, #3ddc84)' }}>
                  <CheckCircle size={16} /> Audit session complete — all workflows passed{contractId ? ` · contract ${contractId} executed` : ''}.
                </div>
                <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
                  This session is finalized, so re-submitting is disabled. The full report is archived in the <strong>Audit History</strong> tab (with PDF export).
                </div>
                <button className="preset-btn primary" onClick={reset} style={{ alignSelf: 'flex-start' }}>
                  <Satellite size={13} style={{ marginRight: '4px', verticalAlign: 'middle' }} /> New audit session
                </button>
              </div>
            ) : phase === 'awaiting' && fields ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                {/* The fields the mesh ASKED for come FIRST (highlighted); the earlier
                    inputs follow so they can be edited too — one submit sends it all. */}
                {fields.filter((f) => !STD_TOKENS.has(f.name)).length > 0 ? (
                  <>
                    <FieldDock fields={fields.filter((f) => !STD_TOKENS.has(f.name))} onSubmit={submitFields} busy={busy}
                      defaults={{ image_uri: imageUri, medium, character, product_category: productCategory, vendor, target_market: market }}
                      formId="mesh-asked-fields" hideSubmit />
                    <div style={{ borderTop: '1px dashed var(--glass-border)', paddingTop: '0.5rem', fontSize: '0.72rem', color: 'var(--text-muted)' }}>
                      You can also edit any earlier input — everything is submitted together:
                    </div>
                    {standardInputs()}
                    <button type="submit" form="mesh-asked-fields" className="preset-btn primary" disabled={busy} style={{ alignSelf: 'flex-start' }}>
                      <Send size={13} style={{ marginRight: '4px', verticalAlign: 'middle' }} /> {busy ? 'Sending…' : 'Submit answer'}
                    </button>
                  </>
                ) : (
                  <>
                    <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>
                      Adjust the inputs the mesh flagged and re-submit:
                    </div>
                    {standardInputs()}
                    <button className="preset-btn primary" onClick={() => submitFields({})} disabled={busy} style={{ alignSelf: 'flex-start' }}>
                      <Send size={13} style={{ marginRight: '4px', verticalAlign: 'middle' }} /> {busy ? 'Sending…' : 'Submit'}
                    </button>
                  </>
                )}
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                <div style={{ fontSize: '0.9rem', fontWeight: 700, color: 'var(--text-main)' }}>
                  {phase === 'done' ? 'Adjust inputs & re-run:' : 'Start an audit — fill in and submit:'}
                </div>
                {standardInputs()}
                <button className="preset-btn primary" onClick={startAudit} disabled={busy || !imageUri.trim()} style={{ alignSelf: 'flex-start' }}>
                  <Satellite size={13} style={{ marginRight: '4px', verticalAlign: 'middle' }} />
                  {busy ? 'Running…' : (phase === 'done' ? 'Re-run audit' : 'Submit — run audit')}
                </button>
                {phase === 'done' && graph && Object.entries(graph).some(([id, n]) => id !== 'orchestrator' && ESCALATABLE.has(n.status)) && (
                  <div style={{ marginTop: '0.4rem', paddingTop: '0.5rem', borderTop: '1px dashed var(--glass-border)', display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
                    <div style={{ fontSize: '0.66rem', color: 'var(--text-muted)' }}>
                      Can't clear a flagged finding by editing inputs? Raise an exception for manual review:
                    </div>
                    <input className="top-textarea" placeholder="Reason (optional) — e.g. T-Shirt medium approved by Legal; misspellings intentional"
                      value={exReason} onChange={(e) => setExReason(e.target.value)} style={{ fontSize: '0.72rem' }} />
                    <button className="preset-btn" onClick={raiseException} disabled={busy || escalating}
                      style={{ alignSelf: 'flex-start', fontSize: '0.7rem', borderColor: '#a98bff', color: '#a98bff' }}>
                      {escalating ? 'Escalating…' : '⏫ Raise exception request'}
                    </button>
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
    {/* Right pane: the live workflow graph — adds nodes as the plan arrives, lights
        each up as its agent runs, and shows the final status. */}
    {/* flex 0.6 vs the chat's 1 → the graph takes 37.5% of the row: exactly 75% of
        the 50% share it had before. */}
    <aside className="canvas-panel" style={{ flex: 0.6, minWidth: 0, display: 'flex', flexDirection: 'column', minHeight: 0, padding: '0.7rem' }}>
      <h3 className="panel-title" style={{ margin: '0 0 0.4rem', fontSize: '0.82rem', display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
        <Share2 size={14} style={{ color: 'var(--accent-purple)' }} /> Workflow graph
      </h3>
      <div style={{ flex: 1, minHeight: 0, overflow: 'auto', display: 'flex', alignItems: 'flex-start', justifyContent: 'center' }}>
        <WorkflowGraph graph={graph} components={components} mcpTools={mcpTools} toolLights={toolLights} />
      </div>
    </aside>
    </div>
    </A2UIProvider>
  );
}
