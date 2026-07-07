import React, { useState, useEffect, useRef } from 'react';
import {
  Upload, Send, Shield, AlertTriangle, AlertCircle, CheckCircle,
  MapPin, Sliders, Play, RefreshCw, BarChart2, Terminal, Info,
  ArrowRight, GitBranch, Layers, Check, Database, RefreshCw as LoopIcon, HelpCircle, XCircle, MessagesSquare, Satellite
} from 'lucide-react';
import ChatAudit from './ChatAudit';
import AuditHistory from './AuditHistory';

// Backend base URL. Empty = same origin (the app container's FastAPI serves both
// the static frontend and /api). Set VITE_API_URL for the Vite dev server (e.g.
// http://localhost:8000) when running the frontend separately from the backend.
const API_BASE = import.meta.env.VITE_API_URL || '';

// ---------------------------------------------------------------------------
// A2UI renderer
// Walks the `a2ui_payload.canvas_layout` schema emitted by the Sourcing
// Orchestrator's compile_ui node and paints matching React components. The
// agent decides the layout; the frontend just renders whatever it is handed.
// ---------------------------------------------------------------------------
function A2UIField({ field }) {
  const blocked = field.status === 'blocked';
  const cleared = field.status === 'clear';
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem', flex: '1 1 180px' }}>
      <label style={{ fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.04em', color: 'var(--text-muted)' }}>
        {field.id}
      </label>
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '0.5rem',
        padding: '0.5rem 0.75rem', borderRadius: '0.4rem', fontSize: '0.85rem', fontWeight: 600,
        background: 'var(--bg-secondary)',
        border: `1px solid ${blocked ? 'var(--color-danger)' : cleared ? 'var(--color-success)' : 'var(--glass-border)'}`,
        color: blocked ? 'var(--color-danger)' : 'var(--text-main)'
      }}>
        <span>{typeof field.value === 'number' ? field.value.toLocaleString() : String(field.value)}</span>
        {field.status && (
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: '0.2rem', fontSize: '0.7rem' }}>
            {blocked ? <><AlertCircle size={12} /> blocked</> : <><CheckCircle size={12} /> {field.status}</>}
          </span>
        )}
      </div>
    </div>
  );
}

function A2UIComponent({ component }) {
  if (component.type === 'remediation_form') {
    return (
      <div className="canvas-panel" style={{ padding: '0.85rem' }}>
        <h3 className="panel-title" style={{ fontSize: '0.85rem', marginBottom: '0.5rem' }}>
          <Sliders size={14} /> remediation_form
        </h3>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.75rem' }}>
          {(component.fields || []).map((f, i) => <A2UIField key={f.id || i} field={f} />)}
        </div>
      </div>
    );
  }
  return (
    <div className="canvas-panel" style={{ padding: '0.85rem', fontSize: '0.8rem', color: 'var(--text-muted)' }}>
      Unsupported A2UI component: <code>{component.type}</code>
    </div>
  );
}

function A2UICanvas({ payload }) {
  if (!payload || !payload.canvas_layout) return null;
  const { container, components = [] } = payload.canvas_layout;
  return (
    <div data-container={container} style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
      <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>
        a2ui v{payload.a2ui_version} · container <code>{container}</code>
      </div>
      {components.map((c, i) => <A2UIComponent key={i} component={c} />)}
    </div>
  );
}

