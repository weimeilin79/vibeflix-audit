import { useState, useEffect, useRef } from 'react';
import { createPortal } from 'react-dom';
import { RotateCw } from 'lucide-react';

// Demo-prep control: rolls every vibeflix engine's replicas.
//
// The mesh is dependable for the first few audits after a deploy and then starts refusing
// its own calls, so before a demo you want the replicas recycled. This is NOT a rebuild —
// the backend bumps a MESH_ROLLOUT env stamp on each engine, which is enough for Agent
// Engine to roll new replicas onto the package that is already deployed.
//
// Visibility and whether a key is demanded both come from /api/admin/enabled, so an
// ordinary deployment shows no trace of this. Long-lived shared projects run in "key" mode
// (the console is on the internet and rolling mid-demo in front of an audience is a real
// risk); workshop, one-click and local installs run "open", because those projects are
// short-lived and single-owner and a key would be friction protecting nothing. When a key is
// wanted the operator types it and it lives in sessionStorage — never in this bundle, which
// is served publicly.
//
// The nudge is symptom-driven, never a timer or a run count: the backend raises it only when
// an audit actually showed the credential fault. Measured evidence for why a timer would be
// wrong is in eng-report/UPSTREAM-BUG-mtls-handshake-agent-identity.md.

const POLL_MS = 3000;
const CONFIG_MS = 20000;   // re-read config so the nudge can appear after an audit

