import { useState, useMemo } from 'react';
import {
    Download, FileText, Code2, RotateCcw, ChevronDown, ChevronUp,
    CheckCircle2, AlertTriangle, XCircle, BarChart3, ListChecks, DownloadCloud
} from 'lucide-react';
import { getDownloadUrl } from '../api';

function CategoryBar({ name, score, passed, total }) {
    const isPerfect = score === 100;
    return (
        <div className="flex flex-col gap-1">
            <div className="flex items-center justify-between">
                <span className="text-xs font-bold uppercase tracking-wider" style={{ color: 'var(--text-heading)' }}>{name}</span>
                <span className="text-xs font-mono font-medium" style={{ color: isPerfect ? 'var(--success)' : 'var(--text-muted)' }}>
                    {passed}/{total}
                </span>
            </div>
            <div className="h-2 rounded-sm overflow-hidden" style={{ background: 'var(--bg-muted)' }}>
                <div className="h-full transition-all duration-700 rounded-sm" style={{ width: `${score}%`, background: isPerfect ? 'var(--success)' : 'var(--primary)' }} />
            </div>
        </div>
    );
}

export default function ResultsPage({ result, sessionId, onReset }) {
    const [showIssues, setShowIssues] = useState(false);
    const [compTab, setCompTab] = useState('abstract');

    const report = result?.compliance_report || {};
    const score = report.score ?? 0;
    const violations = report.violations || [];
    const warnings = report.warnings || [];
    const categories = report.categories || {};
    const errors = result?.errors || [];
    const comparison = result?.comparison || null;
    const original = comparison?.original || {};
    const formatted = comparison?.formatted || {};

    const compSections = useMemo(() => {
        const secs = [{ key: 'abstract', label: 'Abstract' }];
        const all = new Set([
            ...(formatted.sections || []).map(s => s.name || s.heading),
            ...(original.sections || []).map(s => s.name || s.heading),
        ]);
        all.forEach(k => {
            if (k && k.toLowerCase() !== 'abstract') secs.push({ key: k, label: k });
        });
        return secs;
    }, [original, formatted]);

    return (
        <div className="max-w-7xl mx-auto px-6 py-12 animate-fade-in flex flex-col gap-8">

            {/* Top Banner */}
            <div className="flex flex-col md:flex-row justify-between items-start md:items-end gap-6">
                <div>
                    <h2 className="text-3xl font-extrabold tracking-tight mb-2" style={{ color: 'var(--text-heading)' }}>
                        Compliance Dashboard
                    </h2>
                    <p className="text-sm font-medium" style={{ color: 'var(--text-muted)' }}>
                        {report.summary || 'Manuscript successfully generated and validated against journal rules.'}
                    </p>
                </div>
                <div className="flex gap-3">
                    {sessionId && (
                        <>
                            <a href={getDownloadUrl(sessionId, 'docx')} download className="btn-primary">
                                <DownloadCloud className="w-4 h-4" /> Export DOCX
                            </a>
                            <a href={getDownloadUrl(sessionId, 'pdf')} download className="btn-secondary">
                                <FileText className="w-4 h-4" /> PDF
                            </a>
                            <a href={getDownloadUrl(sessionId, 'latex')} download className="btn-secondary">
                                <Code2 className="w-4 h-4" /> LaTeX
                            </a>
                        </>
                    )}
                </div>
            </div>

            {errors.length > 0 && (
                <div className="p-4 rounded-xl border" style={{ background: 'var(--error-bg)', borderColor: 'var(--error-border)' }}>
                    {errors.map((err, i) => (
                        <p key={i} className="text-sm font-semibold flex items-start gap-2" style={{ color: 'var(--error)' }}>
                            <XCircle className="w-4 h-4 shrink-0 mt-0.5" /> {err}
                        </p>
                    ))}
                </div>
            )}

            {/* Grid Layout */}
            <div className="grid lg:grid-cols-3 gap-8">

                {/* Left Column: Data Metrics */}
                <div className="flex flex-col gap-8">
                    {/* Main Score Card */}
                    <div className="card p-8 flex flex-col items-center justify-center text-center">
                        <div className="relative w-32 h-32 flex items-center justify-center mb-4">
                            <svg className="w-full h-full transform -rotate-90">
                                <circle cx="64" cy="64" r="60" fill="none" stroke="var(--bg-subtle)" strokeWidth="8" />
                                <circle cx="64" cy="64" r="60" fill="none" stroke="var(--primary)" strokeWidth="8"
                                    strokeDasharray={377} strokeDashoffset={377 - (score / 100 * 377)} strokeLinecap="round"
                                    className="transition-all duration-1000 ease-out" />
                            </svg>
                            <div className="absolute inset-0 flex items-center justify-center">
                                <span className="text-4xl font-extrabold" style={{ color: 'var(--text-heading)' }}>{score}</span>
                            </div>
                        </div>
                        <h3 className="font-bold text-lg" style={{ color: 'var(--text-heading)' }}>Adherence Score</h3>
                        <p className="text-xs mt-1" style={{ color: 'var(--text-muted)' }}>Analyzed across {Object.keys(categories).length} vectors</p>
                    </div>

                    {/* Breakdown Card */}
                    <div className="card p-6">
                        <h3 className="text-sm font-bold uppercase tracking-wider mb-6 flex items-center gap-2" style={{ color: 'var(--text-muted)' }}>
                            <BarChart3 className="w-4 h-4" /> Vector Breakdown
                        </h3>
                        <div className="space-y-5">
                            {Object.entries(categories).map(([name, data]) => (
                                <CategoryBar key={name} name={name} score={data.score ?? 0} passed={data.passed ?? 0} total={data.total ?? 0} />
                            ))}
                        </div>
                    </div>
                </div>

                {/* Middle & Right Column: Comparison & Issues */}
                <div className="lg:col-span-2 flex flex-col gap-8">

                    {/* Violations / Warnings Banner */}
                    {(violations.length > 0 || warnings.length > 0) && (
                        <div className="card border-l-4" style={{ borderLeftColor: violations.length > 0 ? 'var(--error)' : 'var(--warning)' }}>
                            <button onClick={() => setShowIssues(!showIssues)} className="w-full p-5 text-left flex items-center justify-between">
                                <div className="flex items-center gap-3">
                                    <ListChecks className="w-5 h-5" style={{ color: violations.length > 0 ? 'var(--error)' : 'var(--warning)' }} />
                                    <span className="text-sm font-bold" style={{ color: 'var(--text-heading)' }}>
                                        Action Required: {violations.length} Critical Violations, {warnings.length} Warnings
                                    </span>
                                </div>
                                {showIssues ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                            </button>

                            {showIssues && (
                                <div className="px-5 pb-5 pt-2 border-t space-y-3" style={{ borderColor: 'var(--border)' }}>
                                    {violations.map((v, i) => (
                                        <div key={`v-${i}`} className="flex items-start gap-2 text-sm p-3 rounded" style={{ background: 'var(--error-bg)', color: 'var(--error)' }}>
                                            <XCircle className="w-4 h-4 shrink-0 mt-0.5" />
                                            <span className="font-medium">{typeof v === 'string' ? v : v.message}</span>
                                        </div>
                                    ))}
                                    {warnings.map((w, i) => (
                                        <div key={`w-${i}`} className="flex items-start gap-2 text-sm p-3 rounded" style={{ background: 'var(--warning-bg)', color: 'var(--warning)' }}>
                                            <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
                                            <span className="font-medium">{typeof w === 'string' ? w : w.message}</span>
                                        </div>
                                    ))}
                                </div>
                            )}
                        </div>
                    )}

                    {/* Diff Viewer */}
                    {comparison && (
                        <div className="card flex-1 flex flex-col min-h-[500px] overflow-hidden">
                            <div className="bg-slate-50 border-b p-3 flex overflow-x-auto gap-2 scrollbar-none" style={{ background: 'var(--bg-subtle)', borderColor: 'var(--border)' }}>
                                {compSections.map(s => (
                                    <button
                                        key={s.key}
                                        onClick={() => setCompTab(s.key)}
                                        className="px-4 py-2 rounded-md justify-center text-xs font-bold whitespace-nowrap transition-colors"
                                        style={{
                                            background: compTab === s.key ? 'var(--bg-white)' : 'transparent',
                                            color: compTab === s.key ? 'var(--primary)' : 'var(--text-muted)',
                                            boxShadow: compTab === s.key ? 'var(--shadow-sm)' : 'none',
                                            border: compTab === s.key ? '1px solid var(--border)' : '1px solid transparent'
                                        }}
                                    >
                                        {s.label}
                                    </button>
                                ))}
                            </div>

                            <div className="grid md:grid-cols-2 p-1 gap-1 flex-1 bg-slate-200" style={{ background: 'var(--border)' }}>
                                {/* Left Split: Original */}
                                <div className="bg-white p-6 overflow-y-auto" style={{ background: 'var(--bg-white)' }}>
                                    <div className="inline-block px-2 py-1 bg-red-50 text-red-600 text-[10px] font-bold uppercase tracking-widest rounded mb-4">
                                        Original Source
                                    </div>
                                    <div className="text-sm leading-relaxed font-serif" style={{ color: 'var(--text-muted)' }}>
                                        {compTab === 'abstract'
                                            ? (original.abstract || 'N/A')
                                            : (original.sections?.find(s => (s.name || s.heading) === compTab)?.content || 'N/A')}
                                    </div>
                                </div>

                                {/* Right Split: Formatted */}
                                <div className="bg-white p-6 overflow-y-auto" style={{ background: 'var(--bg-white)' }}>
                                    <div className="inline-block px-2 py-1 bg-emerald-50 text-emerald-600 text-[10px] font-bold uppercase tracking-widest rounded mb-4">
                                        Formatted Output
                                    </div>
                                    <div className="text-sm leading-relaxed font-serif text-slate-900" style={{ color: 'var(--text-heading)' }}>
                                        {compTab === 'abstract'
                                            ? (formatted.abstract || 'N/A')
                                            : (formatted.sections?.find(s => (s.name || s.heading) === compTab)?.content || 'N/A')}
                                    </div>
                                </div>
                            </div>
                        </div>
                    )}
                </div>
            </div>

            <div className="mt-4 text-center">
                <button onClick={onReset} className="text-sm font-semibold hover:underline" style={{ color: 'var(--text-muted)' }}>
                    <RotateCcw className="w-3.5 h-3.5 inline mr-1" /> Start Over
                </button>
            </div>
        </div>
    );
}