export default function App() {
  // Navigation / Tabs
  const [activeTab, setActiveTab] = useState('canvas');

  // Simulation Steps
  // 'idle' -> 'uploading' -> 'analyzing' -> 'negotiating' -> 'warning' -> 'resolved' -> 'completed' -> 'failed'
  const [flowState, setFlowState] = useState('idle');
  const [activeScenario, setActiveScenario] = useState(null);
  
  // Dynamic Sourcing Parameters
  const [targetMarket, setTargetMarket] = useState('North America');
  const [productionVolume, setProductionVolume] = useState(15000);
  const [showSliderGuardrail, setShowSliderGuardrail] = useState(false);
  const [showAddendumSuccess, setShowAddendumSuccess] = useState(false);
  const [showHitlOptions, setShowHitlOptions] = useState(false);
  const [darkMode, setDarkMode] = useState(false);

  // Sourcing & Approval History Log States
  const [currentRunLogged, setCurrentRunLogged] = useState(false);
  const [expandedItemId, setExpandedItemId] = useState(null);
  const [historyFilter, setHistoryFilter] = useState('ALL');
  const [approvalHistory, setApprovalHistory] = useState([
    {
      id: "VIBE-LIC-7742-US",
      asset: "Mandalorian Helmet (Black Series)",
      category: "Vinyl & Props",
      market: "North America",
      volume: 20000,
      timestamp: "Jun 24 14:32",
      scenario: "clean",
      status: "APPROVED",
      path: [
        { name: "Mockup Ingestion", status: "pass", detail: "Validated CV payload format" },
        { name: "Brand Style", status: "pass", detail: "Outfit font compliant" },
        { name: "Legal IP Counsel", status: "pass", detail: "Exclusivity checks passed" },
        { name: "Storyline Lore", status: "pass", detail: "Season 3 Mandalorian lore consistent" },
        { name: "Sourcing Contract", status: "pass", detail: "20,000 units PO Dispatched" }
      ]
    },
    {
      id: "VIBE-LIC-8012-AP",
      asset: "Darth Vader Bobblehead",
      category: "Bobblehead Series",
      market: "Asia-Pacific",
      volume: 22000,
      timestamp: "Jun 25 09:15",
      scenario: "hitl",
      status: "APPROVED",
      path: [
        { name: "Mockup Ingestion", status: "pass", detail: "Validated CV payload format" },
        { name: "Brand Style", status: "pass", detail: "Outfit font compliant" },
        { name: "Legal IP Counsel", status: "warning", detail: "Asia-Pacific Exclusivity Alert resolved" },
        { name: "Storyline Lore", status: "pass", detail: "Vader lore consistent" },
        { name: "Sourcing Contract", status: "pass", detail: "22,000 units PO Dispatched" }
      ]
    }
  ]);

  useEffect(() => {
    if (darkMode) {
      document.body.classList.add('dark-mode');
    } else {
      document.body.classList.remove('dark-mode');
    }
  }, [darkMode]);
  
  // Mockup Box Parameters
  const [mockupFile, setMockupFile] = useState("grogu_mockup_box.png");
  const [fontStyle, setFontStyle] = useState("SpaceGrotesk");
  const [customsStatus, setCustomsStatus] = useState("Valid");
  const [storylineStatus, setStorylineStatus] = useState("Compliant");

  // Multi-Agent Negotiation Stream Log (For Scenario 2)
  const [negotiationLogs, setNegotiationLogs] = useState([]);
  
  // Messages log
  const [chatLogs, setChatLogs] = useState([
    "System active. Choose a scenario below to run the licensing audits."
  ]);
  const [inputText, setInputText] = useState('');
  const fileInputRef = useRef(null);

  // Telemetry logs
  const [logs, setLogs] = useState([
    { id: 1, time: "21:02:45", agent: "Orchestrator", message: "System initialized. Scenario controllers online." }
  ]);
  const terminalEndRef = useRef(null);

  const addLog = (agent, message) => {
    const time = new Date().toLocaleTimeString();
    setLogs(prev => [...prev, { id: Date.now(), time, agent, message }]);
  };

  useEffect(() => {
    if (terminalEndRef.current) {
      terminalEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [logs]);

  // Automated Sourcing Release Finalization when verification succeeds
  useEffect(() => {
    if (flowState === 'resolved') {
      if (activeScenario === 'hitl' && showHitlOptions) {
        return;
      }
      const timer = setTimeout(() => {
        setFlowState('completed');
        setChatLogs(prev => [...prev, "⚡ Auto-Finalization Triggered: Sourcing registry signature submitted to ledger automatically."]);
        addLog("Orchestrator", "Automated Action: Sourcing release finalized on ledger registry.");
      }, 2000);
      return () => clearTimeout(timer);
    }
  }, [flowState, activeScenario, showHitlOptions]);

  // Sourcing Log Effect: Records completed or failed simulation runs to approvalHistory
  useEffect(() => {
    if ((flowState === 'completed' || flowState === 'failed') && !currentRunLogged && activeScenario) {
      setCurrentRunLogged(true);

      const timestamp = new Date().toLocaleString('en-US', {
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
        hour12: false
      }).replace(',', '');

      if (flowState === 'completed') {
        let record = {};
        if (activeScenario === 'clean') {
          record = {
            id: `VIBE-LIC-1092-EU`,
            asset: "Grogu Plush Toy",
            category: "Plush & Textiles",
            market: "Europe",
            volume: productionVolume,
            timestamp,
            scenario: "clean",
            status: "APPROVED",
            path: [
              { name: "Mockup Ingestion", status: "pass", detail: "Validated CV mockup format" },
              { name: "Brand Style", status: "pass", detail: "Certified Outfit font family matched" },
              { name: "Legal IP Counsel", status: "pass", detail: "Europe region non-exclusive clearance" },
              { name: "Storyline Lore", status: "pass", detail: "Concept aligns with season canonical scripts" },
              { name: "Sourcing Contract", status: "pass", detail: `${productionVolume.toLocaleString()} units PO dispatched to primary factory` }
            ]
          };
        } else if (activeScenario === 'collab') {
          record = {
            id: `VIBE-LIC-8841-EU`,
            asset: "Grogu Vinyl Figurine",
            category: "Vinyl Figures",
            market: targetMarket,
            volume: productionVolume,
            timestamp,
            scenario: "collab",
            status: "APPROVED",
            path: [
              { name: "Mockup Ingestion", status: "pass", detail: "Ingested prototype design mockup" },
              { name: "Brand Style", status: "pass", detail: "Replaced SpaceGrotesk with certified Outfit font" },
              { name: "Legal IP Counsel", status: "pass", detail: "Rerouted from North America (Hasbro block) to Europe" },
              { name: "Storyline Lore", status: "pass", detail: "Replaced lightsaber leak image with hover-pram design" },
              { name: "Sourcing Contract", status: "pass", detail: `${productionVolume.toLocaleString()} units PO dispatched to European hub` }
            ]
          };
        } else if (activeScenario === 'hitl') {
          const isSplit = showAddendumSuccess;
          record = {
            id: `VIBE-LIC-9012-SPLIT`,
            asset: "Grogu Bobblehead Figurine",
            category: "Bobblehead Series",
            market: targetMarket,
            volume: isSplit ? 40000 : 25000,
            timestamp,
            scenario: "hitl",
            status: isSplit ? "APPROVED (SPLIT)" : "APPROVED (CAPPED)",
            path: [
              { name: "Mockup Ingestion", status: "pass", detail: "Ingested Bobblehead packaging mockup" },
              { name: "Brand Style", status: "pass", detail: "Outfit font verified compliant" },
              { name: "Legal IP Counsel", status: "pass", detail: "Exclusivity checks passed" },
              { name: "Storyline Lore", status: "pass", detail: "Character concepts consistent with scripts" },
              { 
                name: "Sourcing Contract", 
                status: isSplit ? "warning" : "pass", 
                detail: isSplit 
                  ? "Split override approved: 25k units (Primary) + 15k units (Addendum SC-7798-EU) dispatched"
                  : "Cap enforced: Sourcing volume capped at 25,000 units, excess cancelled" 
              }
            ]
          };
        }
        
        if (record.id) {
          setApprovalHistory(prev => [record, ...prev]);
        }
      } else if (flowState === 'failed') {
        const record = {
          id: `VIBE-LIC-REJ-404`,
          asset: "Bootleg Grogu Plush",
          category: "Plush & Toys",
          market: targetMarket,
          volume: productionVolume,
          timestamp,
          scenario: "fail",
          status: "REJECTED",
          path: [
            { name: "Mockup Ingestion", status: "pass", detail: "Ingested unverified import prototype mockup" },
            { name: "Brand Style", status: "warning", detail: "Flagged SpaceGrotesk font structure anomaly" },
            { name: "Legal IP Counsel", status: "pass", detail: "Exclusivity checklist checked" },
            { name: "Storyline Lore", status: "fail", detail: "CRITICAL: Character leaks Season 4 spoilers (Grogu wielding lightsaber)" },
            { name: "Sourcing Contract", status: "fail", detail: "Release aborted due to lore compliance failure" }
          ]
        };
        setApprovalHistory(prev => [record, ...prev]);
      }
    }
  }, [flowState, activeScenario, targetMarket, productionVolume, showAddendumSuccess, currentRunLogged]);

  // SCENARIO SIMULATOR INTERFACE KICKOFF
  const triggerScenario = (type) => {
    setActiveScenario(type);
    setFlowState('uploading');
    setShowSliderGuardrail(false);
    setShowAddendumSuccess(false);
    setShowHitlOptions(false);
    setNegotiationLogs([]);
    setCurrentRunLogged(false);

    if (type === 'clean') {
      setMockupFile("grogu_plush_clean_box.png");
      setFontStyle("Outfit"); // Certified font
      setTargetMarket("Europe"); // Clear market
      setProductionVolume(15000); // Safe capacity limit
      setCustomsStatus("Valid");
      setStorylineStatus("Compliant");

      setChatLogs(prev => [...prev, "[Scenario Trigger] Ingesting certified Grogu Plush Box Mockup."]);
      addLog("Orchestrator", "Scenario: Clean release audit initialized.");
      addLog("mcp-vision-analyzer", "Running Computer Vision element parser on clean mockup...");

      setTimeout(() => {
        setFlowState('analyzing');
        addLog("Brand Style Compliance Agent", "Evaluating Outfit typography swatches via mcp-ip-registry...");
        addLog("IP Counsel Agent", "Checking exclusivity contracts for Europe via mcp-legal-contracts...");
        addLog("Franchise Storyline & Lore Agent", "Verifying design concept against scripts, lore parameters, and spoiler databases...");

        setTimeout(() => {
          setFlowState('resolved');
          setChatLogs(prev => [...prev, "✅ Clean Audit Passed: Branding, territorial rights, and franchise lore match master contract parameters."]);
          addLog("Brand Style Compliance Agent", "Certified Outfit font family matched successfully. Status: Compliant.");
          addLog("IP Counsel Agent", "Europe cleared. Exclusive figurine locks do not apply. Status: Cleared.");
          addLog("Franchise Storyline & Lore Agent", "Script check: Concept (Grogu in hover-pram) aligns with season scripts. No spoiler leaks found. Status: Compliant.");
          addLog("Orchestrator", "Display Logic: Invoking deploy_audit_canvas layout with clean status mapping.");
        }, 1500);
      }, 1500);

    } else if (type === 'collab') {
      setMockupFile("grogu_vinyl_fig_mockup.jpg");
      setFontStyle("SpaceGrotesk"); // Uncertified font
      setTargetMarket("North America"); // Clash market
      setProductionVolume(15000);
      setCustomsStatus("Valid");
      setStorylineStatus("Spoiler Flagged"); // Initialized to Spoiler Flagged

      setChatLogs(prev => [...prev, "[Scenario Trigger] Ingesting Figurine Prototype Box (Collaborative Agent Negotiation)."]);
      addLog("Orchestrator", "Scenario: Autonomous agent negotiation mesh initialized.");
      addLog("mcp-vision-analyzer", "Running Computer Vision element parser on figurine prototype box...");

      setTimeout(() => {
        setFlowState('analyzing');
        addLog("Brand Style Compliance Agent", "Checking font structures in mcp-ip-registry...");
        addLog("IP Counsel Agent", "Querying territorial licenses for North America in mcp-legal-contracts...");
        addLog("Franchise Storyline & Lore Agent", "Scanning script databases...");

        setTimeout(() => {
          setFlowState('negotiating');
          setChatLogs(prev => [...prev, "🔄 Sourcing Blocks Detected. Starting autonomous inter-agent negotiation mesh..."]);
          
          // Step-by-step simulated multi-agent negotiation conversations
          const steps = [
            { 
              agent: "IP Counsel Agent", 
              message: "IP Exclusivity alert: North America has exclusive licensing locks held by competitor Hasbro. We cannot clear this design as-is." 
            },
            { 
              agent: "Franchise Storyline & Lore Agent", 
              message: "Storyline check: Ingested concept has Grogu box containing a Season 4 lightsaber spoiler element, which violates active spoiler embargos. I suggest Brand Style Agent modify the packaging artwork or replace the primary image asset to remove the lightsaber." 
            },
            { 
              agent: "Brand Style Compliance Agent", 
              message: "Style compliance acknowledging. Replacing the lightsaber prototype image with a compliant season-approved hover-pram design. Also, correcting the uncertified title font 'SpaceGrotesk' to the certified 'Outfit' family." 
            },
            { 
              agent: "IP Counsel Agent", 
              message: "Corrected mockup verified. I've re-queried checking regional contracts. Under the new hover-pram design, Europe and Asia-Pacific regions are completely non-exclusive. I suggest auto-rerouting the sourcing request to Europe." 
            },
            { 
              agent: "Franchise Storyline & Lore Agent", 
              message: "Storyline verifying Europe release scripts: Sourcing schedule matches EU release timelines. Certified image and font cleared. Sourcing safety verified." 
            },
            { 
              agent: "Orchestrator", 
              message: "Audit constraints satisfied: Remapping distribution market to Europe, applying certified hover-pram graphics, and replacing font styling. Unlocking Canvas release." 
            }
          ];

          steps.forEach((step, index) => {
            setTimeout(() => {
              setNegotiationLogs(prev => [...prev, step]);
              addLog(step.agent, `Negotiation: ${step.message}`);
              
              // Dynamic visual parameter updates as agents negotiate in real-time
              if (index === 2) {
                // Brand Style Agent resolves font and replaces the spoiler lightsaber image with a clean design
                setFontStyle("Outfit");
                setMockupFile("grogu_plush_clean_box.png");
              } else if (index === 3) {
                // IP Counsel Agent reroutes the market to Europe
                setTargetMarket("Europe");
              } else if (index === 4) {
                // Storyline Agent clears the timeline alignment
                setStorylineStatus("Compliant");
              } else if (index === steps.length - 1) {
                // Orchestrator finalizes and resolves flow state
                setFlowState('resolved');
                setChatLogs(prev => [...prev, "✅ Negotiation Successful: Agents collaborated to replace the spoiler image, correct font styling, and reroute the market to Europe."]);
              }
            }, (index + 1) * 1800);
          });

        }, 1500);
      }, 1500);

    } else if (type === 'hitl') {
      setMockupFile("grogu_bobblehead_design.jpg");
      setFontStyle("Outfit");
      setTargetMarket("Europe");
      setProductionVolume(40000); // Exceeds the 25k cap limit!
      setCustomsStatus("Valid");
      setStorylineStatus("Compliant");

      setChatLogs(prev => [...prev, "[Scenario Trigger] Ingesting Bobblehead design (Human-in-the-Loop Cap Split)."]);
      addLog("Orchestrator", "Scenario: High capacity release checks initialized.");
      addLog("mcp-vision-analyzer", "Running CV parser on Bobblehead packaging design mockup...");

      setTimeout(() => {
        setFlowState('analyzing');
        addLog("Brand Style Compliance Agent", "Verifying typography rules...");
        addLog("IP Counsel Agent", "Verifying rights for Europe...");
        addLog("Franchise Storyline & Lore Agent", "Verifying bobblehead design details against scripts...");

        setTimeout(() => {
          setFlowState('resolved');
          setChatLogs(prev => [...prev, "💡 Verification Clear. Sourcing capacity cap (25k) check triggered. Human override required."]);
          addLog("Orchestrator", "Volume cap validation engaged. Sourcing request declares 40,000 SKUs.");
          addLog("mcp-procurement-ledger", "check_sku_volume_caps: CAPPED. Primary capacity limit is 25,000 units.");
          addLog("Franchise Storyline & Lore Agent", "Script check passed. Bobblehead details match season guidelines.");
          addLog("Orchestrator", "Sourcing volume exceeds primary cap limit. Human override check required to proceed.");
          // Enable human override selection panel
          setShowHitlOptions(true);
        }, 1500);
      }, 1500);

    } else if (type === 'fail') {
      setMockupFile("bootleg_baby_yoda_plush.png");
      setFontStyle("SpaceGrotesk");
      setTargetMarket("Europe");
      setProductionVolume(15000);
      setCustomsStatus("Valid");
      setStorylineStatus("Spoiler Leak Blocked"); // Storyline fail trigger

      setChatLogs(prev => [...prev, "[Scenario Trigger] Ingesting unverified import prototype (Script/Storyline Leak Failure)."]);
      addLog("Orchestrator", "Scenario: Storyline canon and script audit initialized.");
      addLog("mcp-vision-analyzer", "Running CV checks on prototype character details...");

      setTimeout(() => {
        setFlowState('analyzing');
        addLog("Brand Style Compliance Agent", "Verifying typography...");
        addLog("IP Counsel Agent", "Checking exclusivity contracts...");
        addLog("Franchise Storyline & Lore Agent", "Verifying character assets against unreleased scripts...");

        setTimeout(() => {
          setFlowState('failed');
          setChatLogs(prev => [...prev, "❌ Hard Failure: Prototype design leaks unreleased script spoilers. Release blocked."]);
          addLog("Franchise Storyline & Lore Agent", "CRITICAL BLOCK: Design depicts Grogu wielding a yellow lightsaber, leaking unreleased script Season 4 storylines!");
          addLog("Orchestrator", "Display Layer: Disabling release actions and rendering strict lore block alerts.");
        }, 1500);
      }, 1500);
    }
  };

  // Submit text prompt commands
  const handlePromptSubmit = (e) => {
    e.preventDefault();
    if (!inputText.trim()) return;

    const promptText = inputText;
    setChatLogs(prev => [...prev, `[User Prompt] "${promptText}"`]);
    setInputText('');

    addLog("Orchestrator", `Instruction parsed: "${promptText}"`);

    if (promptText.toLowerCase().includes('clean') || promptText.toLowerCase().includes('scenario 1')) {
      triggerScenario('clean');
    } else if (promptText.toLowerCase().includes('collab') || promptText.toLowerCase().includes('scenario 2') || promptText.toLowerCase().includes('negotiate')) {
      triggerScenario('collab');
    } else if (promptText.toLowerCase().includes('human') || promptText.toLowerCase().includes('hitl') || promptText.toLowerCase().includes('scenario 3')) {
      triggerScenario('hitl');
    } else if (promptText.toLowerCase().includes('fail') || promptText.toLowerCase().includes('spoil') || promptText.toLowerCase().includes('scenario 4')) {
      triggerScenario('fail');
    } else if (flowState === 'warning' && (promptText.toLowerCase().includes('europe') || promptText.toLowerCase().includes('change'))) {
      setTargetMarket('Europe');
    } else {
      setTimeout(() => {
        setChatLogs(prev => [...prev, "Command not recognized. Select a preset scenario buttons on the top left."]);
      }, 800);
    }
  };

  // Monitor market change and simulate agent layout loopback (Only manual adjustments)
  useEffect(() => {
    if (flowState === 'warning' && targetMarket === 'Europe' && activeScenario !== 'collab') {
      addLog("Orchestrator", "Layout change detected (Target Territory ➔ Europe). Loop triggered back to Sourcing analysis.");
      addLog("IP Counsel Agent", "Recheck Loop: Verifying rights for region: Europe...");
      addLog("mcp-legal-contracts", "scan_global_exclusivity_clauses: Exclusivity check passed for Europe.");
      
      setFlowState('resolved');
      setChatLogs(prev => [
        ...prev, 
        "✅ Exclusivity resolved. Sourcing capacity controls unlocked. Define volume limits."
      ]);
    } else if (flowState === 'resolved' && targetMarket === 'North America' && activeScenario !== 'collab') {
      setFlowState('warning');
      addLog("IP Counsel Agent", "WARNING: Exclusive conflict re-engaged in North America.");
    }
  }, [targetMarket, flowState, activeScenario]);

  // Handle production volume changes and guardrails
  const handleVolumeChange = (val) => {
    const parsedVal = parseInt(val);
    setProductionVolume(parsedVal);
    
    if (parsedVal > 25000) {
      setShowSliderGuardrail(true);
      setProductionVolume(25000);
      addLog("Orchestrator", `Volume cap rule validation failed for ${parsedVal}. Max cap is 25k.`);
      addLog("mcp-procurement-ledger", "check_sku_volume_caps: Blocked. Volume cap exceeded.");
      
      setTimeout(() => {
        setShowSliderGuardrail(false);
        setShowAddendumSuccess(true);
        addLog("Orchestrator", "Addendum SC-7798-EU generated successfully for 15,000 units with secondary manufacturing partner.");
      }, 2500);
    }
  };

  // ---- Live backend audit (real ADK orchestrator via /api/audit) ----
  // liveStatus: 'idle' | 'running' | 'hitl' | 'done' | 'error'
  const [liveStatus, setLiveStatus] = useState('idle');
  const [liveResult, setLiveResult] = useState(null);
  const [liveError, setLiveError] = useState(null);
  const [liveSession, setLiveSession] = useState(null);
  const [liveHitlMessage, setLiveHitlMessage] = useState(null);
  // The vendor image LINK the orchestrator audits (gs:// or https). brand_style's
  // asset-source gate + vision extraction key off this.
  const [imageUri, setImageUri] = useState('gs://vibeflix-approved-assets/vendor_request.jpg');

  const applyLiveResponse = (data) => {
    if (data && data.hitl_required) {
      setLiveSession(data.session_id);
      setLiveHitlMessage(data.message);
      setLiveStatus('hitl');
    } else {
      setLiveResult(data);
      setLiveStatus('done');
      addLog("Orchestrator", "Live backend audit returned a2ui_payload. Rendering agent-painted canvas.");
    }
  };

  const runLiveAudit = async () => {
    setLiveStatus('running');
    setLiveError(null);
    setLiveResult(null);
    setLiveHitlMessage(null);
    setLiveSession(null);
    addLog("Orchestrator", `POST ${API_BASE}/api/audit — image_uri=${imageUri}, market=${targetMarket}, volume=${productionVolume}`);
    try {
      const res = await fetch(`${API_BASE}/api/audit`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          image_path: mockupFile,
          image_uri: imageUri,
          target_market: targetMarket,
          volume: productionVolume,
        }),
      });
      if (!res.ok) throw new Error(`Backend responded ${res.status}: ${await res.text()}`);
      applyLiveResponse(await res.json());
    } catch (err) {
      setLiveError(String(err.message || err));
      setLiveStatus('error');
      addLog("Orchestrator", `Live audit failed (backend offline?): ${err.message || err}`);
    }
  };

  const resolveLiveHitl = async (choice) => {
    setLiveStatus('running');
    addLog("Orchestrator", `POST ${API_BASE}/api/audit/resume — sourcing override choice "${choice}"`);
    try {
      const res = await fetch(`${API_BASE}/api/audit/resume`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: liveSession, choice }),
      });
      if (!res.ok) throw new Error(`Backend responded ${res.status}: ${await res.text()}`);
      applyLiveResponse(await res.json());
    } catch (err) {
      setLiveError(String(err.message || err));
      setLiveStatus('error');
    }
  };

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
            <div style={{ display: 'grid', gridTemplateColumns: '1.2fr 1fr', gap: '1.5rem' }}>
              
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
                    Instead of sequential human reviews, the <strong>Sourcing Orchestrator</strong> routes packaging design mockups and volume orders to three domain compliance agents running concurrently — and Vendor &amp; Licensing hands off to a <strong>Legal Clearance agent</strong>:
                  </p>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.6rem', marginTop: '0.5rem' }}>
                    <div style={{ background: 'var(--bg-secondary)', border: '1px solid var(--glass-border)', padding: '0.5rem', borderRadius: '4px', fontSize: '0.75rem' }}>
                      <strong style={{ color: '#1a73e8', display: 'block', marginBottom: '0.2rem' }}>🎨 Style Agent</strong>
                      Uses CV tool models to verify fonts, layout parameters, and swatch compliance instantly.
                    </div>
                    <div style={{ background: 'var(--bg-secondary)', border: '1px solid var(--glass-border)', padding: '0.5rem', borderRadius: '4px', fontSize: '0.75rem' }}>
                      <strong style={{ color: '#ea4335', display: 'block', marginBottom: '0.2rem' }}>⚖️ Vendor &amp; Licensing</strong>
                      Scans exclusivity + trademark, recommends eligible vendors, and onboards new ones.
                    </div>
                    <div style={{ background: 'var(--bg-secondary)', border: '1px solid var(--glass-border)', padding: '0.5rem', borderRadius: '4px', fontSize: '0.75rem' }}>
                      <strong style={{ color: '#c9922e', display: 'block', marginBottom: '0.2rem' }}>💰 Deal Pricing</strong>
                      Reconciles the vendor's agreed total consideration (royalty + advance + MG) against the licensor rate card via an evaluate→validate→iterate loop.
                    </div>
                    <div style={{ background: 'var(--bg-secondary)', border: '1px solid var(--accent-purple)', padding: '0.5rem', borderRadius: '4px', fontSize: '0.75rem' }}>
                      <strong style={{ color: 'var(--accent-purple)', display: 'block', marginBottom: '0.2rem' }}>⚖️ Legal Clearance</strong>
                      A standalone agent — in this demo Vendor &amp; Licensing hands off to it (any agent could). Executes the licensing contract and <strong>RAG-discovers</strong> its undefined process from scattered internal docs.
                    </div>
                  </div>
                </div>

              </div>

              {/* Right Column: Animated Workflow Flowchart */}
              <div className="canvas-panel" style={{ justifyContent: 'space-between' }}>
                <div>
                  <h3 className="panel-title" style={{ fontSize: '0.95rem', borderBottom: '1px solid var(--glass-border)', paddingBottom: '0.5rem' }}>
                    <RefreshCw size={16} className="spin" style={{ animation: 'spin 12s linear infinite', color: 'var(--color-success)' }} />
                    Compliance Lifespans: Visual Workflow
                  </h3>
                  <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: '0.75rem' }}>
                    Hover over nodes to trace how information streams dynamically in the simulator mesh. Blue flow dash offset shows active auditing path.
                  </p>
                </div>

                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', width: '100%', margin: '0.5rem 0' }}>
                  {/* Inserted SVG Workflow Diagram */}
                  <svg width="100%" height="230" viewBox="0 0 820 270" style={{ background: 'var(--bg-secondary)', borderRadius: '8px', border: '1px solid var(--glass-border)', padding: '0.5rem' }}>
                    <defs>
                      <marker id="arrow" viewBox="0 0 10 10" refX="6" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
                        <path d="M 0 2 L 10 5 L 0 8 z" fill="var(--text-muted)" />
                      </marker>
                    </defs>

                    {/* edges (solid) */}
                    <path d="M 102 134 L 165 35" stroke="var(--glass-border)" strokeWidth="1.5" fill="none" markerEnd="url(#arrow)" />
                    <path d="M 102 134 L 165 102" stroke="var(--glass-border)" strokeWidth="1.5" fill="none" markerEnd="url(#arrow)" />
                    <path d="M 102 134 L 165 200" stroke="var(--glass-border)" strokeWidth="1.5" fill="none" markerEnd="url(#arrow)" />
                    <path d="M 313 35 L 420 119" stroke="var(--glass-border)" strokeWidth="1.5" fill="none" markerEnd="url(#arrow)" />
                    <path d="M 313 102 L 420 119" stroke="var(--glass-border)" strokeWidth="1.5" fill="none" markerEnd="url(#arrow)" />
                    <path d="M 313 200 L 420 119" stroke="var(--glass-border)" strokeWidth="1.5" fill="none" markerEnd="url(#arrow)" />
                    <path d="M 538 119 L 578 119" stroke="var(--glass-border)" strokeWidth="1.5" fill="none" markerEnd="url(#arrow)" />
                    <path d="M 686 119 L 718 119" stroke="var(--glass-border)" strokeWidth="1.5" fill="none" markerEnd="url(#arrow)" />
                    {/* legal hand-off from Vendor & Licensing (dashed) */}
                    <path d="M 245 122 L 258 128" stroke="var(--accent-purple)" strokeWidth="1.5" fill="none" strokeDasharray="3 3" markerEnd="url(#arrow)" />

                    {/* animated active flow */}
                    <path d="M 102 134 L 165 102" stroke="#1a73e8" strokeWidth="1.5" fill="none" strokeDasharray="6 6" className="animated-flow" />
                    <path d="M 313 102 L 420 119" stroke="#34a853" strokeWidth="1.5" fill="none" strokeDasharray="6 6" className="animated-flow" />
                    <path d="M 538 119 L 578 119" stroke="#34a853" strokeWidth="1.5" fill="none" strokeDasharray="6 6" className="animated-flow" />
                    <path d="M 686 119 L 718 119" stroke="#34a853" strokeWidth="1.5" fill="none" strokeDasharray="6 6" className="animated-flow" />

                    {/* Ingestion */}
                    <g transform="translate(12, 105)">
                      <rect width="90" height="58" rx="6" fill="var(--bg-card)" stroke="var(--accent-purple)" strokeWidth="2" />
                      <text x="45" y="25" fill="var(--text-dark)" fontSize="8.5" fontWeight="bold" textAnchor="middle">Mockup Ingestion</text>
                      <text x="45" y="39" fill="var(--accent-purple)" fontSize="7.5" fontWeight="bold" textAnchor="middle">Ingest assets</text>
                      <text x="45" y="51" fill="var(--text-muted)" fontSize="7" textAnchor="middle">Computer Vision</text>
                    </g>

                    {/* Brand Style */}
                    <g transform="translate(165, 15)">
                      <rect width="148" height="40" rx="6" fill="var(--bg-card)" stroke="var(--glass-border)" strokeWidth="1" />
                      <text x="10" y="18" fill="var(--text-dark)" fontSize="9" fontWeight="bold">🎨 Brand Style</text>
                      <text x="10" y="32" fill="#1a73e8" fontSize="7" fontWeight="bold">fonts · swatches · medium</text>
                      <circle cx="138" cy="12" r="3.5" fill="#34a853" />
                    </g>

                    {/* Vendor & Licensing */}
                    <g transform="translate(165, 82)">
                      <rect width="148" height="40" rx="6" fill="var(--bg-card)" stroke="var(--glass-border)" strokeWidth="1" />
                      <text x="10" y="18" fill="var(--text-dark)" fontSize="9" fontWeight="bold">⚖️ Vendor &amp; Licensing</text>
                      <text x="10" y="32" fill="#ea4335" fontSize="7" fontWeight="bold">exclusivity · trademark · vendors</text>
                      <circle cx="138" cy="12" r="3.5" fill="#fbbc05" />
                    </g>

                    {/* Legal Clearance — hangs off Vendor & Licensing */}
                    <g transform="translate(198, 128)">
                      <rect width="120" height="38" rx="6" fill="var(--bg-card)" stroke="var(--accent-purple)" strokeWidth="1.5" strokeDasharray="4 3" />
                      <text x="10" y="17" fill="var(--text-dark)" fontSize="8.5" fontWeight="bold">⚖️ Legal Clearance</text>
                      <text x="10" y="30" fill="var(--accent-purple)" fontSize="6.5" fontWeight="bold">RAG · executes contract (LC-#)</text>
                    </g>

                    {/* Deal Pricing */}
                    <g transform="translate(165, 180)">
                      <rect width="148" height="40" rx="6" fill="var(--bg-card)" stroke="var(--glass-border)" strokeWidth="1" />
                      <text x="10" y="18" fill="var(--text-dark)" fontSize="9" fontWeight="bold">💰 Deal Pricing</text>
                      <text x="10" y="32" fill="#c9922e" fontSize="7" fontWeight="bold">royalty · advance · MG</text>
                      <circle cx="138" cy="12" r="3.5" fill="#34a853" />
                    </g>

                    {/* Orchestrator */}
                    <g transform="translate(420, 90)">
                      <rect width="118" height="58" rx="6" fill="var(--bg-card)" stroke="var(--color-warning)" strokeWidth="2" />
                      <text x="59" y="22" fill="var(--text-dark)" fontSize="9" fontWeight="bold" textAnchor="middle">Orchestrator</text>
                      <text x="59" y="37" fill="var(--color-warning)" fontSize="7.5" fontWeight="bold" textAnchor="middle">Remediation + HITL</text>
                      <text x="59" y="50" fill="var(--text-muted)" fontSize="7" textAnchor="middle">A / B override</text>
                    </g>

                    {/* UI Renderer (A2UI) */}
                    <g transform="translate(578, 90)">
                      <rect width="108" height="58" rx="6" fill="var(--bg-card)" stroke="var(--accent-blue)" strokeWidth="2" />
                      <text x="54" y="22" fill="var(--text-dark)" fontSize="9" fontWeight="bold" textAnchor="middle">UI Renderer</text>
                      <text x="54" y="37" fill="var(--accent-blue)" fontSize="7.5" fontWeight="bold" textAnchor="middle">A2UI panels</text>
                      <text x="54" y="50" fill="var(--text-muted)" fontSize="7" textAnchor="middle">reports → surface</text>
                    </g>

                    {/* Sourcing */}
                    <g transform="translate(718, 90)">
                      <rect width="88" height="58" rx="6" fill="var(--bg-card)" stroke="var(--color-success)" strokeWidth="2" />
                      <text x="44" y="22" fill="var(--text-dark)" fontSize="9" fontWeight="bold" textAnchor="middle">Sourcing</text>
                      <text x="44" y="37" fill="var(--color-success)" fontSize="7.5" fontWeight="bold" textAnchor="middle">Contracts</text>
                      <text x="44" y="50" fill="var(--text-muted)" fontSize="7" textAnchor="middle">PO dispatched</text>
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

            </div>

            {/* Sourcing Approvals & Dispatch History Log Card */}
            <div className="canvas-panel" style={{ padding: '1.25rem' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid var(--glass-border)', paddingBottom: '0.75rem', marginBottom: '1rem', flexWrap: 'wrap', gap: '0.5rem' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  <span style={{ fontSize: '1.2rem' }}>📜</span>
                  <h3 className="panel-title" style={{ fontSize: '0.95rem', margin: 0 }}>Sourcing Compliance Approvals & Dispatch History</h3>
                </div>
                
                {/* Filter buttons */}
                <div style={{ display: 'flex', gap: '0.4rem' }}>
                  {['ALL', 'APPROVED', 'REJECTED'].map((filter) => (
                    <button
                      key={filter}
                      className={`preset-btn ${historyFilter === filter ? 'primary' : ''}`}
                      onClick={() => setHistoryFilter(filter)}
                      style={{ 
                        padding: '0.25rem 0.5rem', 
                        fontSize: '0.7rem',
                        cursor: 'pointer'
                      }}
                    >
                      {filter}
                    </button>
                  ))}
                </div>
              </div>

              {/* Description */}
              <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: '1rem', marginTop: 0 }}>
                This ledger records the historical pipeline audits finalized in the interactive simulator or ingested from production runs. Click any record to expand and view the complete step-by-step agent workflow routing path.
              </p>

              {/* History List */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
                {approvalHistory
                  .filter(item => {
                    if (historyFilter === 'ALL') return true;
                    if (historyFilter === 'APPROVED') return item.status.startsWith('APPROVED');
                    if (historyFilter === 'REJECTED') return item.status === 'REJECTED';
                    return true;
                  })
                  .map((item) => {
                    const isExpanded = expandedItemId === item.id;
                    const isApproved = item.status.startsWith('APPROVED');
                    return (
                      <div 
                        key={item.id} 
                        style={{ 
                          background: 'var(--bg-secondary)', 
                          border: '1px solid',
                          borderColor: isExpanded 
                            ? (isApproved ? 'var(--color-success)' : 'var(--color-danger)') 
                            : 'var(--glass-border)',
                          borderRadius: '0.5rem',
                          padding: '0.75rem 1rem',
                          cursor: 'pointer',
                          transition: 'all 0.2s ease',
                          boxShadow: isExpanded ? '0 4px 12px rgba(0,0,0,0.06)' : 'none'
                        }}
                        onClick={() => setExpandedItemId(isExpanded ? null : item.id)}
                      >
                        {/* Summary Header */}
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.5rem' }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                            <span style={{ 
                              fontFamily: 'monospace', 
                              fontSize: '0.75rem', 
                              background: 'var(--bg-tertiary)', 
                              padding: '2px 6px', 
                              borderRadius: '4px',
                              border: '1px solid var(--glass-border)',
                              color: 'var(--text-dark)',
                              fontWeight: 'bold'
                            }}>
                              {item.id}
                            </span>
                            <span style={{ fontSize: '0.85rem', fontWeight: 700, color: 'var(--text-dark)' }}>
                              {item.asset}
                            </span>
                            <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>
                              ({item.category})
                            </span>
                          </div>
                          
                          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                            <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>
                              {item.timestamp}
                            </span>
                            <span style={{ 
                              fontSize: '0.65rem', 
                              fontWeight: 800, 
                              padding: '2px 6px', 
                              borderRadius: '3px',
                              background: isApproved ? 'rgba(16, 185, 129, 0.1)' : 'rgba(239, 68, 68, 0.1)',
                              color: isApproved ? 'var(--color-success)' : 'var(--color-danger)',
                              border: '1px solid',
                              borderColor: isApproved ? 'rgba(16, 185, 129, 0.2)' : 'rgba(239, 68, 68, 0.2)'
                            }}>
                              {item.status}
                            </span>
                          </div>
                        </div>

                        {/* Sub-details (Volume & Market) */}
                        <div style={{ display: 'flex', gap: '1.5rem', marginTop: '0.4rem', fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                          <div>
                            <strong>Market Route:</strong> <span style={{ color: 'var(--text-dark)' }}>{item.market}</span>
                          </div>
                          <div>
                            <strong>Sourcing Capacity:</strong> <span style={{ color: 'var(--text-dark)' }}>{item.volume.toLocaleString()} units</span>
                          </div>
                        </div>

                        {/* Collapsed view: Show simple horizontal path preview */}
                        {!isExpanded && (
                          <div style={{ 
                            display: 'flex', 
                            alignItems: 'center', 
                            gap: '0.4rem', 
                            flexWrap: 'wrap', 
                            marginTop: '0.75rem',
                            paddingTop: '0.75rem',
                            borderTop: '1px dashed var(--glass-border)' 
                          }}>
                            <span style={{ fontSize: '0.65rem', fontWeight: 'bold', textTransform: 'uppercase', color: 'var(--text-muted)' }}>Workflow Path:</span>
                            {item.path.map((step, idx) => (
                              <React.Fragment key={idx}>
                                {idx > 0 && <span style={{ color: 'var(--text-muted)', fontSize: '0.65rem' }}>➔</span>}
                                <div style={{ 
                                  display: 'flex', 
                                  alignItems: 'center', 
                                  gap: '0.2rem', 
                                  color: step.status === 'pass' ? 'var(--color-success)' : (step.status === 'warning' ? 'var(--color-warning)' : 'var(--color-danger)'),
                                  fontSize: '0.65rem',
                                  fontWeight: 600
                                }}>
                                  {step.status === 'pass' && <CheckCircle size={8} />}
                                  {step.status === 'warning' && <AlertTriangle size={8} />}
                                  {step.status === 'fail' && <XCircle size={8} />}
                                  <span>{step.name}</span>
                                </div>
                              </React.Fragment>
                            ))}
                            <span style={{ marginLeft: 'auto', fontSize: '0.65rem', color: 'var(--accent-blue)' }}>Click to view details ➔</span>
                          </div>
                        )}

                        {/* Expanded view: Show vertical stepper with detailed audits */}
                        {isExpanded && (
                          <div style={{ 
                            marginTop: '1rem', 
                            paddingTop: '1rem', 
                            borderTop: '1px solid var(--glass-border)',
                            animation: 'slideIn 0.25s ease-out'
                          }} onClick={(e) => e.stopPropagation() /* Prevent double toggle when clicking inside */}>
                            <h4 style={{ fontSize: '0.75rem', textTransform: 'uppercase', color: 'var(--text-dark)', margin: '0 0 0.75rem 0', display: 'flex', alignItems: 'center', gap: '0.3rem' }}>
                              <GitBranch size={12} style={{ color: 'var(--accent-purple)' }} /> Complete Audit Workflow Trace Path
                            </h4>

                            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', position: 'relative', paddingLeft: '1.25rem' }}>
                              {/* Vertical Line Connector */}
                              <div style={{ 
                                position: 'absolute', 
                                left: '5px', 
                                top: '8px', 
                                bottom: '8px', 
                                width: '2px', 
                                background: 'var(--glass-border)',
                                zIndex: 0
                              }} />

                              {item.path.map((step, idx) => (
                                <div key={idx} style={{ display: 'flex', gap: '0.75rem', position: 'relative', zIndex: 1 }}>
                                  {/* Step Dot */}
                                  <div style={{ 
                                    width: '12px', 
                                    height: '12px', 
                                    borderRadius: '50%', 
                                    background: step.status === 'pass' ? 'var(--color-success)' : (step.status === 'warning' ? 'var(--color-warning)' : 'var(--color-danger)'),
                                    position: 'absolute',
                                    left: '-20px',
                                    top: '3px',
                                    border: '2px solid var(--bg-secondary)',
                                    boxShadow: '0 0 0 2px var(--bg-secondary)'
                                  }} />

                                  <div style={{ display: 'flex', flexDirection: 'column', gap: '0.15rem' }}>
                                    <span style={{ fontSize: '0.75rem', fontWeight: 'bold', color: 'var(--text-dark)' }}>
                                      {step.name}
                                    </span>
                                    <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>
                                      {step.detail}
                                    </span>
                                  </div>

                                  {/* Step Status Badge */}
                                  <span style={{ 
                                    marginLeft: 'auto',
                                    fontSize: '0.6rem', 
                                    fontWeight: 700, 
                                    padding: '1px 4px', 
                                    borderRadius: '3px',
                                    height: 'fit-content',
                                    background: step.status === 'pass' ? 'rgba(16, 185, 129, 0.06)' : (step.status === 'warning' ? 'rgba(245, 158, 11, 0.06)' : 'rgba(239, 68, 68, 0.06)'),
                                    color: step.status === 'pass' ? 'var(--color-success)' : (step.status === 'warning' ? 'var(--color-warning)' : 'var(--color-danger)'),
                                    border: '1px solid',
                                    borderColor: step.status === 'pass' ? 'rgba(16, 185, 129, 0.15)' : (step.status === 'warning' ? 'rgba(245, 158, 11, 0.15)' : 'rgba(239, 68, 68, 0.15)')
                                  }}>
                                    {step.status === 'pass' ? 'CLEARED' : (step.status === 'warning' ? 'OVERRIDDEN' : 'BLOCKED')}
                                  </span>
                                </div>
                              ))}
                            </div>

                            <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '1rem' }}>
                              <button 
                                className="preset-btn" 
                                style={{ padding: '0.2rem 0.5rem', fontSize: '0.65rem', cursor: 'pointer' }}
                                onClick={() => setExpandedItemId(null)}
                              >
                                Close Details
                              </button>
                            </div>
                          </div>
                        )}
                      </div>
                    );
                  })}
              </div>
            </div>

          </div>
        )}

        {activeTab === 'canvas' && <ChatAudit />}

        {activeTab === 'history' && (
          <div style={{ width: '100%', height: '100%', overflowY: 'auto' }}>
            <AuditHistory />
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
