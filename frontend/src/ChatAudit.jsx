import React, { useState, useRef, useEffect } from 'react';
import { Send, Satellite, RotateCcw, CheckCircle, AlertTriangle, HelpCircle, Lock, Upload, Share2 } from 'lucide-react';
import { A2UIProvider, A2UIRenderer, useA2UI } from '@a2ui/react';
import { injectStyles } from '@a2ui/react/styles';

// Inject the A2UI renderer's structural + component styles once (CSS-in-JS).
injectStyles();

// Talks to the real ADK orchestrator (app.py). Same origin in prod; override for dev.
const API_BASE = import.meta.env.VITE_API_URL || '';
const MARKETS = ['North America', 'Europe', 'Asia-Pacific', 'Global'];

// The backend STREAMS incremental A2UI surfaceUpdate messages (plan → per-agent
// fills → sourcing) and @a2ui/react patches the surface in place, so panels fill in
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
function FieldDock({ fields, onSubmit, busy, defaults = {} }) {
  const [values, setValues] = useState(() =>
    Object.fromEntries(fields.map((f) => [
      f.name,
      defaults[f.name] || f.value || (f.type === 'select' ? (f.options?.[0]?.value ?? '') : ''),
    ]))
  );
  const set = (name, v) => setValues((prev) => ({ ...prev, [name]: v }));
  const ready = fields.every((f) => !f.required || String(values[f.name] ?? '').trim() !== '');
  return (
    <form onSubmit={(e) => { e.preventDefault(); if (ready && !busy) onSubmit(values); }}
      style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', width: '100%' }}>
      {fields.map((f) => (
        <div key={f.name} style={{ display: 'flex', flexDirection: 'column', gap: '0.2rem' }}>
          <label style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>{f.label}{f.required ? ' *' : ''}</label>
          {f.type === 'select' ? (
            <select className="top-textarea" value={values[f.name]} onChange={(e) => set(f.name, e.target.value)}>
              {(f.options || []).map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
          ) : (
            <input className="top-textarea" type={f.type === 'number' ? 'number' : 'text'}
              placeholder={f.placeholder || ''} value={values[f.name]} onChange={(e) => set(f.name, e.target.value)} />
          )}
        </div>
      ))}
      <button type="submit" className="preset-btn primary" disabled={!ready || busy} style={{ alignSelf: 'flex-start' }}>
        <Send size={13} style={{ marginRight: '4px', verticalAlign: 'middle' }} />
        {busy ? 'Sending…' : 'Submit answer'}
      </button>
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
  done:        { fill: '#123726', border: '#3ddc84', dot: '#3ddc84', label: 'done' },
  blocked:     { fill: '#3a1717', border: '#ff5c5c', dot: '#ff5c5c', label: 'blocked' },
  failed:      { fill: '#2e1420', border: '#ff6b9d', dot: '#ff6b9d', label: 'failed' },
  needs_input: { fill: '#3a2f12', border: '#ffc24a', dot: '#ffc24a', label: 'needs input' },
  awaiting:    { fill: '#3a2f12', border: '#ffc24a', dot: '#ffc24a', label: 'awaiting input' },
  reused:      { fill: '#1c1c1c', border: '#3a3a3a', dot: '#666', label: 'reused' },
  pending:     { fill: '#1c1c1c', border: '#3a3a3a', dot: '#777', label: 'queued' },
};

function WorkflowGraph({ graph }) {
  const nodes = graph ? Object.values(graph) : [];
  if (!nodes.length) {
    return <div style={{ padding: '1.2rem 0.6rem', fontSize: '0.72rem', color: 'var(--text-muted)', textAlign: 'center', lineHeight: 1.5 }}>
      Run an audit — the workflow graph builds here, lighting up each agent as it runs.
    </div>;
  }
  const W = 380, NW = 116, NH = 46;
  const root = nodes.find((n) => !n.parent);
  const l1 = nodes.filter((n) => root && n.parent === root.id);
  const l2 = nodes.filter((n) => n.parent && (!root || n.parent !== root.id));
  const pos = {};
  if (root) pos[root.id] = { x: (W - NW) / 2, y: 14 };
  const gap = 14;
  const total = l1.length * NW + Math.max(0, l1.length - 1) * gap;
  const x0 = Math.max(6, (W - total) / 2);
  l1.forEach((n, i) => { pos[n.id] = { x: x0 + i * (NW + gap), y: 120 }; });
  l2.forEach((n) => { const p = pos[n.parent] || { x: (W - NW) / 2 }; pos[n.id] = { x: p.x, y: 226 }; });
  const H = l2.length ? 292 : 190;

  const edge = (a, b, dashed) => {
    const pa = pos[a], pb = pos[b]; if (!pa || !pb) return null;
    const x1 = pa.x + NW / 2, y1 = pa.y + NH, x2 = pb.x + NW / 2, y2 = pb.y, my = (y1 + y2) / 2;
    return <path key={`${a}-${b}`} d={`M ${x1} ${y1} C ${x1} ${my}, ${x2} ${my}, ${x2} ${y2}`}
      fill="none" stroke="var(--glass-border, #444)" strokeWidth="1.4" strokeDasharray={dashed ? '3 3' : undefined} />;
  };

  const NodeBox = ({ n }) => {
    const p = pos[n.id]; if (!p) return null;
    const s = WF_STATUS[n.status] || WF_STATUS.pending;
    return (
      <g className={n.status === 'running' ? 'wf-running' : ''}>
        <rect x={p.x} y={p.y} width={NW} height={NH} rx="9" fill={s.fill} stroke={s.border}
          strokeWidth={n.status === 'running' ? 2 : 1.3} strokeDasharray={n.status === 'reused' ? '4 3' : undefined} />
        <circle cx={p.x + 13} cy={p.y + 15} r="4" fill={s.dot} />
        <text x={p.x + NW / 2} y={p.y + 19} textAnchor="middle" fontSize="11" fontWeight="700" fill="var(--text-primary, #e8e8e8)">{n.label}</text>
        <text x={p.x + NW / 2} y={p.y + 34} textAnchor="middle" fontSize="9" fill={s.dot}>{s.label}</text>
      </g>
    );
  };

  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" style={{ maxHeight: '100%' }}>
      {root && l1.map((n) => edge(root.id, n.id, false))}
      {l2.map((n) => edge(n.parent, n.id, true))}
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

  const [imageUri, setImageUri] = useState('gs://vibeflix-approved-assets/vendor_request.jpg');
  const [market, setMarket] = useState('North America');
  const [volume, setVolume] = useState(15000);
  const [medium, setMedium] = useState('');
  const [character, setCharacter] = useState('');
  const [productCategory, setProductCategory] = useState('');
  const [vendor, setVendor] = useState('');
  const [uploading, setUploading] = useState(false);

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
  useEffect(() => { const el = scrollRef.current; if (el) el.scrollTop = el.scrollHeight; }, [messages, phase]);

  const push = (m) => setMessages((prev) => [...prev, m]);

  // Stream an audit: POST /api/audit/stream and feed each SSE A2UI message to the
  // live renderer via pmRef. Each run paints its OWN surface (`audit-<n>`) as a new
  // transcript entry, so a re-run appends below instead of overwriting the last.
  const runStream = async (request, fallbackPhase) => {
    setBusy(true); setPhase('running'); setFields(null);
    setGraph({ orchestrator: { id: 'orchestrator', label: 'Orchestrator', status: 'running' } });
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
          if (d.a2ui) {
            pmRef.current?.([retarget(d.a2ui, surfaceId)]);
          } else if (d.event === 'graph') {
            if (d.op === 'plan') {
              setGraph((g) => {
                const next = { orchestrator: (g?.orchestrator) || { id: 'orchestrator', label: 'Orchestrator', status: 'running' } };
                for (const n of d.nodes) next[n.id] = { id: n.id, label: n.label, parent: 'orchestrator', status: n.run ? 'running' : 'reused' };
                return next;
              });
            } else if (d.op === 'status') {
              setGraph((g) => ({
                ...(g || {}),
                [d.id]: { ...(g?.[d.id] || { id: d.id, label: d.label || d.id, parent: d.parent }), status: d.status, ...(d.parent ? { parent: d.parent } : {}), ...(d.label ? { label: d.label } : {}) },
              }));
            }
          } else if (d.event === 'done') {
            if (d.run_token) runTokenRef.current = d.run_token;
            setGraph((g) => g ? { ...g, orchestrator: { ...g.orchestrator, status: 'done' } } : g);
            setPhase('done'); ended = true;
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
    } finally { setBusy(false); }
  };

  // run_token threads the prior audit so the orchestrator re-runs only affected
  // workflows. Carried on every submit in a session; cleared by "New".
  const startAudit = () => {
    push({ role: 'user', text: `Audit ${imageUri}\n${character ? `${character} · ` : ''}${market} · ${Number(volume).toLocaleString()} units${medium ? ` · medium: ${medium}` : ''}` });
    runStream({ image_uri: imageUri, target_market: market, volume: Number(volume), character, product_category: productCategory, vendor, medium, run_token: runTokenRef.current }, 'start');
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
    push({ role: 'user', text: Object.entries(values).map(([k, v]) => `${k} = ${v}`).join('\n') });
    runStream({
      image_uri: values.image_uri || imageUri,
      target_market: values.target_market || market,
      volume: Number(volume),
      character: values.character || character,
      product_category: values.product_category || productCategory,
      vendor: values.vendor || vendor,
      new_vendor: values.new_vendor || '',
      add_category_approved: values.add_category_approved || '',
      medium: values.medium ?? medium,
      run_token: runTokenRef.current,
    }, 'awaiting');
  };
  const reset = () => {
    runTokenRef.current = null;
    setMessages([{ role: 'system', text: 'New session. Start an audit below.' }]);
    setFields(null); setSessionId(null); setPhase('start');
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

  const StatusIcon = phase === 'done' ? CheckCircle : phase === 'awaiting' ? HelpCircle : phase === 'running' ? Satellite : AlertTriangle;

  return (
    <A2UIProvider>
    <div style={{ display: 'flex', height: '100%', width: '100%', minHeight: 0, gap: '0.6rem' }}>
    <div style={{ display: 'flex', flexDirection: 'column', flex: 1, minWidth: 0, minHeight: 0, gap: '0.6rem' }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <h3 className="panel-title" style={{ margin: 0, fontSize: '0.95rem', display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
          <StatusIcon size={16} style={{ color: 'var(--accent-purple)' }} /> Live Compliance Audit
          <span style={{ fontSize: '0.68rem', color: 'var(--text-muted)', fontWeight: 400 }}>· real ADK orchestrator ({API_BASE || 'same origin'})</span>
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
            ) : phase === 'awaiting' && fields ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                {/* Everything provided so far — so context isn't lost when only one more field is asked. */}
                <div style={{ fontSize: '0.66rem', color: 'var(--text-muted)', display: 'flex', flexWrap: 'wrap', gap: '0.2rem 0.8rem' }}>
                  {[['character', character], ['vendor', vendor], ['category', productCategory], ['market', market], ['volume', volume && Number(volume).toLocaleString()], ['medium', medium], ['image', imageUri]]
                    .filter(([, v]) => v).map(([k, v]) => <span key={k}><b>{k}:</b> {String(v).length > 40 ? String(v).slice(0, 40) + '…' : v}</span>)}
                </div>
                <FieldDock fields={fields} onSubmit={submitFields} busy={busy}
                  defaults={{ image_uri: imageUri, medium, character, product_category: productCategory, vendor, target_market: market }} />
                <button className="preset-btn" onClick={() => { setFields(null); setPhase('done'); }} disabled={busy}
                  style={{ alignSelf: 'flex-start', fontSize: '0.68rem' }} title="Edit all inputs instead of just the requested field">
                  ↔ edit all inputs instead
                </button>
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>
                  {phase === 'done' ? 'Adjust inputs & re-run:' : 'Start an audit — fill in and submit:'}
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr 1fr', gap: '0.5rem' }}>
                  <input className="top-textarea" placeholder="Vendor image link (gs://… or https://…)" value={imageUri} onChange={(e) => setImageUri(e.target.value)} />
                  <select className="top-textarea" value={market} onChange={(e) => setMarket(e.target.value)}>
                    {MARKETS.map((m) => <option key={m} value={m}>{m}</option>)}
                  </select>
                  <input className="top-textarea" type="number" placeholder="Volume" value={volume} onChange={(e) => setVolume(e.target.value)} />
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.5rem' }}>
                  <select className="top-textarea" value={character} onChange={(e) => setCharacter(e.target.value)}>
                    <option value="">Character / trademark — (blank → agent asks)</option>
                    {characters.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}
                  </select>
                  <input className="top-textarea" placeholder="Vendor — id (VND-1001) or name (blank → agent asks)" value={vendor} onChange={(e) => setVendor(e.target.value)} />
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap' }}>
                  <label className="preset-btn" style={{ cursor: uploading ? 'wait' : 'pointer', fontSize: '0.7rem' }}>
                    <Upload size={12} style={{ marginRight: '4px', verticalAlign: 'middle' }} />
                    {uploading ? 'Uploading…' : 'Upload image'}
                    <input type="file" accept="image/*" style={{ display: 'none' }} disabled={uploading}
                      onChange={(e) => { uploadImage(e.target.files?.[0]); e.target.value = ''; }} />
                  </label>
                  <span style={{ fontSize: '0.66rem', color: 'var(--text-muted)' }}>→ uploads to gs://vibeflix-request-image</span>
                </div>
                <input className="top-textarea" placeholder="Product medium (leave blank and brand_style will ask; e.g. vinyl figure box, poster, T-shirt)"
                  value={medium} onChange={(e) => setMedium(e.target.value)} />
                <button className="preset-btn primary" onClick={startAudit} disabled={busy || !imageUri.trim()} style={{ alignSelf: 'flex-start' }}>
                  <Satellite size={13} style={{ marginRight: '4px', verticalAlign: 'middle' }} />
                  {busy ? 'Running…' : (phase === 'done' ? 'Re-run audit' : 'Submit — run audit')}
                </button>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
    {/* Right pane: the live workflow graph — adds nodes as the plan arrives, lights
        each up as its agent runs, and shows the final status. */}
    <aside className="canvas-panel" style={{ width: '380px', flexShrink: 0, display: 'flex', flexDirection: 'column', minHeight: 0, padding: '0.7rem' }}>
      <h3 className="panel-title" style={{ margin: '0 0 0.4rem', fontSize: '0.82rem', display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
        <Share2 size={14} style={{ color: 'var(--accent-purple)' }} /> Workflow graph
      </h3>
      <div style={{ flex: 1, minHeight: 0, overflow: 'auto', display: 'flex', alignItems: 'flex-start', justifyContent: 'center' }}>
        <WorkflowGraph graph={graph} />
      </div>
    </aside>
    </div>
    </A2UIProvider>
  );
}
