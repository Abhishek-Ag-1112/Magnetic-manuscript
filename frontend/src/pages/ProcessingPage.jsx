import { useMemo, useEffect, useRef, useState } from 'react';
import {
    FileSearch, PenTool, BookOpen, CheckCircle2, FileOutput,
    Brain, Layers, Sparkles, Clock, Loader2, Terminal, Activity, FileCheck2,
    Quote, Database, ShieldCheck, Fingerprint, Layout
} from 'lucide-react';

const PIPELINE_STEPS = [
    { id: 'parse', label: 'Document Parsing', desc: 'Extracting text, tables \u0026 structure from your manuscript', icon: FileSearch },
    { id: 'normalize', label: 'Structure Normalization', desc: 'Mapping sections to journal-compliant hierarchy', icon: Layers },
    { id: 'load_rules', label: 'Journal Rules Engine', desc: 'Loading target journal formatting requirements', icon: BookOpen },
    { id: 'rewrite', label: 'Content Preservation', desc: 'Extracting metadata, preserving original text', icon: PenTool },
    { id: 'convert_citations', label: 'Citation Formatting', desc: 'Converting references to target citation style', icon: Quote },
    { id: 'validate_references', label: 'CrossRef Verification', desc: 'Validating DOIs against CrossRef database', icon: Database },
    { id: 'format', label: 'Document Generation', desc: 'Building publish-ready DOCX with proper layout', icon: Layout },
    { id: 'validate', label: 'Compliance Scoring', desc: 'Checking against journal submission requirements', icon: ShieldCheck },
    { id: 'check_plagiarism', label: 'Originality Analysis', desc: 'Checking for self-plagiarism patterns', icon: Fingerprint },
];

const TOTAL_STEPS = PIPELINE_STEPS.length;

function getStepStatus(stepId, stepIndex, agentEvents) {
    const complete = agentEvents.find(e => e.type === 'agent_complete' && (e.data?.agent === stepId || e.data?.index === stepIndex));
    if (complete) return 'complete';
    const start = agentEvents.find(e => e.type === 'agent_start' && (e.data?.agent === stepId || e.data?.index === stepIndex));
    if (start) return 'active';
    return 'pending';
}

function getDetails(stepId, stepIndex, agentEvents) {
    return agentEvents.find(e => e.type === 'agent_complete' && (e.data?.agent === stepId || e.data?.index === stepIndex))?.data || null;
}

