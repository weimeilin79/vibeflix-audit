import React, { useState } from 'react';
import { RefreshCw, HardDrive, ChevronDown, ChevronRight } from 'lucide-react';

const API_BASE = import.meta.env.VITE_API_URL || '';

// One-line summary for a record: its first few scalar fields.
function summarize(v) {
  if (v == null || typeof v !== 'object') return String(v ?? '');
  return Object.entries(v)
    .filter(([, x]) => ['string', 'number', 'boolean'].includes(typeof x) && String(x).length < 60)
    .slice(0, 3)
    .map(([k, x]) => `${k}: ${x}`)
    .join(' · ');
}

function Doc({ id, value }) {
  const [open, setOpen] = useState(false);
  return (
    <div style={{ borderTop: '1px solid var(--glass-border)' }}>
      <div onClick={() => setOpen((o) => !o)}
        style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', padding: '0.35rem 0.2rem', cursor: 'pointer', fontSize: '0.74rem' }}>
        {open ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
        <span style={{ fontFamily: 'monospace', fontWeight: 700 }}>{id}</span>
        <span style={{ color: 'var(--text-muted)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{summarize(value)}</span>
      </div>
      {open && (
        <pre style={{ margin: '0 0 0.5rem 1.4rem', padding: '0.5rem', fontSize: '0.68rem', lineHeight: 1.45,
          background: 'var(--bg-tertiary)', border: '1px solid var(--glass-border)', borderRadius: '0.35rem',
          overflowX: 'auto', maxHeight: '340px' }}>{JSON.stringify(value, null, 2)}</pre>
      )}
    </div>
  );
}

function Collection({ title, docs, hint }) {
  const entries = Object.entries(docs || {});
  const [open, setOpen] = useState(false);
  return (
    <div className="glass-card" style={{ padding: '0.7rem 0.9rem', borderRadius: '0.55rem',
      border: '1px solid var(--glass-border)', background: 'var(--bg-secondary)' }}>
      <div onClick={() => setOpen((o) => !o)} style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', cursor: 'pointer' }}>
        {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        <span style={{ fontSize: '0.8rem', fontWeight: 700 }}>{title}</span>
        <span style={{ fontSize: '0.68rem', color: 'var(--text-muted)' }}>
          {entries.length} record{entries.length === 1 ? '' : 's'}{hint ? ` · ${hint}` : ''}
        </span>
      </div>
      {open && (
        <div style={{ marginTop: '0.4rem' }}>
          {entries.length === 0 && <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', padding: '0.3rem 0' }}>empty</div>}
          {entries.map(([id, v]) => <Doc key={id} id={id} value={v} />)}
        </div>
      )}
    </div>
  );
}

export default function DatabaseView() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState(null);

  // Loaded ONLY on demand — the dump walks every store + Firestore collection,
  // so nothing fetches on mount or tab switches; the Refresh button drives it.
  const load = async () => {
    setLoading(true); setErr(null);
    try {
      const r = await fetch(`${API_BASE}/api/database`);
      setData(await r.json());
    } catch (e) { setErr(String(e)); }
    finally { setLoading(false); }
  };

  const stores = data?.stores || {};
  const registries = data?.registries || {};
  const audits = Object.fromEntries((data?.audit_history || []).map((a) => [a.order_id || a.id, a]));

  return (
    <div style={{ maxWidth: '980px', margin: '0 auto', width: '100%', display: 'flex', flexDirection: 'column', gap: '0.6rem', padding: '1rem' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
        <HardDrive size={16} style={{ color: 'var(--accent-purple)' }} />
        <h2 style={{ margin: 0, fontSize: '0.95rem' }}>Database</h2>
        <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>
          — every store the mesh runs on{data ? ` · Firestore: ${data.firestore_database}` : ''}
        </span>
        <button className="preset-btn" style={{ marginLeft: 'auto', fontSize: '0.7rem' }} onClick={load} disabled={loading}>
          <RefreshCw size={12} style={{ marginRight: '4px', verticalAlign: 'middle' }} className={loading ? 'spin' : ''} />
          {loading ? 'Loading…' : 'Refresh'}
        </button>
      </div>
      {err && <div style={{ fontSize: '0.72rem', color: '#ff5c5c' }}>Failed to load: {err}</div>}
      {!data && !loading && (
        <div style={{ fontSize: '0.74rem', color: 'var(--text-muted)', padding: '1.5rem', textAlign: 'center' }}>
          Click <strong>Refresh</strong> to load a snapshot of every store — nothing loads automatically.
        </div>
      )}
      {data && (
        <>
          <div style={{ fontSize: '0.7rem', fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em', marginTop: '0.3rem' }}>Licensing stores (mcp_licensing)</div>
          <Collection title="🏭 Vendors" docs={stores.vendors} hint="Firestore-backed CRUD" />
          <Collection title="™️ Trademarks" docs={stores.trademarks} hint="in-memory" />
          <Collection title="🔒 Exclusivity contracts" docs={stores.exclusivity} hint="in-memory" />
          <Collection title="📜 Licensing contracts" docs={stores.contracts} hint="in-memory · executed by legal" />
          <Collection title="💰 Rate cards" docs={stores.rate_cards} hint="in-memory · read-only" />
          <div style={{ fontSize: '0.7rem', fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em', marginTop: '0.3rem' }}>Semantic registries (Firestore · live-editable rules)</div>
          <Collection title="🎨 brand_style_registry" docs={registries.brand_style_registry} />
          <Collection title="⚖️ legal_registry" docs={registries.legal_registry} />
          <Collection title="📦 market_policy" docs={registries.market_policy} hint="incl. the sourcing cap the gate reads" />
          <div style={{ fontSize: '0.7rem', fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em', marginTop: '0.3rem' }}>Audit history (Firestore)</div>
          <Collection title="🗂 audit_history" docs={audits} hint="one record per audit order" />
        </>
      )}
    </div>
  );
}
