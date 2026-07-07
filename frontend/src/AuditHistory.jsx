import React, { useState, useEffect, useCallback } from 'react';
import { RefreshCw, FileText, ChevronDown, ChevronRight, ScrollText } from 'lucide-react';

const API_BASE = import.meta.env.VITE_API_URL || '';

// status → chip colors (mirrors the workflow graph's vocabulary)
const CHIP = {
  cleared:     { bg: '#123726', fg: '#3ddc84' },
  compliant:   { bg: '#123726', fg: '#3ddc84' },
  blocked:     { bg: '#3a1717', fg: '#ff5c5c' },
  failed:      { bg: '#2e1420', fg: '#ff6b9d' },
  flagged:     { bg: '#3a2f12', fg: '#ffc24a' },
  rejected:    { bg: '#3a2f12', fg: '#ffc24a' },
  needs_input: { bg: '#3a2f12', fg: '#ffc24a' },
};

function Chip({ label, status }) {
  const c = CHIP[status] || { bg: 'var(--bg-tertiary)', fg: 'var(--text-muted)' };
  return (
    <span style={{ background: c.bg, color: c.fg, borderRadius: '0.3rem', padding: '0.1rem 0.45rem',
      fontSize: '0.66rem', fontWeight: 600, whiteSpace: 'nowrap' }}>
      {label} · {(status || '?').replace('_', ' ')}
    </span>
  );
}

// "brand_style_compliance_agent" → "Brand Style"
const nice = (name) => (name || '')
  .replace(/_/g, ' ').replace(/\b(compliance|agent|report)\b/g, '').trim()
  .replace(/\b\w/g, (ch) => ch.toUpperCase());

