import React, { useState, useEffect, useRef } from 'react';
import { 
  Upload, Send, Shield, AlertTriangle, AlertCircle, CheckCircle, 
  MapPin, Sliders, Play, RefreshCw, BarChart2, Terminal, Info,
  ArrowRight, GitBranch, Layers, Check, Database, RefreshCw as LoopIcon, HelpCircle, XCircle, MessagesSquare
} from 'lucide-react';

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
              <Sliders size={14} style={{ marginRight: '4px', display: 'inline-block', verticalAlign: 'middle' }} /> Interactive Simulator UI
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

      {/* Front & Top User Entry Dashboard Section (Only shown in Tab 1 / Simulator UI) */}
      {activeTab === 'canvas' && (
        <section className="top-user-entry">
          <div className="entry-row" style={{ flexWrap: 'wrap', gap: '0.75rem' }}>
            
            {/* Preset Scenario Selectors Center */}
            <div style={{ display: 'flex', gap: '0.4rem', flexWrap: 'wrap' }}>
              <button 
                className={`preset-btn ${activeScenario === 'clean' ? 'primary' : ''}`} 
                onClick={() => triggerScenario('clean')}
                disabled={flowState === 'uploading' || flowState === 'negotiating'}
                title="Scenario 1: Clean release with zero guidelines infractions."
              >
                🟢 Scenario 1: Clean (Pass)
              </button>
              <button 
                className={`preset-btn ${activeScenario === 'collab' ? 'primary' : ''}`} 
                onClick={() => triggerScenario('collab')}
                disabled={flowState === 'uploading' || flowState === 'negotiating'}
                title="Scenario 2: Exclusivity conflicts resolved autonomously via inter-agent negotiation."
              >
                🟡 Scenario 2: Agent Mesh (Collab)
              </button>
              <button 
                className={`preset-btn ${activeScenario === 'hitl' ? 'primary' : ''}`} 
                onClick={() => triggerScenario('hitl')}
                disabled={flowState === 'uploading' || flowState === 'negotiating'}
                title="Scenario 3: Capped limits requiring Human-in-the-loop overrides."
              >
                🔵 Scenario 3: Overrides (HITL)
              </button>
              <button 
                className={`preset-btn ${activeScenario === 'fail' ? 'primary' : ''}`} 
                onClick={() => triggerScenario('fail')}
                disabled={flowState === 'uploading' || flowState === 'negotiating'}
                title="Scenario 4: Character script leak blocks releases completely."
              >
                🔴 Scenario 4: Spoilers (Fail)
              </button>
              
              <span style={{ borderLeft: '1px solid var(--glass-border)', margin: '0 0.5rem' }}></span>
              
              <button 
                className="preset-btn"
                onClick={() => {
                  setFlowState('idle');
                  setActiveScenario(null);
                  setTargetMarket('North America');
                  setProductionVolume(15000);
                  setShowSliderGuardrail(false);
                  setShowAddendumSuccess(false);
                  setChatLogs(["System active. Workspace reset. Ready for kickoff..."]);
                  setNegotiationLogs([]);
                  addLog("Orchestrator", "Workspace variables reset.");
                  setCurrentRunLogged(false);
                }}
              >
                🔄 Reset Canvas
              </button>
            </div>

            {/* Prompt input field */}
            <form onSubmit={handlePromptSubmit} className="prompt-bar-container" style={{ minWidth: '300px' }}>
              <input 
                type="text"
                className="top-textarea"
                placeholder="Or type prompt command (e.g. 'run scenario 2')..."
                value={inputText}
                onChange={(e) => setInputText(e.target.value)}
              />
              <button type="submit" className="icon-btn" style={{ background: 'transparent', border: 'none', color: 'var(--text-muted)' }}>
                <Send size={16} />
              </button>
            </form>
            
          </div>

          {/* Action log feed row */}
          <div style={{ display: 'flex', gap: '0.5rem', overflowX: 'auto', padding: '0.2rem 0' }}>
            {chatLogs.slice(-2).map((log, idx) => (
              <div key={idx} style={{ background: 'var(--bg-tertiary)', border: '1px solid var(--glass-border)', padding: '0.35rem 0.75rem', borderRadius: '0.35rem', fontSize: '0.75rem', display: 'flex', alignItems: 'center', gap: '0.4rem', whiteSpace: 'nowrap' }}>
                <Info size={12} style={{ color: 'var(--accent-purple)' }} />
                <span>{log}</span>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Main Workspace Body */}
      <div className="workspace-body" style={{ gridTemplateColumns: activeTab === 'canvas' ? '1fr 1.2fr' : '1fr' }}>
        
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
                The Vibeflix Merchandising ecosystem handles the global sourcing of licensed consumer items (vinyl figures, toy prototypes, apparel). To prevent severe downstream errors—ranging from trademark exclusions and copyright lawsuits to storyline canon script leaks—this workspace coordinates and executes real-time multi-agent compliance audits prior to placing manufacturing orders.
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
                      <strong style={{ color: 'var(--color-danger)' }}>3. Canon Storyline Spoiler Leaks:</strong> Sourcing figurines depicting characters in unreleased plotlines (e.g. spoiler details on box) ruins fan experiences.
                    </div>
                    <div style={{ fontSize: '0.8rem' }}>
                      <strong style={{ color: 'var(--color-danger)' }}>4. Sourcing Overproduction Limits:</strong> Ordering volume past approved caps without authorized overrides breaches master manufacturing agreements.
                    </div>
                  </div>
                </div>

                {/* ADK 2.0 Mesh Coordination Card */}
                <div className="canvas-panel" style={{ flex: 1 }}>
                  <h3 className="panel-title" style={{ fontSize: '0.95rem', borderBottom: '1px solid var(--glass-border)', paddingBottom: '0.5rem' }}>
                    <GitBranch size={16} style={{ color: 'var(--accent-blue)' }} /> Parallel Multi-Agent Auditing Mesh (ADK 2.0)
                  </h3>
                  <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                    Instead of sequential human reviews, the <strong>Sourcing Orchestrator</strong> routes packaging design mockups and volume orders to three autonomous compliance agents running concurrently:
                  </p>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '0.75rem', marginTop: '0.5rem' }}>
                    <div style={{ background: 'var(--bg-secondary)', border: '1px solid var(--glass-border)', padding: '0.5rem', borderRadius: '4px', fontSize: '0.75rem' }}>
                      <strong style={{ color: '#1a73e8', display: 'block', marginBottom: '0.2rem' }}>🎨 Style Agent</strong>
                      Uses CV tool models to verify fonts, layout parameters, and swatch compliance instantly.
                    </div>
                    <div style={{ background: 'var(--bg-secondary)', border: '1px solid var(--glass-border)', padding: '0.5rem', borderRadius: '4px', fontSize: '0.75rem' }}>
                      <strong style={{ color: '#ea4335', display: 'block', marginBottom: '0.2rem' }}>⚖️ Legal IP Agent</strong>
                      Scans exclusivity matrices and region contracts to prevent infringement conflicts.
                    </div>
                    <div style={{ background: 'var(--bg-secondary)', border: '1px solid var(--glass-border)', padding: '0.5rem', borderRadius: '4px', fontSize: '0.75rem' }}>
                      <strong style={{ color: '#34a853', display: 'block', marginBottom: '0.2rem' }}>🎬 Storyline Agent</strong>
                      Audits design assets against canonical scripts and active release timeline embargoes.
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
                  <svg width="100%" height="210" viewBox="0 0 800 210" style={{ background: 'var(--bg-secondary)', borderRadius: '8px', border: '1px solid var(--glass-border)', padding: '0.5rem' }}>
                    <defs>
                      <marker id="arrow" viewBox="0 0 10 10" refX="6" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
                        <path d="M 0 2 L 10 5 L 0 8 z" fill="var(--text-muted)" />
                      </marker>
                    </defs>

                    {/* Background paths */}
                    <path d="M 120 105 L 250 50" stroke="var(--glass-border)" strokeWidth="2" fill="none" markerEnd="url(#arrow)" />
                    <path d="M 120 105 L 250 105" stroke="var(--glass-border)" strokeWidth="2" fill="none" markerEnd="url(#arrow)" />
                    <path d="M 120 105 L 250 160" stroke="var(--glass-border)" strokeWidth="2" fill="none" markerEnd="url(#arrow)" />

                    <path d="M 390 50 L 520 105" stroke="var(--glass-border)" strokeWidth="2" fill="none" markerEnd="url(#arrow)" />
                    <path d="M 390 105 L 520 105" stroke="var(--glass-border)" strokeWidth="2" fill="none" markerEnd="url(#arrow)" />
                    <path d="M 390 160 L 520 105" stroke="var(--glass-border)" strokeWidth="2" fill="none" markerEnd="url(#arrow)" />

                    <path d="M 640 105 L 710 105" stroke="var(--glass-border)" strokeWidth="2" fill="none" markerEnd="url(#arrow)" />

                    {/* Dotted paths representing active flow */}
                    <path d="M 120 105 L 250 50" stroke="#1a73e8" strokeWidth="2" fill="none" strokeDasharray="6 6" className="animated-flow" />
                    <path d="M 120 105 L 250 105" stroke="#1a73e8" strokeWidth="2" fill="none" strokeDasharray="6 6" className="animated-flow" />
                    <path d="M 120 105 L 250 160" stroke="#1a73e8" strokeWidth="2" fill="none" strokeDasharray="6 6" className="animated-flow" />

                    <path d="M 390 50 L 520 105" stroke="#34a853" strokeWidth="2" fill="none" strokeDasharray="6 6" className="animated-flow" />
                    <path d="M 390 105 L 520 105" stroke="#34a853" strokeWidth="2" fill="none" strokeDasharray="6 6" className="animated-flow" />
                    <path d="M 390 160 L 520 105" stroke="#34a853" strokeWidth="2" fill="none" strokeDasharray="6 6" className="animated-flow" />

                    <path d="M 640 105 L 710 105" stroke="#34a853" strokeWidth="2" fill="none" strokeDasharray="6 6" className="animated-flow" />

                    {/* Node 1: Ingestion */}
                    <g transform="translate(30, 70)">
                      <rect width="90" height="70" rx="6" fill="var(--bg-card)" stroke="var(--accent-purple)" strokeWidth="2" style={{ filter: 'drop-shadow(0 2px 4px rgba(0,0,0,0.08))' }} />
                      <text x="45" y="28" fill="var(--text-dark)" fontSize="9" fontWeight="bold" textAnchor="middle">Mockup Ingestion</text>
                      <text x="45" y="44" fill="var(--accent-purple)" fontSize="8" fontWeight="bold" textAnchor="middle">Ingest assets</text>
                      <text x="45" y="58" fill="var(--text-muted)" fontSize="7" textAnchor="middle">Computer Vision</text>
                    </g>

                    {/* Node 2A: Style Agent */}
                    <g transform="translate(250, 22)">
                      <rect width="140" height="46" rx="6" fill="var(--bg-card)" stroke="var(--glass-border)" strokeWidth="1" />
                      <text x="10" y="18" fill="var(--text-dark)" fontSize="9" fontWeight="bold">Brand Style Agent</text>
                      <text x="10" y="32" fill="#1a73e8" fontSize="7" fontWeight="bold">Verify fonts, hex swatches</text>
                      <circle cx="130" cy="23" r="4" fill="#34a853" />
                    </g>

                    {/* Node 2B: Legal IP */}
                    <g transform="translate(250, 82)">
                      <rect width="140" height="46" rx="6" fill="var(--bg-card)" stroke="var(--glass-border)" strokeWidth="1" />
                      <text x="10" y="18" fill="var(--text-dark)" fontSize="9" fontWeight="bold">Legal IP Agent</text>
                      <text x="10" y="32" fill="#ea4335" fontSize="7" fontWeight="bold">Territory & contracts checks</text>
                      <circle cx="130" cy="23" r="4" fill="#fbbc05" />
                    </g>

                    {/* Node 2C: Storyline Lore */}
                    <g transform="translate(250, 142)">
                      <rect width="140" height="46" rx="6" fill="var(--bg-card)" stroke="var(--glass-border)" strokeWidth="1" />
                      <text x="10" y="18" fill="var(--text-dark)" fontSize="9" fontWeight="bold">Storyline Lore Agent</text>
                      <text x="10" y="32" fill="#34a853" fontSize="7" fontWeight="bold">Script spoiler leak checks</text>
                      <circle cx="130" cy="23" r="4" fill="#34a853" />
                    </g>

                    {/* Node 3: Orchestrator & HITL Decision */}
                    <g transform="translate(520, 70)">
                      <rect width="120" height="70" rx="6" fill="var(--bg-card)" stroke="var(--color-warning)" strokeWidth="2" />
                      <text x="60" y="24" fill="var(--text-dark)" fontSize="9" fontWeight="bold" textAnchor="middle">Remediation Mesh</text>
                      <text x="60" y="40" fill="var(--color-warning)" fontSize="8" fontWeight="bold" textAnchor="middle">& HITL Decision</text>
                      <text x="60" y="56" fill="var(--text-muted)" fontSize="7" textAnchor="middle" >Option A / B override</text>
                    </g>

                    {/* Node 4: Sourcing Contract Dispatch */}
                    <g transform="translate(710, 70)">
                      <rect width="80" height="70" rx="6" fill="var(--bg-card)" stroke="var(--color-success)" strokeWidth="2" />
                      <text x="40" y="28" fill="var(--text-dark)" fontSize="10" fontWeight="bold" textAnchor="middle">Sourcing</text>
                      <text x="40" y="44" fill="var(--color-success)" fontSize="8" fontWeight="bold" textAnchor="middle">Contracts Issued</text>
                      <text x="40" y="58" fill="var(--text-muted)" fontSize="7" textAnchor="middle">PO Dispatched</text>
                    </g>
                  </svg>
                </div>

                <div style={{ display: 'flex', justifyContent: 'space-between', background: 'var(--bg-secondary)', border: '1px solid var(--glass-border)', padding: '0.6rem 0.85rem', borderRadius: '6px' }}>
                  <span style={{ fontSize: '0.75rem', fontWeight: 'bold' }}>💻 System Ready to Run:</span>
                  <span style={{ fontSize: '0.75rem', color: 'var(--accent-blue)', cursor: 'pointer', fontWeight: 'bold' }} onClick={() => setActiveTab('canvas')}>
                    Go to Interactive Simulator UI ➔
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

        {activeTab === 'canvas' && (
          <>
            {/* Left Column: Adaptive Remediation & Viewport */}
            <div className="workspace-column">
              
              {/* Mockup Box front panel Viewport */}
              <div className="canvas-panel">
                <h3 className="panel-title">
                  <span>🖼️ Prototype Box Viewport</span>
                </h3>
                
                <div className="mockup-display">
                  {flowState === 'idle' ? (
                    <div className="mockup-placeholder">
                      <Upload size={28} style={{ color: 'var(--accent-purple)' }} />
                      <div>
                        <p style={{ fontWeight: 600 }}>Mockup Packaging Display Panel</p>
                        <p style={{ fontSize: '0.75rem', marginTop: '0.2rem', color: 'var(--text-muted)' }}>
                          Click a Preset Scenario button at the top to ingest mockup box designs
                        </p>
                      </div>
                    </div>
                  ) : (
                    <div style={{ position: 'relative', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '1rem', width: '100%' }}>
                      
                      <div style={{
                        width: '180px',
                        height: '240px',
                        background: 'var(--bg-card)',
                        border: '2px solid var(--glass-border)',
                        borderRadius: '8px',
                        position: 'relative',
                        display: 'flex',
                        flexDirection: 'column',
                        justifyContent: 'space-between',
                        padding: '0.85rem',
                        boxShadow: 'var(--box-shadow-premium)'
                      }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                          <span style={{ 
                            fontSize: '0.55rem', 
                            color: storylineStatus === 'Compliant' ? 'var(--color-success)' : 'var(--color-danger)', 
                            fontWeight: 800, 
                            border: '1px solid',
                            borderColor: storylineStatus === 'Compliant' ? 'var(--color-success)' : 'var(--color-danger)',
                            padding: '1px 3px', 
                            borderRadius: '3px' 
                          }}>
                            {storylineStatus === 'Compliant' ? 'STAR WARS' : 'BLOCKED'}
                          </span>
                          <span style={{ fontSize: '0.45rem', color: 'var(--text-muted)' }}>VINYL FIGURE</span>
                        </div>

                        <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0.4rem 0', background: 'var(--bg-tertiary)', borderRadius: '4px' }}>
                          <div style={{ fontSize: '2.5rem' }}>
                            {storylineStatus === 'Compliant' ? '👽' : '🎬'}
                          </div>
                        </div>

                        <div style={{ textAlign: 'center' }}>
                          <div style={{ fontSize: '0.45rem', color: 'var(--text-muted)' }}>POP SERIES #339</div>
                          <div style={{ 
                            fontSize: '0.8rem', 
                            fontWeight: 700, 
                            color: 'var(--text-dark)', 
                            fontFamily: fontStyle === 'SpaceGrotesk' ? 'SpaceGrotesk' : 'Outfit', 
                            letterSpacing: '0.05em' 
                          }}>
                            {storylineStatus === 'Compliant' ? 'THE CHILD' : 'SCRIPT LEAK'}
                          </div>
                        </div>

                        {/* Render active warning overlays when flowState is warning or negotiating */}
                        {['warning', 'negotiating'].includes(flowState) && (
                          <>
                            {/* Overlay for Font Typo (SpaceGrotesk) */}
                            {fontStyle === 'SpaceGrotesk' && (
                              <div 
                                className="warning-overlay-box" 
                                style={{ top: '190px', left: '10px', width: '160px', height: '28px' }}
                              >
                                <span className="warning-tooltip" style={{ top: '-25px' }}>Typo (SpaceGrotesk)</span>
                              </div>
                            )}

                            {/* Overlay for Exclusivity conflict (North America exclusivity locks) */}
                            {targetMarket === 'North America' && (
                              <div 
                                className="warning-overlay-box danger" 
                                style={{ top: '8px', left: '8px', width: '164px', height: '224px' }}
                              >
                                <span className="warning-tooltip" style={{ top: '80px' }}>NA Exclusive Block (Hasbro)</span>
                              </div>
                            )}

                            {/* Overlay for Lore Spoiler (Season 4 Lightsaber) */}
                            {storylineStatus === 'Spoiler Flagged' && (
                              <div 
                                className="warning-overlay-box danger" 
                                style={{ top: '40px', left: '10px', width: '160px', height: '110px' }}
                              >
                                <span className="warning-tooltip" style={{ top: '-25px', background: 'var(--color-danger)', color: 'white' }}>Lore Spoiler (S4 Lightsaber)</span>
                              </div>
                            )}
                          </>
                        )}

                        {flowState === 'failed' && (
                          <div 
                            className="warning-overlay-box danger" 
                            style={{ top: '8px', left: '8px', width: '164px', height: '224px' }}
                          >
                            <span className="warning-tooltip" style={{ top: '45%', background: 'var(--color-danger)', color: 'white' }}>LORE OVERRIDE (Lightsaber Spoiler)</span>
                          </div>
                        )}
                      </div>
                      
                    </div>
                  )}
                </div>
              </div>

              {/* Sequential Canvas Parameter Remediations */}
              <div className="canvas-panel">
                <h3 className="panel-title">
                  <span>⚡ Adaptive Remediation Canvas</span>
                </h3>

                {flowState === 'idle' && (
                  <div style={{ padding: '1rem 0', color: 'var(--text-muted)', fontSize: '0.8rem', textAlign: 'center' }}>
                    Select a Preset Scenario at the top to begin parameters verification.
                  </div>
                )}

                {flowState === 'uploading' && (
                  <div style={{ padding: '1rem 0', color: 'var(--text-muted)', fontSize: '0.8rem', textAlign: 'center', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.5rem' }}>
                    <RefreshCw size={14} className="spin" style={{ animation: 'spin 2s linear infinite' }} />
                    <span>Ingesting mockup box design...</span>
                  </div>
                )}

                {flowState === 'analyzing' && (
                  <div style={{ padding: '1rem 0', color: 'var(--text-muted)', fontSize: '0.8rem', textAlign: 'center', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.5rem' }}>
                    <RefreshCw size={14} className="spin" style={{ animation: 'spin 2s linear infinite' }} />
                    <span>Running Parallel Style, Legal Exclusivity & Storyline Checks...</span>
                  </div>
                )}

                {/* SCENARIO 2: ACTIVE DYNAMIC AGENT NEGOTIATION SCREEN */}
                {flowState === 'negotiating' && (
                  <div style={{ display: 'flex', flex1: 1, flexDirection: 'column', gap: '0.5rem', animation: 'slideIn 0.3s ease-out' }}>
                    <div className="risk-card warning" style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                      <MessagesSquare size={16} className="spin" style={{ animation: 'spin 4s linear infinite', color: 'var(--color-warning)' }} />
                      <div style={{ fontSize: '0.8rem', fontWeight: 'bold' }}>Active Mesh Negotiation Stream (No Human HITL)</div>
                    </div>
                    
                    <div style={{ 
                      background: 'var(--bg-secondary)', 
                      border: '1px solid var(--glass-border)', 
                      borderRadius: '0.5rem', 
                      padding: '0.75rem', 
                      display: 'flex', 
                      flexDirection: 'column', 
                      gap: '0.5rem',
                      maxHeight: '200px',
                      overflowY: 'auto'
                    }}>
                      {negotiationLogs.map((nLog, idx) => (
                        <div key={idx} style={{ fontSize: '0.75rem', borderBottom: '1px solid rgba(255,255,255,0.03)', paddingBottom: '0.25rem', animation: 'slideIn 0.3s' }}>
                          <span style={{ color: 'var(--accent-purple)', fontWeight: 'bold', marginRight: '0.4rem' }}>
                            {nLog.agent}:
                          </span>
                          <span style={{ color: 'var(--text-dark)' }}>{nLog.message}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {['warning', 'resolved', 'completed', 'failed'].includes(flowState) && (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                    
                    {/* INPUT 1: Target territory (rendered base on IP exclusivity checks) */}
                    {flowState === 'warning' && (
                      <div style={{ animation: 'slideIn 0.3s ease-out' }}>
                        <div className="risk-card">
                          <div className="risk-title text-danger">
                            <AlertCircle size={14} /> Legal Exclusivity Collision (North America)
                          </div>
                          <p className="risk-desc">
                            Hasbro Inc. holds exclusive Star Wars stylized vinyl figure rights in NA. Swapping territory clears this block.
                          </p>
                        </div>

                        <div className="form-group" style={{ border: '1px dashed var(--color-danger)', padding: '0.75rem', borderRadius: '0.4rem', background: 'rgba(var(--color-danger-rgb), 0.04)' }}>
                          <label className="form-label">
                            <span style={{ color: 'var(--color-danger)', fontWeight: 'bold' }}>⚠️ Next Remediation: Select Target Market</span>
                            <span style={{ color: 'var(--accent-blue)' }}>mcp-legal-contracts</span>
                          </label>
                          <select 
                            className="form-select"
                            value={targetMarket}
                            onChange={(e) => setTargetMarket(e.target.value)}
                            style={{ borderColor: 'var(--color-danger)' }}
                          >
                            <option value="North America">North America (Hasbro Exclusive - Blocked)</option>
                            <option value="Europe">Europe (Non-Exclusive - Cleared)</option>
                          </select>
                        </div>
                      </div>
                    )}

                    {/* INPUT 2: Production capacity slider (rendered after market check passes) */}
                    {flowState === 'resolved' && (
                      <div style={{ animation: 'slideIn 0.3s ease-out' }}>
                        {showHitlOptions ? (
                          <div className="risk-card warning" style={{ border: '2px solid var(--color-warning)', background: 'rgba(var(--color-warning-rgb), 0.05)', padding: '1rem' }}>
                            <div className="risk-title" style={{ color: 'var(--color-warning)', fontSize: '0.95rem', display: 'flex', alignItems: 'center', gap: '0.5rem', fontWeight: 700 }}>
                              <Shield size={16} /> Human Decision Required
                            </div>
                            <p className="risk-desc" style={{ fontSize: '0.8rem', color: 'var(--text-main)', margin: '0.5rem 0' }}>
                              Procurement volume of <strong>{productionVolume.toLocaleString()} units</strong> exceeds the hard capacity cap limit of <strong>25,000 units</strong> for primary vendor. Select a remediation path to proceed:
                            </p>
                            
                            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', marginTop: '0.75rem' }}>
                              <button 
                                className="preset-btn primary"
                                style={{ 
                                  textAlign: 'left', 
                                  padding: '0.75rem', 
                                  background: 'rgba(var(--accent-blue-rgb), 0.06)',
                                  borderColor: 'var(--accent-blue)',
                                  borderRadius: '0.35rem',
                                  fontSize: '0.75rem',
                                  cursor: 'pointer',
                                  display: 'flex',
                                  flexDirection: 'column',
                                  gap: '0.2rem'
                                }}
                                onClick={() => {
                                  setProductionVolume(25000);
                                  setShowAddendumSuccess(true);
                                  setShowSliderGuardrail(false);
                                  setShowHitlOptions(false);
                                  addLog("Orchestrator", "User approved capacity split override. Generating Addendum Contract SC-7798-EU.");
                                  addLog("mcp-procurement-ledger", "Ledger transaction updated. Primary: 25,000 SKUs. Addendum: 15,000 SKUs.");
                                  setChatLogs(prev => [...prev, "✅ Human Override Selected: Split excess 15,000 units into Addendum Contract SC-7798-EU."]);
                                }}
                              >
                                <span style={{ fontWeight: 'bold', color: 'var(--accent-blue)', display: 'flex', alignItems: 'center', gap: '0.3rem' }}>
                                  <Layers size={12} /> Option A: Split Sourcing (Addendum SC-7798-EU)
                                </span>
                                <span style={{ color: 'var(--text-muted)' }}>Split excess 15,000 units to secondary manufacturing partner under addendum.</span>
                              </button>

                              <button 
                                className="preset-btn"
                                style={{ 
                                  textAlign: 'left', 
                                  padding: '0.75rem', 
                                  background: 'rgba(var(--color-warning-rgb), 0.06)',
                                  borderColor: 'var(--color-warning)',
                                  borderRadius: '0.35rem',
                                  fontSize: '0.75rem',
                                  cursor: 'pointer',
                                  display: 'flex',
                                  flexDirection: 'column',
                                  gap: '0.2rem'
                                }}
                                onClick={() => {
                                  setProductionVolume(25000);
                                  setShowAddendumSuccess(false);
                                  setShowSliderGuardrail(false);
                                  setShowHitlOptions(false);
                                  addLog("Orchestrator", "User selected: Enforce Cap. Sourcing order capped strictly at 25,000 SKUs.");
                                  addLog("mcp-procurement-ledger", "Capped volume enforced. Primary: 25,000 SKUs. Excess cancelled.");
                                  setChatLogs(prev => [...prev, "✅ Human Override Selected: Strictly capped volume at 25,000 SKUs (excess cancelled)."]);
                                }}
                              >
                                <span style={{ fontWeight: 'bold', color: 'var(--color-warning)', display: 'flex', alignItems: 'center', gap: '0.3rem' }}>
                                  <Sliders size={12} /> Option B: Enforce Cap (25,000 SKUs)
                                </span>
                                <span style={{ color: 'var(--text-muted)' }}>Snap volume down to 25,000 units limit. Do not split to addendum.</span>
                              </button>
                            </div>
                          </div>
                        ) : (
                          <>
                            <div className="risk-card" style={{ background: 'rgba(var(--accent-blue-rgb), 0.04)', borderColor: 'rgba(var(--accent-blue-rgb), 0.15)' }}>
                              <div className="risk-title" style={{ color: 'var(--color-success)' }}>
                                <CheckCircle size={14} /> Style & Legal clearances cleared!
                              </div>
                              <p className="risk-desc">
                                {activeScenario === 'collab' ? (
                                  "Agents successfully auto-negotiated Europe rerouting & certified Outfit typography replacement."
                                ) : (
                                  "All licensing regulations check out. Verify sourcing limits next to finalize release."
                                )}
                              </p>
                            </div>

                            <div className="form-group" style={{ border: '1px dashed var(--color-success)', padding: '0.75rem', borderRadius: '0.4rem', background: 'rgba(var(--accent-blue-rgb), 0.02)' }}>
                              <label className="form-label">
                                <span style={{ color: 'var(--color-success)', fontWeight: 'bold' }}>✓ Sourcing Allocation Capacity</span>
                                <span style={{ color: 'var(--accent-blue)' }}>mcp-procurement-ledger</span>
                              </label>
                              
                              <div className="volume-slider-container">
                                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.8rem', fontWeight: 600 }}>
                                  <span>{productionVolume.toLocaleString()} SKUs</span>
                                  <span style={{ color: 'var(--text-muted)' }}>Limit: 25,000</span>
                                </div>
                                
                                <input 
                                  type="range" 
                                  min="5000" 
                                  max="50000" 
                                  step="5000" 
                                  value={productionVolume}
                                  className="slider-control"
                                  onChange={(e) => handleVolumeChange(e.target.value)}
                                />

                                {showSliderGuardrail && (
                                  <div className="slider-cap-alert">
                                    <AlertCircle size={12} style={{ flexShrink: 0 }} />
                                    <span>Volume limit reached. Splitting gap into addendum...</span>
                                  </div>
                                )}

                                {showAddendumSuccess && (
                                  <div className="slider-cap-alert" style={{ color: 'var(--color-success)', background: 'rgba(var(--color-success-rgb), 0.08)', borderColor: 'rgba(var(--color-success-rgb), 0.2)' }}>
                                    <CheckCircle size={12} style={{ flexShrink: 0 }} />
                                    <span>Gap volume split to Addendum Contract SC-7798-EU.</span>
                                  </div>
                                )}
                              </div>
                            </div>
                          </>
                        )}
                      </div>
                    )}

                    {/* INPUT 3: Ledger receipt transaction details (rendered on final release) */}
                    {flowState === 'completed' && (
                      <div style={{ animation: 'slideIn 0.3s ease-out' }}>
                        <div className="risk-card" style={{ background: 'rgba(var(--color-success-rgb), 0.04)', borderColor: 'rgba(var(--color-success-rgb), 0.2)', padding: '1rem' }}>
                          <div className="risk-title" style={{ color: 'var(--color-success)', fontSize: '0.9rem' }}>
                            <CheckCircle size={16} /> Release Transaction Signed
                          </div>
                          <div style={{ marginTop: '0.75rem', padding: '0.5rem', background: 'var(--bg-tertiary)', border: '1px solid var(--glass-border)', borderRadius: '0.25rem', fontFamily: 'Courier New', fontSize: '0.7rem', color: 'var(--text-main)' }}>
                            <div>TRANSACTION: 0x8a92f7c00e12</div>
                            <div>DESTINATION: Europe</div>
                            <div>CAPACITY: {productionVolume.toLocaleString()} (Primary)</div>
                            {showAddendumSuccess && <div>ADDENDUM: 15,000 (Secondary SC-7798-EU)</div>}
                          </div>
                        </div>
                      </div>
                    )}

                    {/* INPUT 4: HARD FAIL LORE SPILL CARD */}
                    {flowState === 'failed' && (
                      <div className="risk-card" style={{ background: 'rgba(var(--color-danger-rgb), 0.04)', borderColor: 'rgba(var(--color-danger-rgb), 0.2)' }}>
                        <div className="risk-title text-danger">
                          <XCircle size={14} /> Lore Compliance Audit Blocked
                        </div>
                        <p className="risk-desc">
                          Prototype figurine leaks unreleased Season 4 storyline spoilers (Grogu wielding lightsaber). Sourcing release aborted immediately.
                        </p>
                      </div>
                    )}

                    {flowState === 'failed' ? (
                      <button 
                        className="preset-btn"
                        style={{
                          width: '100%',
                          padding: '0.75rem',
                          background: 'rgba(var(--color-danger-rgb), 0.1)',
                          borderColor: 'rgba(var(--color-danger-rgb), 0.2)',
                          fontWeight: 700,
                          fontSize: '0.8rem',
                          color: 'var(--color-danger)',
                          cursor: 'not-allowed'
                        }}
                        disabled
                      >
                        <XCircle size={14} /> Sourcing Release Aborted
                      </button>
                    ) : (
                      <button 
                        className="preset-btn"
                        style={{
                          width: '100%',
                          padding: '0.75rem',
                          background: (flowState === 'resolved' && !showHitlOptions) ? 'var(--color-success)' : 'var(--bg-tertiary)',
                          borderColor: (flowState === 'resolved' && !showHitlOptions) ? 'var(--color-success)' : 'var(--glass-border)',
                          fontWeight: 700,
                          fontSize: '0.8rem',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          gap: '0.5rem',
                          color: (flowState === 'resolved' && !showHitlOptions) ? 'white' : 'var(--text-muted)',
                          cursor: (flowState === 'resolved' && !showHitlOptions) ? 'pointer' : 'not-allowed'
                        }}
                        disabled={flowState !== 'resolved' || showHitlOptions}
                        onClick={() => {
                          setFlowState('completed');
                          addLog("Orchestrator", "Sourcing release finalized on ledger registry.");
                        }}
                      >
                        {(flowState === 'resolved' && !showHitlOptions) ? (
                          <>
                            <RefreshCw size={14} className="spin" style={{ animation: 'spin 2s linear infinite' }} /> Auto-Finalizing Sourcing Release...
                          </>
                        ) : (
                          <>
                            <Play size={14} /> Finalize Sourcing Release
                          </>
                        )}
                      </button>
                    )}

                  </div>
                )}
              </div>

            </div>

            {/* Right Column: Predefined Workflow & Inter-Agent Loops Graph */}
            <div className="workspace-column">
              
              <div className="workflow-graph-container" style={{ flex: 1 }}>
                <h3 className="panel-title">
                  <GitBranch size={16} style={{ color: 'var(--accent-purple)' }} />
                  <span>Proposed Multi-Agent Execution Graph</span>
                </h3>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', flex: 1, justifyContent: 'space-between' }}>
                  {/* Row 1: Style Agent, Legal Agent, & Storyline Agent running concurrently in 3 parallel columns */}
                  {/* Relative wrapper for nodes and dynamic arrow connections */}
                  <div style={{ position: 'relative', width: '100%' }}>
                    
                    {/* SVG Connector Arrows Overlay */}
                    {flowState === 'negotiating' && (
                      <svg 
                        viewBox="0 0 300 100" 
                        preserveAspectRatio="none"
                        style={{ 
                          position: 'absolute', 
                          top: 0, 
                          left: 0, 
                          width: '100%', 
                          height: '100%', 
                          pointerEvents: 'none', 
                          zIndex: 10,
                          overflow: 'visible'
                        }}
                      >
                        <defs>
                          <style>{`
                            @keyframes dash {
                              to {
                                stroke-dashoffset: -20;
                              }
                            }
                          `}</style>
                          <marker id="arrow-purple" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto">
                            <path d="M 0 1.5 L 8 5 L 0 8.5 z" fill="var(--accent-purple)" />
                          </marker>
                          <marker id="arrow-green" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto">
                            <path d="M 0 1.5 L 8 5 L 0 8.5 z" fill="var(--color-success)" />
                          </marker>
                          <marker id="arrow-danger" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto">
                            <path d="M 0 1.5 L 8 5 L 0 8.5 z" fill="var(--color-danger)" />
                          </marker>
                        </defs>

                        {/* Render active step connecting channels */}
                        {(() => {
                          const stepCount = negotiationLogs.length;
                          if (stepCount === 1) {
                            return <path d="M 135,35 Q 95,20 65,35" fill="none" stroke="var(--color-danger)" strokeWidth="1.5" strokeDasharray="4,3" markerEnd="url(#arrow-danger)" style={{ animation: 'dash 1.2s linear infinite' }} />;
                          } else if (stepCount === 2) {
                            return <path d="M 235,35 Q 150,5 65,35" fill="none" stroke="var(--accent-purple)" strokeWidth="1.5" strokeDasharray="4,3" markerEnd="url(#arrow-purple)" style={{ animation: 'dash 1.2s linear infinite' }} />;
                          } else if (stepCount === 3) {
                            return (
                              <>
                                <path d="M 65,35 Q 100,20 135,35" fill="none" stroke="var(--color-success)" strokeWidth="1.5" strokeDasharray="4,3" markerEnd="url(#arrow-green)" style={{ animation: 'dash 1.2s linear infinite' }} />
                                <path d="M 65,35 Q 150,5 235,35" fill="none" stroke="var(--color-success)" strokeWidth="1.5" strokeDasharray="4,3" markerEnd="url(#arrow-green)" style={{ animation: 'dash 1.2s linear infinite' }} />
                              </>
                            );
                          } else if (stepCount === 4) {
                            return (
                              <>
                                <path d="M 165,35 Q 200,20 235,35" fill="none" stroke="var(--accent-purple)" strokeWidth="1.5" strokeDasharray="4,3" markerEnd="url(#arrow-purple)" style={{ animation: 'dash 1.2s linear infinite' }} />
                                <path d="M 135,35 Q 100,20 65,35" fill="none" stroke="var(--accent-purple)" strokeWidth="1.5" strokeDasharray="4,3" markerEnd="url(#arrow-purple)" style={{ animation: 'dash 1.2s linear infinite' }} />
                              </>
                            );
                          } else if (stepCount === 5) {
                            return <path d="M 235,35 Q 200,20 165,35" fill="none" stroke="var(--color-success)" strokeWidth="1.5" strokeDasharray="4,3" markerEnd="url(#arrow-green)" style={{ animation: 'dash 1.2s linear infinite' }} />;
                          }
                          return null;
                        })()}
                      </svg>
                    )}

                    {/* HTML Floating Labels to prevent SVG text distortion */}
                    {flowState === 'negotiating' && (() => {
                      const stepCount = negotiationLogs.length;
                      const baseLabelStyle = {
                        position: 'absolute',
                        transform: 'translateX(-50%)',
                        fontSize: '0.9rem',
                        fontWeight: 'bold',
                        zIndex: 11,
                        pointerEvents: 'none',
                        background: 'var(--bg-card)',
                        padding: '3px 8px',
                        borderRadius: '4px',
                        border: '1px solid var(--glass-border)',
                        boxShadow: '0 2px 4px rgba(0,0,0,0.1)',
                        whiteSpace: 'nowrap'
                      };

                      if (stepCount === 1) {
                        return (
                          <div style={{ ...baseLabelStyle, left: '33.3%', top: '0px', color: 'var(--color-danger)', borderColor: 'rgba(229, 9, 20, 0.3)' }}>
                            Exclusivity Block Check
                          </div>
                        );
                      } else if (stepCount === 2) {
                        return (
                          <div style={{ ...baseLabelStyle, left: '50%', top: '-20px', color: 'var(--accent-purple)', borderColor: 'rgba(124, 58, 237, 0.3)' }}>
                            Suggest Replace Spoiler Image
                          </div>
                        );
                      } else if (stepCount === 3) {
                        return (
                          <div style={{ ...baseLabelStyle, left: '50%', top: '-20px', color: 'var(--color-success)', borderColor: 'rgba(16, 185, 129, 0.3)' }}>
                            Font & Image Swapped (Clean)
                          </div>
                        );
                      } else if (stepCount === 4) {
                        return (
                          <div style={{ ...baseLabelStyle, left: '50%', top: '-8px', color: 'var(--accent-purple)', borderColor: 'rgba(124, 58, 237, 0.3)' }}>
                            Reroute: Check Europe Exclusivity
                          </div>
                        );
                      } else if (stepCount === 5) {
                        return (
                          <div style={{ ...baseLabelStyle, left: '66.6%', top: '0px', color: 'var(--color-success)', borderColor: 'rgba(16, 185, 129, 0.3)' }}>
                            Timelines & Embargo Cleared
                          </div>
                        );
                      }
                      return null;
                    })()}

                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '0.75rem', position: 'relative', zIndex: 1 }}>
                      
                      {/* Node A: Style Compliance Agent Workflow */}
                      <div className={`agent-node-card ${
                        flowState === 'idle' ? '' : (
                          flowState === 'uploading' || flowState === 'analyzing' ? '' : (
                            flowState === 'negotiating' ? (
                              negotiationLogs[negotiationLogs.length - 1]?.agent === 'Brand Style Compliance Agent' ? 'active' : (
                                fontStyle === 'SpaceGrotesk' ? 'warning' : 'success'
                              )
                            ) : (
                              flowState === 'warning' ? 'warning' : 'success'
                            )
                          )
                        )
                      }`}>
                        <div className="node-header">
                          <span>Style Agent</span>
                          <span style={{ fontSize: '0.55rem' }}>
                            {flowState === 'idle' ? '● idle' : (
                              flowState === 'uploading' || flowState === 'analyzing' ? '● verifying' : (
                                flowState === 'negotiating' ? (
                                  negotiationLogs[negotiationLogs.length - 1]?.agent === 'Brand Style Compliance Agent' ? '● negotiating' : (
                                    fontStyle === 'SpaceGrotesk' ? '⚠️ warning' : '✓ pass'
                                  )
                                ) : (
                                  flowState === 'warning' ? '⚠️ warning' : '✓ pass'
                                )
                              )
                            )}
                          </span>
                        </div>
                        <div className="sub-workflow-list">
                          <div className={`sub-step ${flowState !== 'idle' ? 'completed' : ''}`}>
                            {flowState !== 'idle' ? <CheckCircle size={8} /> : <div style={{width: 8}}/>}
                            <span>Ingest Assets</span>
                          </div>
                          <div className={`sub-step ${['analyzing', 'negotiating', 'warning', 'resolved', 'completed', 'failed'].includes(flowState) ? 'completed' : ''}`}>
                            {['analyzing', 'negotiating', 'warning', 'resolved', 'completed', 'failed'].includes(flowState) ? <CheckCircle size={8} /> : <div style={{width: 8}}/>}
                            <span>Verify Swatches</span>
                          </div>
                          <div className={`sub-step ${
                            (flowState === 'warning' || (flowState === 'negotiating' && fontStyle === 'SpaceGrotesk')) ? 'active' : (
                              (['resolved', 'completed', 'failed'].includes(flowState) || (flowState === 'negotiating' && fontStyle === 'Outfit')) ? 'completed' : ''
                            )
                          }`} style={{ borderColor: (flowState === 'warning' || (flowState === 'negotiating' && fontStyle === 'SpaceGrotesk')) ? 'var(--color-warning)' : 'transparent' }}>
                            {(flowState === 'warning' || (flowState === 'negotiating' && fontStyle === 'SpaceGrotesk')) ? <AlertTriangle size={8} className="text-warning" /> : (
                              (['resolved', 'completed', 'failed'].includes(flowState) || (flowState === 'negotiating' && fontStyle === 'Outfit')) ? <CheckCircle size={8} /> : <div style={{width: 8}}/>
                            )}
                            <span>Flag anomalies</span>
                          </div>
                        </div>
                      </div>

                      {/* Node B: Legal Clearance & IP Counsel Workflow */}
                      <div className={`agent-node-card ${
                        flowState === 'idle' ? '' : (
                          flowState === 'uploading' || flowState === 'analyzing' ? '' : (
                            flowState === 'negotiating' ? (
                              negotiationLogs[negotiationLogs.length - 1]?.agent === 'IP Counsel Agent' ? 'active' : (
                                targetMarket === 'North America' ? 'warning' : 'success'
                              )
                            ) : (
                              flowState === 'warning' ? 'warning' : 'success'
                            )
                          )
                        )
                      }`} style={{ borderColor: (flowState === 'warning' || (flowState === 'negotiating' && targetMarket === 'North America' && negotiationLogs[negotiationLogs.length - 1]?.agent !== 'IP Counsel Agent')) ? 'var(--color-danger)' : '' }}>
                        <div className="node-header">
                          <span>Legal IP Agent</span>
                          <span style={{ 
                            fontSize: '0.55rem', 
                            color: (flowState === 'warning' || (flowState === 'negotiating' && targetMarket === 'North America' && negotiationLogs[negotiationLogs.length - 1]?.agent !== 'IP Counsel Agent')) ? 'var(--color-danger)' : '' 
                          }}>
                            {flowState === 'idle' ? '● idle' : (
                              flowState === 'uploading' || flowState === 'analyzing' ? '● verifying' : (
                                flowState === 'negotiating' ? (
                                  negotiationLogs[negotiationLogs.length - 1]?.agent === 'IP Counsel Agent' ? '● negotiating' : (
                                    targetMarket === 'North America' ? '⛔ blocked' : '✓ cleared'
                                  )
                                ) : (
                                  flowState === 'warning' ? '⛔ blocked' : '✓ cleared'
                                )
                              )
                            )}
                          </span>
                        </div>
                        <div className="sub-workflow-list">
                          <div className={`sub-step ${flowState !== 'idle' ? 'completed' : ''}`}>
                            {flowState !== 'idle' ? <CheckCircle size={8} /> : <div style={{width: 8}}/>}
                            <span>Check Rights</span>
                          </div>
                          <div className={`sub-step ${
                            (flowState === 'warning' || (flowState === 'negotiating' && targetMarket === 'North America')) ? 'active' : (
                              (['resolved', 'completed', 'failed'].includes(flowState) || (flowState === 'negotiating' && targetMarket === 'Europe')) ? 'completed' : ''
                            )
                          }`} style={{ borderColor: (flowState === 'warning' || (flowState === 'negotiating' && targetMarket === 'North America')) ? 'var(--color-danger)' : 'transparent' }}>
                            {(flowState === 'warning' || (flowState === 'negotiating' && targetMarket === 'North America')) ? <AlertCircle size={8} style={{ color: 'var(--color-danger)' }} /> : (
                              (['resolved', 'completed', 'failed'].includes(flowState) || (flowState === 'negotiating' && targetMarket === 'Europe')) ? <CheckCircle size={8} /> : <div style={{width: 8}}/>
                            )}
                            <span>Scan Exclusivity</span>
                          </div>
                          <div className={`sub-step ${['resolved', 'completed', 'failed'].includes(flowState) ? 'completed' : ''}`}>
                            {['resolved', 'completed', 'failed'].includes(flowState) ? <CheckCircle size={8} /> : <div style={{width: 8}}/>}
                            <span>Verify Customs</span>
                          </div>
                        </div>
                      </div>

                      {/* Node C: Franchise Storyline & Lore Compliance Agent (AG_Storyline) */}
                      <div className={`agent-node-card ${
                        flowState === 'idle' ? '' : (
                          flowState === 'uploading' || flowState === 'analyzing' ? '' : (
                            flowState === 'negotiating' ? (
                              negotiationLogs[negotiationLogs.length - 1]?.agent === 'Franchise Storyline & Lore Agent' ? 'active' : (
                                storylineStatus === 'Spoiler Flagged' ? 'warning' : 'success'
                              )
                            ) : (
                              flowState === 'failed' ? 'warning' : 'success'
                            )
                          )
                        )
                      }`} style={{ borderColor: (flowState === 'failed' || (flowState === 'negotiating' && storylineStatus === 'Spoiler Flagged' && negotiationLogs[negotiationLogs.length - 1]?.agent !== 'Franchise Storyline & Lore Agent')) ? 'var(--color-danger)' : '' }}>
                        <div className="node-header">
                          <span>Storyline Agent</span>
                          <span style={{ 
                            fontSize: '0.55rem', 
                            color: (flowState === 'failed' || (flowState === 'negotiating' && storylineStatus === 'Spoiler Flagged' && negotiationLogs[negotiationLogs.length - 1]?.agent !== 'Franchise Storyline & Lore Agent')) ? 'var(--color-danger)' : '' 
                          }}>
                            {flowState === 'idle' ? '● idle' : (
                              flowState === 'uploading' || flowState === 'analyzing' ? '● verifying' : (
                                flowState === 'negotiating' ? (
                                  negotiationLogs[negotiationLogs.length - 1]?.agent === 'Franchise Storyline & Lore Agent' ? '● negotiating' : (
                                    storylineStatus === 'Spoiler Flagged' ? '❌ leak' : '✓ consistent'
                                  )
                                ) : (
                                  flowState === 'failed' ? '❌ leak' : '✓ consistent'
                                )
                              )
                            )}
                          </span>
                        </div>
                        <div className="sub-workflow-list">
                          <div className={`sub-step ${['analyzing', 'negotiating', 'warning', 'resolved', 'completed', 'failed'].includes(flowState) ? 'completed' : ''}`}>
                            {['analyzing', 'negotiating', 'warning', 'resolved', 'completed', 'failed'].includes(flowState) ? <CheckCircle size={8} /> : <div style={{width: 8}}/>}
                            <span>Scan Scripts</span>
                          </div>
                          <div className={`sub-step ${
                            (flowState === 'failed' || (flowState === 'negotiating' && storylineStatus === 'Spoiler Flagged')) ? 'active' : (
                              (['resolved', 'completed'].includes(flowState) || (flowState === 'negotiating' && storylineStatus === 'Compliant')) ? 'completed' : ''
                            )
                          }`} style={{ borderColor: (flowState === 'failed' || (flowState === 'negotiating' && storylineStatus === 'Spoiler Flagged')) ? 'var(--color-danger)' : 'transparent' }}>
                            {(flowState === 'failed' || (flowState === 'negotiating' && storylineStatus === 'Spoiler Flagged')) ? <AlertCircle size={8} style={{ color: 'var(--color-danger)' }} /> : (
                              (['resolved', 'completed'].includes(flowState) || (flowState === 'negotiating' && storylineStatus === 'Compliant')) ? <CheckCircle size={8} /> : <div style={{width: 8}}/>
                            )}
                            <span>Verify Canon</span>
                          </div>
                          <div className={`sub-step ${
                            (flowState === 'failed' || (flowState === 'negotiating' && storylineStatus === 'Spoiler Flagged')) ? 'active' : (
                              (['resolved', 'completed'].includes(flowState) || (flowState === 'negotiating' && storylineStatus === 'Compliant')) ? 'completed' : ''
                            )
                          }`} style={{ borderColor: (flowState === 'failed' || (flowState === 'negotiating' && storylineStatus === 'Spoiler Flagged')) ? 'var(--color-danger)' : 'transparent' }}>
                            {(flowState === 'failed' || (flowState === 'negotiating' && storylineStatus === 'Spoiler Flagged')) ? <XCircle size={8} style={{ color: 'var(--color-danger)' }} /> : (
                              (['resolved', 'completed'].includes(flowState) || (flowState === 'negotiating' && storylineStatus === 'Compliant')) ? <CheckCircle size={8} /> : <div style={{width: 8}}/>
                            )}
                            <span>Check Embargo</span>
                          </div>
                        </div>
                      </div>

                    </div>
                  </div>

                  {/* INTER-AGENT LOOPBACK INDICATOR */}
                  <div className="loop-feedback-line" style={{ marginTop: '0.5rem' }}>
                    <span className="loop-label" style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                      <LoopIcon size={16} className={['warning', 'resolved', 'negotiating'].includes(flowState) ? "spin" : ""} style={{ animation: ['warning', 'resolved', 'negotiating'].includes(flowState) ? 'spin 3s linear infinite' : 'none' }} />
                      <span>Concurrently verifying multi-agent parameters overrides loopback</span>
                    </span>
                  </div>

                  {/* Flow Arrow indicating transition to Sourcing & Dispatch */}
                  <div className="arrow-flow active" style={{ display: 'flex', flexDirection: 'column' }}>
                    <div style={{ fontSize: '0.6rem', color: 'var(--text-muted)', marginBottom: '0.2rem' }}>CONTRACT DISPATCH</div>
                    <ArrowRight style={{ transform: 'rotate(90deg)' }} />
                  </div>

                  {/* Row 2: Post-Approval Sourcing & Dispatch */}
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: '1rem' }}>
                    {flowState === 'completed' ? (
                      /* Visual Document Preview Card */
                      <div className="canvas-panel" style={{ 
                        background: 'rgba(var(--color-success-rgb), 0.03)',
                        border: '2px solid var(--color-success)',
                        boxShadow: 'var(--shadow-neon-success)',
                        padding: '1rem',
                        borderRadius: '0.6rem',
                        animation: 'slideIn 0.4s ease-out'
                      }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid var(--glass-border)', paddingBottom: '0.5rem', marginBottom: '0.75rem' }}>
                          <span style={{ fontSize: '0.75rem', fontWeight: 800, color: 'var(--color-success)', display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
                            <CheckCircle size={14} /> CERTIFICATE OF COMPLIANCE ISSUED
                          </span>
                          <span style={{ fontSize: '0.6rem', color: 'var(--text-muted)', fontFamily: 'monospace' }}>
                            ID: VIBE-LIC-{(activeScenario === 'collab') ? '8841-EU' : ((activeScenario === 'hitl') ? '9012-SPLIT' : '1092-EU')}
                          </span>
                        </div>

                        {/* Document Content Details */}
                        <div style={{ display: 'flex', gap: '1rem', fontSize: '0.75rem' }}>
                          {/* Compliance Certificate Column */}
                          <div style={{ flex: 1.2, background: 'var(--bg-secondary)', border: '1px dashed var(--glass-border)', padding: '0.6rem', borderRadius: '0.4rem' }}>
                            <div style={{ fontWeight: 'bold', fontSize: '0.65rem', textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: '0.4rem' }}>Licensing Certificate</div>
                            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.3rem', fontSize: '0.7rem' }}>
                              <div><strong>Brand:</strong> STAR WARS</div>
                              <div><strong>Target Route:</strong> {targetMarket}</div>
                              <div><strong>Approved Font:</strong> {fontStyle}</div>
                              <div><strong>Status:</strong> <span style={{ color: 'var(--color-success)', fontWeight: 'bold' }}>CLEARED FOR PRODUCTION</span></div>
                            </div>
                            <div style={{ borderTop: '1px solid var(--glass-border)', marginTop: '0.5rem', paddingTop: '0.4rem' }}>
                              <div style={{ fontSize: '0.55rem', fontWeight: 'bold', textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: '0.2rem' }}>Digital Agent Signatures</div>
                              <div style={{ display: 'flex', gap: '0.4rem', flexWrap: 'wrap' }}>
                                <span style={{ fontSize: '0.5rem', background: 'rgba(16, 185, 129, 0.1)', color: 'var(--color-success)', padding: '1px 4px', borderRadius: '3px', border: '1px solid rgba(16, 185, 129, 0.2)' }}>✓ Style Compliance</span>
                                <span style={{ fontSize: '0.5rem', background: 'rgba(16, 185, 129, 0.1)', color: 'var(--color-success)', padding: '1px 4px', borderRadius: '3px', border: '1px solid rgba(16, 185, 129, 0.2)' }}>✓ IP Counsel</span>
                                <span style={{ fontSize: '0.5rem', background: 'rgba(16, 185, 129, 0.1)', color: 'var(--color-success)', padding: '1px 4px', borderRadius: '3px', border: '1px solid rgba(16, 185, 129, 0.2)' }}>✓ Storyline Lore</span>
                              </div>
                            </div>
                          </div>

                          {/* Associated Contracts Column */}
                          <div style={{ flex: 1, background: 'var(--bg-secondary)', border: '1px dashed var(--glass-border)', padding: '0.6rem', borderRadius: '0.4rem', display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
                            <div>
                              <div style={{ fontWeight: 'bold', fontSize: '0.65rem', textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: '0.4rem' }}>Dispatched Contracts</div>
                              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.35rem', fontSize: '0.65rem' }}>
                                <div style={{ display: 'flex', alignItems: 'center', gap: '0.25rem', color: 'var(--accent-blue)' }}>
                                  <Layers size={10} /> Master Manufacturing Agr.
                                </div>
                                <div style={{ color: 'var(--text-muted)', paddingLeft: '0.75rem', fontSize: '0.55rem' }}>
                                  Hub: {targetMarket} Factory (Signed)
                                </div>
                                
                                {activeScenario === 'hitl' && showAddendumSuccess && (
                                  <>
                                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.25rem', color: 'var(--accent-purple)', marginTop: '0.2rem' }}>
                                      <Layers size={10} /> Addendum Contract SC-7798
                                    </div>
                                    <div style={{ color: 'var(--text-muted)', paddingLeft: '0.75rem', fontSize: '0.55rem' }}>
                                      15,000 SKUs Split Allocation
                                    </div>
                                  </>
                                )}
                              </div>
                            </div>
                            <div style={{ fontSize: '0.6rem', color: 'var(--color-success)', fontWeight: 'bold', borderTop: '1px solid var(--glass-border)', paddingTop: '0.4rem', display: 'flex', alignItems: 'center', gap: '0.2rem', marginTop: '0.4rem' }}>
                              <span>🚀 PO dispatched to factories</span>
                            </div>
                          </div>
                        </div>
                      </div>
                    ) : (
                      /* Idle / Pending State */
                      <div className={`agent-node-card ${
                        flowState === 'failed' ? 'warning' : ''
                      }`} style={{ borderColor: flowState === 'failed' ? 'var(--color-danger)' : '' }}>
                        <div className="node-header">
                          <span>Post-Approval Sourcing & Dispatch</span>
                          <span>{flowState === 'failed' ? '❌ release frozen' : '● pending audit'}</span>
                        </div>
                        <div className="sub-workflow-list" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.5rem' }}>
                          <div className={`sub-step ${flowState === 'failed' ? 'completed' : ''}`}>
                            {flowState === 'failed' ? <XCircle size={10} style={{ color: 'var(--color-danger)' }} /> : <div style={{width: 10}}/>}
                            <span>1. Generating Certificate</span>
                          </div>
                          <div className={`sub-step ${flowState === 'failed' ? 'completed' : ''}`}>
                            {flowState === 'failed' ? <XCircle size={10} style={{ color: 'var(--color-danger)' }} /> : <div style={{width: 10}}/>}
                            <span>2. Dispatching Contracts</span>
                          </div>
                        </div>
                      </div>
                    )}
                  </div>

                </div>
              </div>

              {/* Console log terminal */}
              <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: 'var(--text-muted)', fontSize: '0.7rem', marginBottom: '0.4rem' }}>
                  <Terminal size={12} />
                  <span>Execution telemetry console logs</span>
                </div>
                <div className="console-panel">
                  {logs.map(log => (
                    <div key={log.id} className="log-line">
                      <span className="log-timestamp">[{log.time}]</span>
                      <span className="log-agent">{log.agent}:</span>
                      <span>{log.message}</span>
                    </div>
                  ))}
                  <div ref={terminalEndRef} />
                </div>
              </div>

            </div>
          </>
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