function LiveTimer({ running }) {
    const [seconds, setSeconds] = useState(0);
    useEffect(() => {
        if (!running) return;
        setSeconds(0);
        const interval = setInterval(() => setSeconds(s => s + 1), 1000);
        return () => clearInterval(interval);
    }, [running]);
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${String(secs).padStart(2, '0')}`;
}

export default function ProcessingPage({ fileName, journalName, agentEvents = [], pipelineStatus }) {
    const scrollRef = useRef(null);
    const completedCount = useMemo(() =>
        PIPELINE_STEPS.filter((s, i) => getStepStatus(s.id, i, agentEvents) === 'complete').length,
        [agentEvents]
    );

    const progress = pipelineStatus === 'complete' ? 100 : Math.round((completedCount / TOTAL_STEPS) * 100);
    const isRunning = pipelineStatus === 'running';

    // Auto-scroll log
    useEffect(() => {
        if (scrollRef.current) {
            scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
        }
    }, [agentEvents]);

    return (
        <div className="max-w-[1400px] mx-auto px-6 py-8 md:py-12 animate-fade-in relative ext-layout">

            {/* Header */}
            <div className="mb-12 border-b-2 border-slate-900 pb-8 flex flex-col md:flex-row md:items-end justify-between gap-6">
                <div>
                    <div className={`inline-flex items-center gap-2 px-4 py-1.5 rounded-none border-2 text-xs font-black uppercase tracking-widest mb-6 ${pipelineStatus === 'error' ? 'border-red-600 text-red-600 bg-red-50' :
                        pipelineStatus === 'complete' ? 'border-emerald-600 text-emerald-600 bg-emerald-50' :
                            'border-indigo-600 text-indigo-600 bg-indigo-50'
                        }`}>
                        {isRunning ? <Loader2 className="w-4 h-4 animate-spin" /> :
                            pipelineStatus === 'error' ? <span className="w-2.5 h-2.5 bg-red-600 animate-pulse" /> :
                                <CheckCircle2 className="w-4 h-4" />}
                        {isRunning ? 'LIVE :: AGENT PIPELINE ACTIVE' : pipelineStatus === 'error' ? 'HALTED :: ERROR' : 'COMPLETE :: ALL AGENTS FINISHED'}
                    </div>

                    <h1 className="text-4xl md:text-5xl font-black tracking-tighter text-slate-900 leading-none">
                        Manuscript Assembly <br /><span className="text-indigo-600">{isRunning ? 'In Progress' : pipelineStatus === 'complete' ? 'Complete' : 'Error'}</span>
                    </h1>
                </div>

                <div className="flex gap-12 text-right">
                    <div>
                        <p className="text-xs font-bold uppercase tracking-widest text-slate-500 mb-2">Target Journal</p>
                        <p className="text-lg font-bold text-slate-900">{journalName || 'Generic Academic'}</p>
                    </div>
                    <div>
                        <p className="text-xs font-bold uppercase tracking-widest text-slate-500 mb-2">Elapsed</p>
                        <p className="text-2xl font-black text-slate-900 font-mono leading-none">
                            <LiveTimer running={isRunning} />
                        </p>
                    </div>
                    <div>
                        <p className="text-xs font-bold uppercase tracking-widest text-slate-500 mb-2">Progress</p>
                        <p className="text-4xl font-black text-indigo-600 leading-none">{progress}%</p>
                    </div>
                </div>
            </div>

            {/* Error Banner */}
            {pipelineStatus === 'error' && (() => {
                const errorEvent = [...agentEvents].reverse().find(e => e.type === 'error' || (e.data && e.data.error));
                const errorMsg = errorEvent?.data?.error || 'An unexpected error occurred during processing.';
                return (
                    <div className="mb-8 p-6 border-2 border-red-600 bg-red-50 flex items-start gap-4">
                        <span className="w-8 h-8 flex items-center justify-center border-2 border-red-600 bg-white text-red-600 font-black text-lg shrink-0">!</span>
                        <div>
                            <p className="font-black text-red-700 text-sm uppercase tracking-wider mb-1">Pipeline Error</p>
                            <p className="text-red-600 font-medium text-sm">{errorMsg}</p>
                            <p className="text-slate-500 text-xs mt-2">Try reloading the page and re-uploading your manuscript.</p>
                        </div>
                    </div>
                );
            })()}

            {/* Grand Progress Bar */}
            <div className="mb-8">
                <div className="w-full h-3 bg-slate-200 border border-slate-300 overflow-hidden">
                    <div
                        className="h-full transition-all duration-700 ease-out"
                        style={{
                            width: `${progress}%`,
                            background: pipelineStatus === 'error'
                                ? 'linear-gradient(90deg, #dc2626, #ef4444)'
                                : pipelineStatus === 'complete'
                                    ? 'linear-gradient(90deg, #059669, #10b981)'
                                    : 'linear-gradient(90deg, #4f46e5, #818cf8)',
                        }}
                    />
                </div>
                <p className="text-xs font-mono font-bold text-slate-500 mt-2 text-right">
                    {completedCount}/{TOTAL_STEPS} agents completed
                </p>
            </div>

            <div className="grid lg:grid-cols-12 gap-8 items-start">

                {/* Left Col: Vertical Pipeline visualizer (4 columns) */}
                <div className="lg:col-span-4 flex flex-col gap-3">
                    <h3 className="text-sm font-black uppercase tracking-widest text-slate-900 flex items-center gap-2 mb-2">
                        <Activity className="w-4 h-4 text-indigo-600" /> Agent Pipeline
                    </h3>

                    {PIPELINE_STEPS.map((step, index) => {
                        const status = getStepStatus(step.id, index, agentEvents);
                        const details = getDetails(step.id, index, agentEvents);
                        const Icon = step.icon;

                        const isComplete = status === 'complete';
                        const isActive = status === 'active';

                        return (
                            <div key={step.id} className={`p-4 border-2 transition-all duration-300 relative overflow-hidden flex items-center justify-between ${isActive ? 'border-indigo-600 bg-white shadow-[4px_4px_0px_#4F46E5] translate-x-1' :
                                isComplete ? 'border-emerald-200 bg-emerald-50/50' :
                                    'border-slate-200 bg-white'
                                }`}>
                                {isActive && <div className="absolute left-0 top-0 bottom-0 w-1.5 bg-indigo-600 animate-pulse" />}

                                <div className="flex items-center gap-4 z-10 w-full">
                                    <div className={`w-10 h-10 flex flex-shrink-0 items-center justify-center border-2 transition-all duration-300 ${isComplete ? 'border-emerald-500 bg-emerald-50 text-emerald-600' :
                                        isActive ? 'border-indigo-600 bg-indigo-50 text-indigo-600 animate-pulse' :
                                            'border-slate-200 bg-slate-100 text-slate-400'
                                        }`}>
                                        {isComplete ? <CheckCircle2 className="w-5 h-5" /> :
                                            isActive ? <Loader2 className="w-5 h-5 animate-spin" /> :
                                                <Icon className="w-5 h-5" />}
                                    </div>

                                    <div className="flex-1">
                                        <div className="flex justify-between items-baseline mb-1">
                                            <p className={`text-sm font-black tracking-tight ${isActive ? 'text-indigo-900' : isComplete ? 'text-emerald-800' : 'text-slate-900'}`}>
                                                {step.label}
                                            </p>
                                            <span className="text-[10px] font-mono font-bold text-slate-400">
                                                {String(index + 1).padStart(2, '0')}/{String(TOTAL_STEPS).padStart(2, '0')}
                                            </span>
                                        </div>
                                        <p className={`text-xs font-medium line-clamp-1 ${isActive ? 'text-indigo-600' : 'text-slate-500'}`}>
                                            {isActive ? 'Processing...' : isComplete ? '✓ Done' : step.desc}
                                        </p>
                                    </div>

                                    {details?.elapsed && (
                                        <div className="text-[10px] font-mono font-bold text-emerald-600 bg-emerald-50 px-2 py-0.5 border border-emerald-200">
                                            {details.elapsed}s
                                        </div>
                                    )}
                                </div>
                            </div>
                        );
                    })}
                </div>

                {/* Right Col: Console logs & Metrics (8 columns) */}
                <div className="lg:col-span-8 flex flex-col gap-6">

                    {/* Live Metric Bar */}
                    <div className="grid grid-cols-3 gap-4">
                        <div className="border-2 border-slate-200 bg-white p-4 flex flex-col justify-between h-28">
                            <FileCheck2 className="w-5 h-5 text-slate-400 mb-2" />
                            <div>
                                <p className="text-[10px] font-black uppercase tracking-widest text-slate-500">Source File</p>
                                <p className="text-sm font-bold text-slate-900 truncate" title={fileName}>{fileName}</p>
                            </div>
                        </div>
                        <div className="border-2 border-slate-200 bg-white p-4 flex flex-col justify-between h-28">
                            <Clock className="w-5 h-5 text-slate-400 mb-2" />
                            <div>
                                <p className="text-[10px] font-black uppercase tracking-widest text-slate-500">Duration</p>
                                <p className="text-sm font-bold text-slate-900">
                                    {pipelineStatus === 'complete' ? 'Finished' : 'Streaming...'}
                                </p>
                            </div>
                        </div>
                        <div className="border-2 border-slate-200 bg-white p-4 flex flex-col justify-between h-28">
                            <Brain className="w-5 h-5 text-indigo-600 mb-2" />
                            <div>
                                <p className="text-[10px] font-black uppercase tracking-widest text-slate-500">Active Agent</p>
                                <p className="text-sm font-bold text-indigo-600 truncate">
                                    {PIPELINE_STEPS.find((s, i) => getStepStatus(s.id, i, agentEvents) === 'active')?.label || (pipelineStatus === 'complete' ? 'All Complete' : 'Waiting...')}
                                </p>
                            </div>
                        </div>
                    </div>

                    {/* Console Logger */}
                    <div className="border-2 border-slate-900 bg-[#0F172A] flex flex-col h-[500px] shadow-[8px_8px_0px_#e2e8f0]">
                        <div className="p-3 border-b-2 border-slate-800 flex items-center gap-3 bg-slate-900">
                            <Terminal className="w-4 h-4 text-emerald-400" />
                            <h3 className="text-xs font-bold uppercase tracking-widest text-slate-300">Real-Time Agent Log</h3>
                            <div className="ml-auto flex items-center gap-2">
                                {isRunning && <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />}
                                <span className="text-[10px] font-mono text-slate-500">
                                    {agentEvents.length} events
                                </span>
                            </div>
                        </div>

                        <div ref={scrollRef} className="flex-1 overflow-y-auto p-6 font-mono text-[12px] leading-relaxed space-y-2 text-slate-300">
                            <div className="text-slate-500 mb-4">
                                {">"} WebSocket connection established <br />
                                {">"} Waiting for pipeline manifest...
                            </div>

                            {agentEvents.map((e, i) => {
                                if (e.type === 'pipeline_start') {
                                    return (
                                        <div key={i} className="text-cyan-400 mb-2">
                                            <span className="text-slate-500">[{new Date().toISOString().split('T')[1].slice(0, 8)}]</span>
                                            {" "}⚡ PIPELINE INITIATED — {e.data?.total_agents} agents queued
                                        </div>
                                    );
                                }
                                if (e.type === 'agent_start') {
                                    return (
                                        <div key={i} className="text-indigo-400">
                                            <span className="text-slate-500">[{new Date().toISOString().split('T')[1].slice(0, 8)}]</span>
                                            {" "}▶ <span className="text-yellow-300">AGENT</span>::{e.data?.agent?.toUpperCase()} — {e.data?.description || 'Processing...'}
                                        </div>
                                    );
                                }
                                if (e.type === 'agent_complete') {
                                    return (
                                        <div key={i} className="text-slate-300 ml-4 pb-2 border-l-2 border-slate-800 pl-4">
                                            <span className="text-emerald-400 font-bold">✔ COMPLETE</span>
                                            <span className="text-slate-500"> ({e.data?.elapsed}s)</span>
                                            {e.data?.details && Object.entries(e.data.details).filter(([k]) => k !== 'step').map(([k, v]) => (
                                                <div key={k} className="text-slate-500">
                                                    {"  "}└─ <span className="text-slate-400">{k}</span>: <span className="text-slate-300">{typeof v === 'object' ? JSON.stringify(v) : String(v)}</span>
                                                </div>
                                            ))}
                                        </div>
                                    );
                                }
                                if (e.type === 'pipeline_complete') {
                                    return (
                                        <div key={i} className="mt-4 pt-4 border-t border-slate-800 text-emerald-400">
                                            ✦ PIPELINE {e.data?.status === 'complete' ? 'SUCCEEDED' : 'FINISHED WITH ERRORS'}
                                        </div>
                                    );
                                }
                                return null;
                            })}

                            {pipelineStatus === 'complete' && (
                                <div className="mt-6 pt-4 border-t-2 border-emerald-900/50 text-emerald-400 font-bold text-sm">
                                    <span className="animate-pulse">_</span> <br />
                                    {">>> "}ALL AGENTS FINISHED. MANUSCRIPT READY FOR DOWNLOAD.
                                </div>
                            )}
                            {pipelineStatus === 'error' && (
                                <div className="mt-6 pt-4 border-t-2 border-red-900/50 text-red-500 font-bold text-sm">
                                    <span className="animate-pulse">_</span> <br />
                                    {">>> "}PIPELINE ENCOUNTERED AN ERROR. CHECK DETAILS ABOVE.
                                </div>
                            )}
                        </div>
                    </div>

                </div>
            </div>
        </div>
    );
}
