import React, { useState, useEffect, useCallback } from 'react';
import { RefreshCw, FileText, ChevronDown, ChevronRight, ScrollText, Printer, DatabaseBackup } from 'lucide-react';

const API_BASE = import.meta.env.VITE_API_URL || '';

// ---- Export as PDF: render the entry as a self-contained printable page and open
// the browser's print dialog (Save as PDF). No libraries, works offline. ----
const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

function printEntry(entry) {
  const inp = entry.inputs || {};
  const contract = entry.contract || null;
  const when = entry.ts ? new Date(entry.ts).toLocaleString() : '';
  const niceName = (n) => esc((n || '').replace(/_/g, ' ').replace(/\b(compliance|agent|report)\b/g, '').trim()
    .replace(/\b\w/g, (ch) => ch.toUpperCase()));

  const inputRows = [
    ['Character', inp.character], ['Product category', inp.product_category],
    ['Medium', inp.medium], ['Vendor', inp.vendor], ['Territory', inp.target_market],
    ['Volume', inp.volume ? `${Number(inp.volume).toLocaleString()} units` : null],
    ['Net $/unit', inp.net_unit_price], ['Royalty rate', inp.agreed_royalty_rate],
    ['Advance', inp.agreed_advance], ['Min. guarantee', inp.agreed_mg],
    ['Image', inp.image_uri], ['Note', inp.note],
  ].filter(([, v]) => v != null && v !== '' && v !== 0);

  const workflows = Object.entries(entry.reports || {}).map(([name, r]) => {
    const items = [...(r?.findings || []), ...(r?.issues || [])].filter((x) => x && typeof x === 'object');
    const rows = items.map((it) =>
      `<li class="${it.severity === 'critical' ? 'crit' : 'warn'}">${esc(it.description || it.issue_type || 'Issue')}</li>`).join('');
    const legal = r?.legal_cleared ? `<p class="legal">${esc(r.legal_cleared)}</p>` : '';
    return `<section>
      <h2>${niceName(name)} <span class="status s-${esc((r?.status || '').toLowerCase())}">${esc((r?.status || '?').toUpperCase())}</span></h2>
      ${legal}${items.length ? `<ul>${rows}</ul>` : (legal ? '' : '<p class="muted">No findings.</p>')}
    </section>`;
  }).join('');

  const contractRows = contract ? [
    ['Contract id', contract.contract_id], ['Status', contract.status],
    ['Vendor', contract.vendor_id], ['Character', contract.character_id],
    ['Category', contract.category], ['Territory', contract.territory],
    ['Royalty', contract.royalty_pct != null ? `${contract.royalty_pct}%` : null],
    ['Production volume', contract.production_volume ? `${Number(contract.production_volume).toLocaleString()} units` : null],
    ['Safety certification', contract.safety_cert_id], ['HS code', contract.hs_code],
    ['License amendment', contract.amendment_id],
  ].filter(([, v]) => v != null && v !== '') : [];

  const html = `<!doctype html><html><head><meta charset="utf-8">
<title>Vibeflix Audit Report ${esc(contract?.contract_id || entry.id || '')}</title>
<style>
  body { font: 13px/1.5 -apple-system, 'Segoe UI', Roboto, sans-serif; color: #111; margin: 2.2rem 2.6rem; }
  h1 { font-size: 1.35rem; margin: 0 0 0.1rem; } h2 { font-size: 0.95rem; margin: 1.1rem 0 0.3rem; border-bottom: 1px solid #ddd; padding-bottom: 0.2rem; }
  .sub { color: #666; font-size: 0.8rem; margin-bottom: 0.9rem; }
  .banner { display: inline-block; padding: 0.25rem 0.7rem; border-radius: 4px; font-weight: 700; font-size: 0.85rem; margin: 0.4rem 0 0.8rem; }
  .pass { background: #e6f6ec; color: #137a3d; border: 1px solid #9fd8b4; }
  .fail { background: #fdf3e0; color: #9a6a0c; border: 1px solid #ecd49a; }
  table { border-collapse: collapse; margin: 0.3rem 0 0.6rem; } td { padding: 0.18rem 1.1rem 0.18rem 0; vertical-align: top; }
  td:first-child { color: #666; white-space: nowrap; } td:last-child { font-weight: 600; word-break: break-all; }
  ul { margin: 0.2rem 0 0.4rem 1.2rem; padding: 0; } li { margin: 0.15rem 0; }
  li.crit::marker { content: '⛔ '; } li.warn::marker { content: '⚠️ '; }
  .status { font-size: 0.72rem; padding: 0.1rem 0.45rem; border-radius: 3px; margin-left: 0.4rem; vertical-align: middle; }
  .s-cleared, .s-compliant { background: #e6f6ec; color: #137a3d; }
  .s-blocked, .s-failed { background: #fdeaea; color: #b3261e; }
  .s-flagged, .s-needs_input, .s-rejected { background: #fdf3e0; color: #9a6a0c; }
  .legal { font-weight: 600; } .muted { color: #888; }
  footer { margin-top: 1.4rem; padding-top: 0.5rem; border-top: 1px solid #ddd; color: #999; font-size: 0.72rem; }
  @media print { body { margin: 0.6in; } }
</style></head><body>
  <h1>🎯 Vibeflix — Licensing Compliance Audit Report</h1>
  <div class="sub">Run ${esc(entry.id || '')} · ${esc(when)}</div>
  <div class="banner ${entry.passed ? 'pass' : 'fail'}">${entry.passed ? '✅ ALL WORKFLOWS PASSED' : '⚠️ COMPLETED WITH FINDINGS'}</div>
  <h2>Audit inputs</h2>
  <table>${inputRows.map(([k, v]) => `<tr><td>${esc(k)}</td><td>${esc(v)}</td></tr>`).join('')}</table>
  ${workflows}
  ${contract ? `<h2>📜 Executed licensing contract</h2>
  <table>${contractRows.map(([k, v]) => `<tr><td>${esc(k)}</td><td>${esc(v)}</td></tr>`).join('')}</table>` : ''}
  <footer>Generated by the Vibeflix Adaptive Licensing Mesh · multi-agent audit (brand style · vendor &amp; licensing · deal pricing · legal clearance)</footer>
<script>window.onload = () => setTimeout(() => window.print(), 150);</script>
</body></html>`;

  const w = window.open('', '_blank');
  if (!w) return;
  w.document.write(html);
  w.document.close();
}

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
    ['Production volume', contract.production_volume ? `${Number(contract.production_volume).toLocaleString()} units` : null],
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
        <button className="preset-btn" style={{ fontSize: '0.66rem', padding: '0.2rem 0.5rem' }}
          title="Open a printable report — choose 'Save as PDF' in the print dialog"
          onClick={(e) => { e.stopPropagation(); printEntry(entry); }}>
          <Printer size={11} style={{ marginRight: '3px', verticalAlign: 'middle' }} /> Export PDF
        </button>
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
  const [resetting, setResetting] = useState(false);
  const [resetMsg, setResetMsg] = useState(null);
  const load = useCallback(async () => {
    try {
      const r = await fetch(`${API_BASE}/api/audits`);
      const d = await r.json();
      setAudits(d.audits || []); setErr(null);
    } catch (e) { setErr(String(e)); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const resetDb = async () => {
    if (!window.confirm(
      'Reset the demo database to its original state?\n\n' +
      '• vendors → pristine defaults (onboarded vendors & added categories removed)\n' +
      '• executed licensing contracts cleared\n' +
      '• audit history wiped (Firestore + local)\n' +
      '• uploaded mockup images deleted from gs://vibeflix-request-image\n\n' +
      'This cannot be undone.')) return;
    setResetting(true); setResetMsg(null);
    try {
      const r = await fetch(`${API_BASE}/api/reset`, { method: 'POST' });
      const d = await r.json();
      const v = d.vendors || {};
      setResetMsg(`✅ Reset done — ${v.vendors_restored ?? '?'} vendors restored, ` +
        `${v.extra_vendors_deleted ?? 0} onboarded vendor(s) removed, ` +
        `${v.contracts_cleared ?? 0} contract(s) cleared, ` +
        `${d.history_cleared ?? 0} audit(s) wiped, ${d.uploads_deleted ?? 0} upload(s) deleted.`);
      await load();
    } catch (e) {
      setResetMsg(`Reset failed: ${e}`);
    } finally {
      setResetting(false);
    }
  };

  return (
    <div style={{ maxWidth: '980px', margin: '0 auto', width: '100%', display: 'flex', flexDirection: 'column', gap: '0.6rem', padding: '1rem' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
        <FileText size={16} style={{ color: 'var(--accent-purple)' }} />
        <h2 style={{ margin: 0, fontSize: '0.95rem' }}>Audit History</h2>
        <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>
          — one entry per audit (latest state; re-submits update it), with full reports{audits?.some((a) => a.contract) ? ' and executed contracts' : ''}
        </span>
        <button className="preset-btn" style={{ marginLeft: 'auto', fontSize: '0.7rem' }} onClick={load}>
          <RefreshCw size={12} style={{ marginRight: '4px', verticalAlign: 'middle' }} /> Refresh
        </button>
        <button className="preset-btn" disabled={resetting}
          title="Restore the demo to its original state: default vendors, no contracts, empty history, uploads deleted"
          style={{ fontSize: '0.7rem', color: '#ff5c5c', borderColor: 'rgba(255,92,92,0.45)' }}
          onClick={resetDb}>
          <DatabaseBackup size={12} style={{ marginRight: '4px', verticalAlign: 'middle' }} />
          {resetting ? 'Resetting…' : 'Reset database'}
        </button>
      </div>
      {resetMsg && <div style={{ fontSize: '0.72rem', color: resetMsg.startsWith('✅') ? 'var(--color-success, #3ddc84)' : '#ff5c5c' }}>{resetMsg}</div>}
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
