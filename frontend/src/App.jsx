import { useState, useEffect } from 'react';
import {
  Shield, Sliders, RefreshCw, BarChart2, Info, GitBranch, Layers, Database
} from 'lucide-react';
import ChatAudit from './ChatAudit';
import AuditHistory from './AuditHistory';
import DatabaseView from './DatabaseView';

// App is the SHELL: the tab bar, the dark-mode toggle, and the two static explainer
// tabs. Everything live happens in the children — ChatAudit runs the audit and renders
// the streamed A2UI surface (@a2ui/react), AuditHistory and DatabaseView read their own
// endpoints. No audit state lives here.

export default function App() {
  const [activeTab, setActiveTab] = useState('canvas');
  const [darkMode, setDarkMode] = useState(false);

  useEffect(() => {
    document.body.classList.toggle('dark-mode', darkMode);
  }, [darkMode]);

  return (
    <div className="app-container">
      
      {/* Top Application Header */}
      <header className="app-header">
        <div className="logo-container">
          <span className="logo-icon" style={{ fontSize: '1.4rem' }}>🎯</span>
          <div className="logo-text">
            <h1 style={{ fontFamily: 'var(--font-family-display)', fontSize: '1.2rem', fontWeight: 900, letterSpacing: '-0.03em', margin: 0 }}>
              <span style={{ color: '#1a73e8' }}>V</span>
              <span style={{ color: '#ea4335' }}>i</span>
              <span style={{ color: '#fbbc05' }}>b</span>
              <span style={{ color: '#1a73e8' }}>e</span>
              <span style={{ color: '#34a853' }}>f</span>
              <span style={{ color: '#ea4335' }}>l</span>
              <span style={{ color: '#1a73e8' }}>i</span>
              <span style={{ color: '#ea4335' }}>x</span>
              <span style={{ color: 'var(--text-dark)', marginLeft: '4px' }}>Audit</span>
            </h1>
            <p style={{ margin: 0 }}>Adaptive Licensing Mesh Workspace</p>
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
          <div className="tab-nav">
            <button 
              className={`tab-btn ${activeTab === 'canvas' ? 'active' : ''}`}
              onClick={() => setActiveTab('canvas')}
            >
              <Sliders size={14} style={{ marginRight: '4px', display: 'inline-block', verticalAlign: 'middle' }} /> Live Audit Console
            </button>
            <button
              className={`tab-btn ${activeTab === 'history' ? 'active' : ''}`}
              onClick={() => setActiveTab('history')}
            >
              <Database size={14} style={{ marginRight: '4px', display: 'inline-block', verticalAlign: 'middle' }} /> Audit History
            </button>
            <button
              className={`tab-btn ${activeTab === 'database' ? 'active' : ''}`}
              onClick={() => setActiveTab('database')}
            >
              <Layers size={14} style={{ marginRight: '4px', display: 'inline-block', verticalAlign: 'middle' }} /> Database
            </button>
            <button
              className={`tab-btn ${activeTab === 'usecase' ? 'active' : ''}`}
              onClick={() => setActiveTab('usecase')}
            >
              <Info size={14} style={{ marginRight: '4px', display: 'inline-block', verticalAlign: 'middle' }} /> Use Case & Workflows
            </button>
            <button 
              className={`tab-btn ${activeTab === 'contrast' ? 'active' : ''}`}
              onClick={() => setActiveTab('contrast')}
            >
              <BarChart2 size={14} style={{ marginRight: '4px', display: 'inline-block', verticalAlign: 'middle' }} /> Stakeholder Matrix & Theory
            </button>
          </div>

          <button 
            className="preset-btn"
            onClick={() => setDarkMode(prev => !prev)}
            style={{ 
              padding: '0.4rem 0.75rem', 
              fontSize: '0.75rem',
              display: 'flex',
              alignItems: 'center',
              gap: '0.35rem',
              cursor: 'pointer',
              background: 'var(--bg-tertiary)',
              borderColor: 'var(--glass-border)',
              borderRadius: '0.35rem',
              color: 'var(--text-main)',
              fontWeight: 600
            }}
            title="Toggle Light/Dark Theme"
          >
            {darkMode ? '☀️ Light Mode' : '🌙 Dark Mode'}
          </button>
        </div>
      </header>

      {/* Main Workspace Body */}
      <div className="workspace-body" style={{ gridTemplateColumns: '1fr', ...(activeTab === 'canvas' ? { gridTemplateRows: '1fr', minHeight: 0 } : {}) }}>
        
        {activeTab === 'usecase' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem', width: '100%', height: '100%', overflowY: 'auto' }}>
            {/* Top Overview Hero Card */}
            <div className="canvas-panel" style={{ padding: '1.5rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '0.75rem' }}>
                <span style={{ fontSize: '2rem' }}>🎯</span>
                <div>
                  <h2 style={{ fontFamily: 'var(--font-family-display)', fontSize: '1.4rem', fontWeight: 800, color: 'var(--accent-blue)', margin: 0 }}>
                    Global Merchandising License Verification Workspace
                  </h2>
                  <p style={{ fontSize: '0.85rem', color: 'var(--text-muted)', margin: 0 }}>
                    Vibeflix Sourcing Compliance & IP Infringement Counterfeit Audit Framework
                  </p>
                </div>
              </div>
              <p style={{ fontSize: '0.85rem', color: 'var(--text-main)', lineHeight: '1.5', marginTop: '0.5rem' }}>
                The Vibeflix Merchandising ecosystem handles the global sourcing of licensed consumer items (vinyl figures, toy prototypes, apparel). To prevent severe downstream errors—ranging from trademark exclusions and copyright lawsuits to under-priced licensing deals—this workspace coordinates and executes real-time multi-agent compliance audits prior to placing manufacturing orders.
              </p>
            </div>

            {/* Split Details Section */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: '1.5rem' }}>
              
              {/* Left Column: Business Problem & Agents Mesh */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
                
                {/* Sourcing Challenges Card */}
                <div className="canvas-panel" style={{ flex: 1 }}>
                  <h3 className="panel-title" style={{ fontSize: '0.95rem', borderBottom: '1px solid var(--glass-border)', paddingBottom: '0.5rem' }}>
                    <Shield size={16} style={{ color: 'var(--color-danger)' }} /> Core Sourcing Challenges
                  </h3>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', marginTop: '0.5rem' }}>
                    <div style={{ fontSize: '0.8rem' }}>
                      <strong style={{ color: 'var(--color-danger)' }}>1. Style & Branding Guideline Compliance:</strong> Manual packaging audit takes days, risking typography mismatch (uncertified fonts) and incorrect swatches.
                    </div>
                    <div style={{ fontSize: '0.8rem' }}>
                      <strong style={{ color: 'var(--color-danger)' }}>2. Territorial Exclusivity Locks:</strong> Sourcing items in restricted zones (e.g. North America exclusivity blocks with third-parties) leads to contract breach and customs seizures.
                    </div>
                    <div style={{ fontSize: '0.8rem' }}>
                      <strong style={{ color: 'var(--color-danger)' }}>3. Under-priced Licensing Deals:</strong> A vendor agreeing to pay below the rate card (royalty + advance + minimum guarantee) erodes the IP's value and shorts the licensor.
                    </div>
                    <div style={{ fontSize: '0.8rem' }}>
                      <strong style={{ color: 'var(--color-danger)' }}>4. Sourcing Overproduction Limits:</strong> Ordering volume past approved caps without authorized overrides breaches master manufacturing agreements.
                    </div>
                  </div>
                </div>

                {/* ADK 2.0 Mesh Coordination Card */}
                <div className="canvas-panel" style={{ flex: 1 }}>
                  <h3 className="panel-title" style={{ fontSize: '0.95rem', borderBottom: '1px solid var(--glass-border)', paddingBottom: '0.5rem' }}>
                    <GitBranch size={16} style={{ color: 'var(--accent-blue)' }} /> Multi-Agent Auditing Mesh (ADK 2.0)
                  </h3>
                  <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                    Instead of sequential human reviews, the <strong>Sourcing Orchestrator</strong> routes packaging design mockups and volume orders to three domain compliance agents running concurrently — and Vendor &amp; Licensing hands off to a <strong>Legal Clearance agent</strong>. When <strong>every workflow passes</strong>, the orchestrator's <em>contract_finalize</em> step ensures the audit ends with an <strong>executed licensing contract</strong> (📜 Final Clearance Report); every completed run is archived in the <strong>Audit History</strong> tab, exportable as PDF.
                  </p>
                  <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', fontWeight: 600, margin: '0.7rem 0 0.3rem' }}>
                    Each agent is a demo of a distinct agent-engineering pattern:
                  </div>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.6rem', marginTop: '0.2rem' }}>
                    <div style={{ background: 'var(--bg-secondary)', border: '1px solid var(--glass-border)', padding: '0.5rem', borderRadius: '4px', fontSize: '0.75rem' }}>
                      <strong style={{ color: '#fbbc05', display: 'block', marginBottom: '0.2rem' }}>🧭 Orchestrator — routing &amp; session start</strong>
                      The main <strong>router</strong> and the <strong>starting point of the trace span</strong>. It reads each incoming request, decides which workflows to run (all three on a first audit, only the affected ones on a re-run), and is where the run's <strong>session memory</strong> is created. Fans the domain agents out concurrently, then owns recovery, the volume-cap decision, and contract finalization.
                    </div>
                    <div style={{ background: 'var(--bg-secondary)', border: '1px solid var(--glass-border)', padding: '0.5rem', borderRadius: '4px', fontSize: '0.75rem' }}>
                      <strong style={{ color: '#1a73e8', display: 'block', marginBottom: '0.2rem' }}>🎨 Style Agent — multimodal + deterministic checks</strong>
                      <strong>Multimodal</strong>: it reads the packaging mockup, extracts everything it needs (printed text, product medium), and pulls the <strong>branding rules from its Skill</strong> to drive the checks. The checking itself is <strong>deterministic</strong> — run inside a <strong>pre-existing MCP workflow</strong> the agent operates on its own by extracting the right parameters, with no human in the loop.
                    </div>
                    <div style={{ background: 'var(--bg-secondary)', border: '1px solid var(--glass-border)', padding: '0.5rem', borderRadius: '4px', fontSize: '0.75rem' }}>
                      <strong style={{ color: '#ea4335', display: 'block', marginBottom: '0.2rem' }}>⚖️ Vendor &amp; Licensing — agent-to-agent comms</strong>
                      Demonstrates <strong>A2A communication</strong>: based on the case it hands off to a <strong>remote Legal agent</strong> — a <strong>two-layer</strong> exchange (it can even answer Legal's questions itself via a liaison). It also drives <strong>multiple MCP servers</strong> (vendors, exclusivity, trademark, market), and its <strong>agent identity / profile setup is the most involved</strong> in the mesh.
                    </div>
                    <div style={{ background: 'var(--bg-secondary)', border: '1px solid var(--glass-border)', padding: '0.5rem', borderRadius: '4px', fontSize: '0.75rem' }}>
                      <strong style={{ color: '#c9922e', display: 'block', marginBottom: '0.2rem' }}>💰 Deal Pricing — reasoning over deterministic data</strong>
                      Shows an agent <strong>reasoning across multiple MCP tools</strong>. The inputs and calculations are <strong>deterministic</strong> (rate cards, projected royalty, MG / advance math from the MCP servers), but the <strong>verdict is the agent's reasoning</strong> over that data through an evaluate→validate→iterate loop — not a hardcoded rule.
                    </div>
                    <div style={{ background: 'var(--bg-secondary)', border: '1px solid var(--accent-purple)', padding: '0.5rem', borderRadius: '4px', fontSize: '0.75rem' }}>
                      <strong style={{ color: 'var(--accent-purple)', display: 'block', marginBottom: '0.2rem' }}>⚖️ Legal Clearance — the remote agent</strong>
                      The standalone agent Vendor &amp; Licensing hands off to (on onboarding, or when the orchestrator requests contract finalization). It <strong>RAG-discovers</strong> its undefined process from scattered internal docs, self-issues a provisional safety cert when none is on file, and executes the LC-#### contract.
                    </div>
                    <div style={{ background: 'var(--bg-secondary)', border: '1px solid #34a853', padding: '0.5rem', borderRadius: '4px', fontSize: '0.75rem' }}>
                      <strong style={{ color: '#34a853', display: 'block', marginBottom: '0.2rem' }}>🖥 UI Renderer — A2UI integration</strong>
                      Integrates with the client's <strong>A2UI library</strong>: instead of agents returning raw JSON, it turns each result into <strong>A2UI surface components</strong> — the live panels and report cards you watch stream into the console — so the interface is generated by the agents rather than hand-coded per report.
                    </div>
                  </div>
                </div>

              </div>


            </div>

            {/* Full-width: Animated Workflow Flowchart */}
            <div className="canvas-panel" style={{ justifyContent: 'space-between' }}>
              <div>
                <h3 className="panel-title" style={{ fontSize: '0.95rem', borderBottom: '1px solid var(--glass-border)', paddingBottom: '0.5rem' }}>
                  <RefreshCw size={16} className="spin" style={{ animation: 'spin 12s linear infinite', color: 'var(--color-success)' }} />
                  Compliance Lifespans: Visual Workflow
                </h3>
                <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: '0.75rem' }}>
                  Hover over nodes to trace how information streams dynamically in the agent mesh. Blue flow dash offset shows active auditing path.
                </p>
              </div>

              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', width: '100%', margin: '0.5rem 0' }}>
                {/* Inserted SVG Workflow Diagram */}
                <svg width="100%" height="345" viewBox="0 0 820 270" style={{ background: 'var(--bg-secondary)', borderRadius: '8px', border: '1px solid var(--glass-border)', padding: '0.5rem' }}>
                  <defs>
                    <marker id="arrow" viewBox="0 0 10 10" refX="6" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
                      <path d="M 0 2 L 10 5 L 0 8 z" fill="var(--text-muted)" />
                    </marker>
                  </defs>

                  {/* edges (solid): App → Orchestrator, App → UI Renderer */}
                  <path d="M 112 120 L 200 62" stroke="var(--glass-border)" strokeWidth="1.5" fill="none" markerEnd="url(#arrow)" />
                  <path d="M 112 148 L 200 210" stroke="var(--glass-border)" strokeWidth="1.5" fill="none" markerEnd="url(#arrow)" />
                  {/* Orchestrator fan-out → brand ‖ vendor ‖ pricing */}
                  <path d="M 330 45 L 470 33" stroke="var(--glass-border)" strokeWidth="1.5" fill="none" markerEnd="url(#arrow)" />
                  <path d="M 330 59 L 470 113" stroke="var(--glass-border)" strokeWidth="1.5" fill="none" markerEnd="url(#arrow)" />
                  <path d="M 330 73 L 470 223" stroke="var(--glass-border)" strokeWidth="1.5" fill="none" markerEnd="url(#arrow)" />
                  {/* Vendor & Licensing ⇢ Legal (private hand-off, dotted) */}
                  <path d="M 620 115 L 658 116" stroke="var(--accent-purple)" strokeWidth="1.5" fill="none" strokeDasharray="3 3" markerEnd="url(#arrow)" />

                  {/* animated active flow */}
                  <path d="M 112 120 L 200 62" stroke="#fbbc05" strokeWidth="1.5" fill="none" strokeDasharray="6 6" className="animated-flow" />
                  <path d="M 112 148 L 200 210" stroke="#1a73e8" strokeWidth="1.5" fill="none" strokeDasharray="6 6" className="animated-flow" />
                  <path d="M 330 59 L 470 113" stroke="#34a853" strokeWidth="1.5" fill="none" strokeDasharray="6 6" className="animated-flow" />

                  {/* App — serves the console, streams SSE, talks to orchestrator + presenter */}
                  <g transform="translate(12, 105)">
                    <rect width="100" height="58" rx="6" fill="var(--bg-card)" stroke="var(--accent-purple)" strokeWidth="2" />
                    <text x="50" y="22" fill="var(--text-dark)" fontSize="9" fontWeight="bold" textAnchor="middle">🌐 App</text>
                    <text x="50" y="37" fill="var(--accent-purple)" fontSize="7.5" fontWeight="bold" textAnchor="middle">React + FastAPI</text>
                    <text x="50" y="50" fill="var(--text-muted)" fontSize="7" textAnchor="middle">SSE · A2UI stream</text>
                  </g>

                  {/* Orchestrator — dispatches the three compliance workflows */}
                  <g transform="translate(200, 30)">
                    <rect width="130" height="58" rx="6" fill="var(--bg-card)" stroke="var(--color-warning)" strokeWidth="2" />
                    <text x="65" y="22" fill="var(--text-dark)" fontSize="9" fontWeight="bold" textAnchor="middle">Orchestrator</text>
                    <text x="65" y="37" fill="var(--color-warning)" fontSize="7.5" fontWeight="bold" textAnchor="middle">dispatch · recover · HITL</text>
                    <text x="65" y="50" fill="var(--text-muted)" fontSize="7" textAnchor="middle">report + contract finalize</text>
                  </g>

                  {/* UI Renderer — standalone presenter, called only by the App */}
                  <g transform="translate(200, 190)">
                    <rect width="130" height="54" rx="6" fill="var(--bg-card)" stroke="var(--accent-blue)" strokeWidth="2" />
                    <text x="65" y="20" fill="var(--text-dark)" fontSize="9" fontWeight="bold" textAnchor="middle">UI Renderer</text>
                    <text x="65" y="34" fill="var(--accent-blue)" fontSize="7.5" fontWeight="bold" textAnchor="middle">A2UI panels</text>
                    <text x="65" y="47" fill="var(--text-muted)" fontSize="7" textAnchor="middle">standalone · reports → surface</text>
                  </g>

                  {/* Brand Style */}
                  <g transform="translate(470, 13)">
                    <rect width="150" height="40" rx="6" fill="var(--bg-card)" stroke="var(--glass-border)" strokeWidth="1" />
                    <text x="10" y="18" fill="var(--text-dark)" fontSize="9" fontWeight="bold">🎨 Brand Style</text>
                    <text x="10" y="32" fill="#1a73e8" fontSize="7" fontWeight="bold">trademark match · medium · fonts</text>
                    <circle cx="140" cy="12" r="3.5" fill="#34a853" />
                  </g>

                  {/* Vendor & Licensing */}
                  <g transform="translate(470, 95)">
                    <rect width="150" height="40" rx="6" fill="var(--bg-card)" stroke="var(--glass-border)" strokeWidth="1" />
                    <text x="10" y="18" fill="var(--text-dark)" fontSize="9" fontWeight="bold">⚖️ Vendor &amp; Licensing</text>
                    <text x="10" y="32" fill="#ea4335" fontSize="7" fontWeight="bold">exclusivity · trademark · vendors</text>
                    <circle cx="140" cy="12" r="3.5" fill="#fbbc05" />
                  </g>

                  {/* Deal Pricing */}
                  <g transform="translate(470, 205)">
                    <rect width="150" height="40" rx="6" fill="var(--bg-card)" stroke="var(--glass-border)" strokeWidth="1" />
                    <text x="10" y="18" fill="var(--text-dark)" fontSize="9" fontWeight="bold">💰 Deal Pricing</text>
                    <text x="10" y="32" fill="#c9922e" fontSize="7" fontWeight="bold">royalty · advance · MG</text>
                    <circle cx="140" cy="12" r="3.5" fill="#34a853" />
                  </g>

                  {/* Legal Clearance — private, only Vendor & Licensing calls it (dotted) */}
                  <g transform="translate(660, 94)">
                    <rect width="150" height="44" rx="6" fill="var(--bg-card)" stroke="var(--accent-purple)" strokeWidth="1.5" strokeDasharray="4 3" />
                    <text x="10" y="18" fill="var(--text-dark)" fontSize="8.5" fontWeight="bold">⚖️ Legal Clearance</text>
                    <text x="10" y="32" fill="var(--accent-purple)" fontSize="6.5" fontWeight="bold">RAG · executes contract (LC-#)</text>
                  </g>
                </svg>
              </div>

              <div style={{ display: 'flex', justifyContent: 'space-between', background: 'var(--bg-secondary)', border: '1px solid var(--glass-border)', padding: '0.6rem 0.85rem', borderRadius: '6px' }}>
                <span style={{ fontSize: '0.75rem', fontWeight: 'bold' }}>💻 System Ready to Run:</span>
                <span style={{ fontSize: '0.75rem', color: 'var(--accent-blue)', cursor: 'pointer', fontWeight: 'bold' }} onClick={() => setActiveTab('canvas')}>
                  Go to Live Audit Console ➔
                </span>
              </div>
            </div>

            {/* Agent Gateway & Agent Identity — platform security */}
            <div className="canvas-panel">
              <h3 className="panel-title" style={{ fontSize: '0.95rem', borderBottom: '1px solid var(--glass-border)', paddingBottom: '0.5rem' }}>
                <Shield size={16} style={{ color: 'var(--accent-purple)' }} /> Agent Gateway &amp; Agent Identity — how the mesh is secured
              </h3>
              <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginTop: '0.5rem' }}>
                Every agent runs on Agent Engine behind a <strong>governed gateway</strong>, authenticated as its own <strong>Agent Identity</strong> — no shared service account. That pairing is what lets a licensing mesh prove <em>which</em> agent did <em>what</em>, and stop any agent from reaching a service it wasn't approved for.
              </p>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.6rem', marginTop: '0.5rem' }}>
                <div style={{ background: 'var(--bg-secondary)', border: '1px solid var(--glass-border)', padding: '0.5rem', borderRadius: '4px', fontSize: '0.75rem' }}>
                  <strong style={{ color: '#1a73e8', display: 'block', marginBottom: '0.2rem' }}>🪪 Agent Identity</strong>
                  Each engine gets its <strong>own principal</strong> (<code>principal://…/reasoningEngines/&lt;id&gt;</code>), set at create time (<code>identity_type=AGENT_IDENTITY</code>) — there is <strong>no service account</strong> behind it. Every call it makes is attributed to that identity, and IAM is granted to the specific principal.
                </div>
                <div style={{ background: 'var(--bg-secondary)', border: '1px solid var(--glass-border)', padding: '0.5rem', borderRadius: '4px', fontSize: '0.75rem' }}>
                  <strong style={{ color: '#34a853', display: 'block', marginBottom: '0.2rem' }}>🚪 Agent Gateway</strong>
                  A <strong>default-deny egress proxy</strong> in front of every agent. An agent can only reach endpoints <strong>registered</strong> with the gateway; each outbound call carries a <code>Proxy-Authorization</code> header the gateway checks before forwarding (per-tool allow-lists). Unregistered egress is refused.
                </div>
                <div style={{ gridColumn: '1 / -1', background: 'var(--bg-secondary)', border: '1px solid var(--accent-purple)', padding: '0.5rem', borderRadius: '4px', fontSize: '0.75rem' }}>
                  <strong style={{ color: 'var(--accent-purple)', display: 'block', marginBottom: '0.2rem' }}>🔒 Least-privilege by design</strong>
                  Because every agent carries a <strong>verifiable identity</strong> and can only reach <strong>allow-listed services</strong>, every action is attributable and <strong>auditable end-to-end</strong>, and a misbehaving agent can't touch anything it wasn't granted. Security is enforced by the platform — not bolted on afterward.
                </div>
              </div>
            </div>

          </div>
        )}

        {/* ChatAudit stays MOUNTED across tab switches so the chat session (transcript,
            surfaces, run_token chain, workflow graph) survives — only its New button
            resets it. `display: contents` keeps the grid layout identical when shown;
            `none` hides it without unmounting. A running SSE stream keeps going too. */}
        <div style={{ display: activeTab === 'canvas' ? 'contents' : 'none' }}>
          <ChatAudit />
        </div>

        {activeTab === 'history' && (
          <div style={{ width: '100%', height: '100%', overflowY: 'auto' }}>
            <AuditHistory />
          </div>
        )}

        {activeTab === 'database' && (
          <div style={{ width: '100%', height: '100%', overflowY: 'auto' }}>
            <DatabaseView />
          </div>
        )}

        {activeTab === 'contrast' && (
          <div style={{ display: 'grid', gridTemplateColumns: '1.25fr 1fr', gap: '1.5rem', width: '100%', height: '100%', overflowY: 'auto' }}>
            {/* Left Column: The Contrast Table */}
            <div className="matrix-card" style={{ display: 'flex', flexDirection: 'column', height: 'fit-content' }}>
              <h3 className="panel-title" style={{ borderBottom: '1px solid var(--glass-border)', paddingBottom: '0.5rem', marginBottom: '0.75rem' }}>
                <BarChart2 size={16} style={{ color: 'var(--accent-purple)' }} /> Operational Contrast Matrix: Sourcing Sandbox
              </h3>
              <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: '1rem', margin: 0 }}>
                A side-by-side contrast mapping traditional licensing reviews against our multi-agent canvas mesh.
              </p>
              
              <table className="matrix-table">
                <thead>
                  <tr>
                    <th>Operational Phase</th>
                    <th>The Manual Way (Status Quo)</th>
                    <th>The Agentic Canvas Way (ADK 2.0 + MCP)</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td><strong>Asset Ingestion</strong></td>
                    <td className="manual">Sifting through manufacturer emails; downloading loose image attachments.</td>
                    <td className="agentic">Instant. Drag-and-drop file parsing via Computer Vision matches character IP automatically.</td>
                  </tr>
                  <tr>
                    <td><strong>Style Verification</strong></td>
                    <td className="manual">Visually comparing prototype print mockups against a static, 200-page Brand Guidelines PDF.</td>
                    <td className="agentic">Automated. Font and color extraction tools instantly flag layout typos in real time.</td>
                  </tr>
                  <tr>
                    <td><strong>Exclusivity Checks</strong></td>
                    <td className="manual">Legal teams manually reviewing rows in siloed Excel spreadsheets or parsing legacy ERP databases.</td>
                    <td className="agentic">Real-time. The IP Counsel Agent queries cross-border contracts via MCP tool layers in milliseconds.</td>
                  </tr>
                  <tr>
                    <td><strong>Out-of-Band Risk</strong></td>
                    <td className="manual">PR staff manually searching Taobao and eBay for early product leaks or bootleg pre-orders.</td>
                    <td className="agentic">Proactive. Market Agents constantly scrape international e-commerce endpoints to catch leaks early.</td>
                  </tr>
                  <tr>
                    <td><strong>Resolution Timeline</strong></td>
                    <td className="manual">2 to 3 Weeks of back-and-forth approval loops and corporate document signing.</td>
                    <td className="agentic">Under 2 Minutes via a unified, interactive visual remediation dashboard.</td>
                  </tr>
                </tbody>
              </table>
            </div>

            {/* Right Column: Stakeholder Impact & Theory */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
              
              {/* Stakeholder Realization Grid */}
              <div className="canvas-panel">
                <h3 className="panel-title" style={{ borderBottom: '1px solid var(--glass-border)', paddingBottom: '0.5rem', marginBottom: '0.75rem' }}>
                  <Shield size={16} style={{ color: 'var(--color-success)' }} /> Stakeholder Value Realization
                </h3>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', marginTop: '0.5rem' }}>
                  <div style={{ fontSize: '0.8rem', borderBottom: '1px solid var(--glass-border)', paddingBottom: '0.5rem' }}>
                    <strong style={{ color: 'var(--accent-blue)', display: 'block' }}>Sourcing & SCM Lead:</strong>
                    Compresses prototype verification cycle times by 95%, optimizing vendor pipeline throughput.
                  </div>
                  <div style={{ fontSize: '0.8rem', borderBottom: '1px solid var(--glass-border)', paddingBottom: '0.5rem' }}>
                    <strong style={{ color: 'var(--accent-blue)', display: 'block' }}>Global Legal IP Counsel:</strong>
                    Establishes systematic guardrails over exclusive contracts, eliminating commercial litigation exposure.
                  </div>
                  <div style={{ fontSize: '0.8rem', borderBottom: '1px solid var(--glass-border)', paddingBottom: '0.5rem' }}>
                    <strong style={{ color: 'var(--accent-blue)', display: 'block' }}>Franchise Brand Director:</strong>
                    Preserves storyline timeline embargoes, guaranteeing that physical toy distribution aligns with streaming launches.
                  </div>
                  <div style={{ fontSize: '0.8rem' }}>
                    <strong style={{ color: 'var(--accent-blue)', display: 'block' }}>Sourcing & Contracts Pipeline:</strong>
                    Dispatches verified regional manufacturing contracts and issues compliance sign-off certificates.
                  </div>
                </div>
              </div>

              {/* Architectural Design Theory */}
              <div className="canvas-panel">
                <h3 className="panel-title" style={{ borderBottom: '1px solid var(--glass-border)', paddingBottom: '0.5rem', marginBottom: '0.75rem' }}>
                  <Database size={16} style={{ color: 'var(--accent-purple)' }} /> Design Theory (A2UI & ADK 2.0)
                </h3>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.6rem', fontSize: '0.8rem', marginTop: '0.5rem' }}>
                  <div>
                    <strong style={{ color: 'var(--text-dark)' }}>• Agent-to-User Interface (A2UI):</strong> Instead of static, predefined layouts, the client interface is rendered dynamically base on tool payloads from agents, allowing UI controls to evolve adaptively.
                  </div>
                  <div>
                    <strong style={{ color: 'var(--text-dark)' }}>• ADK 2.0 Python Agent Mesh:</strong> Multiple specialized compliance processes coordinate on an event-driven graph, loop-backing data updates dynamically when parameters resolve.
                  </div>
                  <div>
                    <strong style={{ color: 'var(--text-dark)' }}>• Grouped Model Context Protocol (MCP):</strong> Decouples integration connectors (such as CV model parsing, trademark registers, scrapers) into modular, independent server instances.
                  </div>
                </div>
              </div>

            </div>
          </div>
        )}

      </div>

    </div>
  );
}