function ContractBlock({ contract }) {
  if (!contract) return null;
  const rows = [
    ['Contract', contract.contract_id], ['Status', contract.status],
    ['Vendor', contract.vendor_id], ['Character', contract.character_id],
    ['Category', contract.category], ['Territory', contract.territory],
    ['Royalty', contract.royalty_pct != null ? `${contract.royalty_pct}%` : null],
    ['Safety cert', contract.safety_cert_id], ['HS code', contract.hs_code],
    ['Amendment', contract.amendment_id],
  ].filter(([, v]) => v != null && v !== '');
  return (
    <div style={{ marginTop: '0.5rem', padding: '0.6rem 0.75rem', borderRadius: '0.4rem',
      border: '1px solid var(--glass-border)', background: 'var(--bg-tertiary)' }}>
      <div style={{ fontSize: '0.72rem', fontWeight: 700, marginBottom: '0.35rem', display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
        <ScrollText size={13} style={{ color: 'var(--accent-purple)' }} /> Executed licensing contract
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(150px, 1fr))', gap: '0.25rem 0.9rem' }}>
        {rows.map(([k, v]) => (
          <div key={k} style={{ fontSize: '0.7rem' }}>
            <span style={{ color: 'var(--text-muted)' }}>{k}: </span>
            <span style={{ fontWeight: 600 }}>{String(v)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function ReportDetail({ name, report }) {
  const items = [...(report?.findings || []), ...(report?.issues || [])].filter((x) => x && typeof x === 'object');
  return (
    <div style={{ marginTop: '0.4rem' }}>
      <div style={{ fontSize: '0.72rem', fontWeight: 700 }}>{nice(name)} — {(report?.status || '?').toUpperCase()}</div>
      {report?.legal_cleared && <div style={{ fontSize: '0.7rem', marginTop: '0.15rem' }}>{report.legal_cleared}</div>}
      {items.length === 0 && !report?.legal_cleared && (
        <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>No findings.</div>
      )}
      {items.map((it, i) => (
        <div key={i} style={{ fontSize: '0.7rem', marginTop: '0.15rem' }}>
          {it.severity === 'critical' ? '⛔' : '⚠️'} {it.description || it.issue_type || 'Issue'}
        </div>
      ))}
    </div>
  );
}

function AuditEntry({ entry }) {
  const [open, setOpen] = useState(false);
  const inp = entry.inputs || {};
  const when = entry.ts ? new Date(entry.ts).toLocaleString() : '';
  const subject = [inp.character, inp.product_category, inp.medium, inp.vendor, inp.target_market,
    inp.volume ? `${Number(inp.volume).toLocaleString()} units` : null].filter(Boolean).join(' · ');
  return (
    <div className="glass-card" style={{ padding: '0.8rem 1rem', borderRadius: '0.55rem',
      border: '1px solid var(--glass-border)', background: 'var(--bg-secondary)' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', cursor: 'pointer', flexWrap: 'wrap' }}
        onClick={() => setOpen((o) => !o)}>
        {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        <span style={{ fontSize: '0.78rem', fontWeight: 700 }}>{entry.passed ? '✅ Passed' : '⚠️ Completed with findings'}</span>
        {entry.contract?.contract_id && (
          <span style={{ fontSize: '0.7rem', color: 'var(--accent-purple)', fontWeight: 700 }}>
            📜 {entry.contract.contract_id}
          </span>
        )}
        <span style={{ fontSize: '0.68rem', color: 'var(--text-muted)', marginLeft: 'auto' }}>{when}</span>
      </div>
      <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', margin: '0.3rem 0 0.45rem 1.35rem' }}>{subject || '—'}</div>
      <div style={{ display: 'flex', gap: '0.4rem', flexWrap: 'wrap', marginLeft: '1.35rem' }}>
        {Object.entries(entry.statuses || {}).map(([n, s]) => <Chip key={n} label={nice(n)} status={s} />)}
      </div>
      {open && (
        <div style={{ marginLeft: '1.35rem', marginTop: '0.5rem', borderTop: '1px solid var(--glass-border)', paddingTop: '0.45rem' }}>
          {inp.image_uri && <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)', wordBreak: 'break-all' }}>🖼 {inp.image_uri}</div>}
          {inp.note && <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)' }}>💬 {inp.note}</div>}
          {Object.entries(entry.reports || {}).map(([n, r]) => <ReportDetail key={n} name={n} report={r} />)}
          <ContractBlock contract={entry.contract} />
        </div>
      )}
    </div>
  );
}

export default function AuditHistory() {
  const [audits, setAudits] = useState(null);
  const [err, setErr] = useState(null);
  const load = useCallback(async () => {
    try {
      const r = await fetch(`${API_BASE}/api/audits`);
      const d = await r.json();
      setAudits(d.audits || []); setErr(null);
    } catch (e) { setErr(String(e)); }
  }, []);
  useEffect(() => { load(); }, [load]);

  return (
    <div style={{ maxWidth: '980px', margin: '0 auto', width: '100%', display: 'flex', flexDirection: 'column', gap: '0.6rem', padding: '1rem' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
        <FileText size={16} style={{ color: 'var(--accent-purple)' }} />
        <h2 style={{ margin: 0, fontSize: '0.95rem' }}>Audit History</h2>
        <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>
          — every completed run, with its full reports{audits?.some((a) => a.contract) ? ' and executed contracts' : ''}
        </span>
        <button className="preset-btn" style={{ marginLeft: 'auto', fontSize: '0.7rem' }} onClick={load}>
          <RefreshCw size={12} style={{ marginRight: '4px', verticalAlign: 'middle' }} /> Refresh
        </button>
      </div>
      {err && <div style={{ fontSize: '0.72rem', color: '#ff5c5c' }}>Failed to load history: {err}</div>}
      {audits && audits.length === 0 && (
        <div style={{ fontSize: '0.74rem', color: 'var(--text-muted)', padding: '1.5rem', textAlign: 'center' }}>
          No completed audits yet — run one in the Live Audit Console and it will be archived here.
        </div>
      )}
      {(audits || []).map((a) => <AuditEntry key={a.id} entry={a} />)}
    </div>
  );
}