export default function MeshRollout() {
  const [cfg, setCfg] = useState(null);   // {rollout, mode, needs_key, nudge, reasons[], audits_since_rollout}
  const [open, setOpen] = useState(false);
  const [adminKey, setAdminKey] = useState(() => sessionStorage.getItem('meshAdminKey') || '');
  const [status, setStatus] = useState(null);   // {running, engines[], error, started}
  const [error, setError] = useState('');
  const timer = useRef(null);
  const cfgTimer = useRef(null);

  useEffect(() => {
    const load = () => fetch('/api/admin/enabled')
      .then(r => r.json())
      .then(setCfg)
      .catch(() => setCfg({ rollout: false }));
    load();
    cfgTimer.current = setInterval(load, CONFIG_MS);
    // ChatAudit blocks a run when the replicas are stale and asks the operator to roll. It
    // fires this event rather than duplicating the dialog (and the key handling) there.
    const openFromElsewhere = () => { load(); setOpen(true); };
    window.addEventListener('vibeflix:open-rollout', openFromElsewhere);
    return () => {
      clearInterval(timer.current); clearInterval(cfgTimer.current);
      window.removeEventListener('vibeflix:open-rollout', openFromElsewhere);
    };
  }, []);

  // Derived above start() on purpose: start() closes over needsKey, and leaving the
  // declaration below the early return relies on TDZ subtleties to stay correct.
  const needsKey = !!cfg?.needs_key;
  const running = !!status?.running;
  const nudge = !!cfg?.nudge && !running;

  const poll = async (key) => {
    try {
      const r = await fetch('/api/admin/rollout', { headers: { 'X-Mesh-Admin-Key': key } });
      if (!r.ok) throw new Error(`status ${r.status}`);
      const d = await r.json();
      setStatus(d);
      if (!d.running) {
        clearInterval(timer.current);
        // Tell ChatAudit the gate may have lifted so it can re-check and unblock.
        window.dispatchEvent(new CustomEvent('vibeflix:rollout-finished'));
      }
    } catch (e) {
      setError(String(e.message || e));
      clearInterval(timer.current);
    }
  };

  const start = async () => {
    setError('');
    const key = adminKey.trim();
    // Short-lived projects (workshop, one-click install, local) run open — asking for a key
    // there would be friction protecting nothing.
    if (needsKey && !key) { setError('Enter the admin key.'); return; }
    try {
      const r = await fetch('/api/admin/rollout', {
        method: 'POST', headers: { 'X-Mesh-Admin-Key': key },
      });
      if (r.status === 403) { setError('That key was refused.'); return; }
      if (r.status === 503) { setError('Rollout is disabled on this deployment.'); return; }
      if (!r.ok) { setError(`Failed: ${r.status}`); return; }
      if (needsKey) sessionStorage.setItem('meshAdminKey', key);
      setStatus({ running: true, engines: [], error: '' });
      clearInterval(timer.current);
      timer.current = setInterval(() => poll(key), POLL_MS);
      poll(key);
    } catch (e) {
      setError(String(e.message || e));
    }
  };

  if (!cfg?.rollout) return null;

  const engines = status?.engines || [];
  const done = status && !status.running && status.phase === 'done';
  const failed = status && !status.running && status.phase === 'failed';
  const verifying = status?.phase === 'verifying';
  const reasons = cfg.reasons || [];

  return (
    <>
      <button
        className="preset-btn"
        onClick={() => setOpen(true)}
        title={nudge
          ? `Credential trouble seen on a recent audit:\n· ${reasons.join('\n· ')}\nRefreshing the backend clears it.`
          : "Refresh the backend — give every engine fresh replicas before a demo"}
        style={{
          padding: '0.4rem 0.75rem', fontSize: '0.75rem', display: 'flex',
          alignItems: 'center', gap: '0.35rem', cursor: 'pointer',
          background: nudge ? '#fef7e0' : 'var(--bg-tertiary)',
          borderColor: nudge ? '#f9ab00' : 'var(--glass-border)',
          borderRadius: '0.35rem',
          color: nudge ? '#8a5a00' : 'var(--text-main)', fontWeight: 600,
        }}
      >
        <RotateCw size={13} className={running ? 'spin' : undefined} />
        {running ? 'Refreshing…' : nudge ? 'Refresh Backend ⚠' : 'Refresh Backend'}
      </button>

      {open && createPortal((
        <div
          onClick={(e) => { if (e.target === e.currentTarget && !running) setOpen(false); }}
          style={{
            position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.45)', zIndex: 1000,
            display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '1rem',
          }}
        >
          <div style={{
            background: 'var(--bg-secondary, #fff)', color: 'var(--text-main)',
            border: '1px solid var(--glass-border)', borderRadius: '0.6rem',
            padding: '1.25rem', width: 'min(30rem, 100%)', maxHeight: '80vh', overflowY: 'auto',
            boxShadow: '0 10px 40px rgba(0,0,0,0.3)',
          }}>
            <h3 style={{ margin: '0 0 0.5rem', fontSize: '1rem', fontWeight: 700 }}>
              Refresh the backend
            </h3>
            <p style={{ margin: '0 0 0.75rem', fontSize: '0.85rem', lineHeight: 1.55 }}>
              Refresh the backend before a demo — it takes about 5 minutes to complete.
              <br />
              <span style={{ opacity: 0.75, fontSize: '0.78rem' }}>
                Every engine gets fresh replicas. Audits are held until they are back up.
              </span>
            </p>

            {nudge && (
              <div style={{
                margin: '0 0 0.75rem', padding: '0.5rem 0.6rem', borderRadius: '0.35rem',
                background: '#fef7e0', border: '1px solid #f9ab00', color: '#8a5a00',
                fontSize: '0.75rem', lineHeight: 1.45,
              }}>
                <strong>A recent audit hit the credential fault.</strong>
                <ul style={{ margin: '0.3rem 0 0', paddingLeft: '1.1rem' }}>
                  {reasons.map((r, i) => <li key={i}>{r}</li>)}
                </ul>
                <div style={{ marginTop: '0.3rem', opacity: 0.8 }}>
                  {cfg.audits_since_rollout} audit(s) since the last roll.
                </div>
              </div>
            )}

            {!running && needsKey && (
              <label style={{ display: 'block', fontSize: '0.75rem', fontWeight: 600, marginBottom: '1rem' }}>
                <span style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: '0.5rem' }}>
                  <span>Admin key</span>
                  {/* The key lives behind auth at this short link, so it is never in this bundle. */}
                  <a
                    href="https://goo.gle/vibeflix-key"
                    target="_blank"
                    rel="noopener noreferrer"
                    style={{ fontSize: '0.72rem', fontWeight: 600, color: '#1a73e8', textDecoration: 'none' }}
                  >
                    Obtain mesh key ↗
                  </a>
                </span>
                <input
                  type="password"
                  value={adminKey}
                  autoComplete="off"
                  onChange={(e) => setAdminKey(e.target.value)}
                  onKeyDown={(e) => { if (e.key === 'Enter') start(); }}
                  placeholder="MESH_ADMIN_KEY"
                  style={{
                    width: '100%', marginTop: '0.3rem', padding: '0.4rem 0.5rem',
                    fontSize: '0.8rem', borderRadius: '0.3rem',
                    border: '1px solid var(--glass-border)',
                    background: 'var(--bg-tertiary)', color: 'var(--text-main)',
                  }}
                />
              </label>
            )}

            {engines.length > 0 && (
              <div style={{ margin: '0 0 0.75rem', fontSize: '0.78rem' }}>
                {engines.map((e, i) => (
                  <div key={i} style={{
                    display: 'flex', justifyContent: 'space-between', padding: '0.2rem 0',
                    borderBottom: '1px solid var(--glass-border)',
                  }}>
                    <span>{e.name}</span>
                    <span>{e.ok === null || e.ok === undefined
                      ? '⏳ waiting'
                      : e.ok ? '✅ patch accepted' : `❌ ${e.error || 'failed'}`}</span>
                  </div>
                ))}
              </div>
            )}

            {status?.phase === 'rolling' && (
              <div style={{ margin: '0 0 0.75rem', fontSize: '0.78rem', lineHeight: 1.5 }}>
                <strong>Replacing replicas.</strong>{' '}
                {status.ops_total
                  ? `${status.ops_done || 0}/${status.ops_total} engines finished`
                  : 'waiting for the platform to confirm'}
              </div>
            )}

            {verifying && (
              <div style={{ margin: '0 0 0.75rem', fontSize: '0.78rem', lineHeight: 1.5 }}>
                <strong>Waiting for the engines to answer.</strong>{' '}
                Confirmed {status.ready_streak || 0}/{status.ready_streak_target || 3} healthy
                checks.
                {status.waiting_on?.length > 0 && (
                  <div style={{ opacity: 0.75 }}>still down: {status.waiting_on.join(', ')}</div>
                )}
              </div>
            )}

            {done && !status.error && (
              <p style={{ fontSize: '0.78rem', color: 'var(--text-main)', margin: '0 0 0.75rem' }}>
                Done — every engine has fresh replicas and the mesh is answering again.
              </p>
            )}
            {status?.error && (
              <p style={{ fontSize: '0.78rem', color: '#c5221f', margin: '0 0 0.75rem' }}>
                {status.error}
              </p>
            )}
            {error && (
              <p style={{ fontSize: '0.78rem', color: '#c5221f', margin: '0 0 0.75rem' }}>{error}</p>
            )}

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.5rem' }}>
              <button
                className="preset-btn"
                disabled={running}
                onClick={() => { if (!running) setOpen(false); }}
                title={running ? 'The refresh has to finish first' : undefined}
                style={{ padding: '0.4rem 0.8rem', fontSize: '0.78rem', borderRadius: '0.35rem',
                         cursor: running ? 'not-allowed' : 'pointer', opacity: running ? 0.4 : 1 }}
              >
                {running ? 'Please wait…' : 'Close'}
              </button>
              {!done && (
                <button
                  className="preset-btn"
                  disabled={running}
                  onClick={start}
                  style={{
                    padding: '0.4rem 0.8rem', fontSize: '0.78rem', borderRadius: '0.35rem',
                    fontWeight: 700, cursor: running ? 'not-allowed' : 'pointer',
                    background: running ? 'var(--bg-tertiary)' : '#1a73e8',
                    color: running ? 'var(--text-main)' : '#fff',
                    borderColor: running ? 'var(--glass-border)' : '#1a73e8',
                  }}
                >
                  {running ? 'Refreshing…' : 'Refresh Backend'}
                </button>
              )}
            </div>
          </div>
        </div>
      ), document.body)}
    </>
  );
}
