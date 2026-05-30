import { useState, useEffect } from 'react';
import { getJournals, getFamilies } from '../api';
import { BookOpen, Library, ArrowRight, ArrowLeft, Search, Type, AlignLeft } from 'lucide-react';

export default function JournalSelectionPage({ onSelect, onBack }) {
    const [mode, setMode] = useState(null);
    const [journals, setJournals] = useState([]);
    const [families, setFamilies] = useState([]);
    const [selected, setSelected] = useState(null);
    const [expandedRules, setExpandedRules] = useState(null);
    const [loading, setLoading] = useState(true);
    const [search, setSearch] = useState('');

    useEffect(() => {
        const loadData = async () => {
            try {
                const [jd, fd] = await Promise.all([getJournals(), getFamilies()]);
                setJournals(jd.journals || []);
                setFamilies(fd.families || []);
            } catch (err) {
                console.error('Failed to load journals:', err);
            } finally {
                setLoading(false);
            }
        };
        loadData();
    }, []);

    const handleSelect = (item, type) => {
        setSelected({ ...item, selectionType: type });
        setExpandedRules(item.id);
    };

    const filtered = (list) =>
        list.filter(
            (j) =>
                j.name.toLowerCase().includes(search.toLowerCase()) ||
                (j.family || '').toLowerCase().includes(search.toLowerCase())
        );

    if (loading) {
        return (
            <div className="flex items-center justify-center py-32">
                <div className="w-8 h-8 flex items-center justify-center">
                    <div className="w-6 h-6 border-2 rounded-full animate-spin" style={{ borderColor: 'var(--border-strong)', borderTopColor: 'var(--primary)' }} />
                </div>
            </div>
        );
    }

    return (
        <div className="max-w-5xl mx-auto px-6 py-12 md:py-20 animate-fade-in">
            {/* Header */}
            <div className="mb-12">
                <h2 className="text-3xl font-extrabold mb-3 tracking-tight" style={{ color: 'var(--text-heading)' }}>
                    Configure Publication Output
                </h2>
                <p className="text-base" style={{ color: 'var(--text-muted)' }}>
                    Select a targeted journal or generic styling family ruleset.
                </p>
            </div>

            {!mode && (
                <div className="grid md:grid-cols-2 gap-6 max-w-2xl">
                    <button onClick={() => setMode('journal')} className="card text-left group p-6 hover:border-indigo-500">
                        <div className="flex items-start gap-5">
                            <div className="w-12 h-12 rounded-lg flex items-center justify-center shrink-0 shadow-sm" style={{ background: 'var(--primary-bg)', color: 'var(--primary)' }}>
                                <BookOpen className="w-6 h-6" />
                            </div>
                            <div>
                                <h3 className="text-lg font-bold" style={{ color: 'var(--text-heading)' }}>
                                    Specific Journal
                                </h3>
                                <p className="text-sm mt-1 mb-3" style={{ color: 'var(--text-muted)' }}>
                                    Target an exact journal. Applies highly specific spacing, headings, and DOIs.
                                </p>
                                <span className="badge badge-primary">{journals.length} Available</span>
                            </div>
                        </div>
                    </button>

                    <button onClick={() => setMode('family')} className="card text-left group p-6 hover:border-sky-500">
                        <div className="flex items-start gap-5">
                            <div className="w-12 h-12 rounded-lg flex items-center justify-center shrink-0 shadow-sm" style={{ background: 'var(--secondary-bg)', color: 'var(--secondary)' }}>
                                <Library className="w-6 h-6" />
                            </div>
                            <div>
                                <h3 className="text-lg font-bold" style={{ color: 'var(--text-heading)' }}>
                                    Format Family
                                </h3>
                                <p className="text-sm mt-1 mb-3" style={{ color: 'var(--text-muted)' }}>
                                    Use top-level publisher standards. Great for pre-prints or early drafts.
                                </p>
                                <span className="badge" style={{ background: 'var(--secondary-bg)', color: 'var(--secondary)', borderColor: 'var(--secondary-border)' }}>
                                    {families.length} Available
                                </span>
                            </div>
                        </div>
                    </button>
                </div>
            )}

            {mode && (
                <div className="flex flex-col lg:flex-row gap-8 animate-slide-up">
                    {/* Main List */}
                    <div className="flex-1">
                        <div className="flex items-center gap-4 mb-6">
                            <button onClick={() => { setMode(null); setSelected(null); setSearch(''); }} className="btn-secondary px-3 py-2">
                                <ArrowLeft className="w-4 h-4" />
                            </button>
                            <div className="relative flex-1 max-w-md">
                                <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2" style={{ color: 'var(--text-faint)' }} />
                                <input
                                    type="text"
                                    placeholder={`Search ${mode === 'journal' ? 'journals' : 'families'}...`}
                                    value={search}
                                    onChange={(e) => setSearch(e.target.value)}
                                    className="input pl-10"
                                />
                            </div>
                        </div>

                        <div className="grid gap-3 stagger-children">
                            {filtered(mode === 'journal' ? journals : families).map((item) => (
                                <div
                                    key={item.id}
                                    className={`selection-card ${selected?.id === item.id ? 'selected' : ''}`}
                                    onClick={() => handleSelect(item, mode)}
                                >
                                    <div className="flex justify-between items-start gap-4">
                                        <div>
                                            <h4 className="text-base font-bold" style={{ color: 'var(--text-heading)' }}>{item.name}</h4>
                                            {item.description && (
                                                <p className="text-sm mt-1" style={{ color: 'var(--text-muted)' }}>{item.description}</p>
                                            )}

                                            <div className="flex flex-wrap items-center gap-2 mt-3">
                                                {item.family && (
                                                    <span className="badge badge-primary">{item.family.replace(/_/g, ' ')}</span>
                                                )}
                                                {item.citation_style && (
                                                    <span className="badge" style={{ background: 'var(--secondary-bg)', color: 'var(--secondary)', borderColor: 'var(--secondary-border)' }}>
                                                        <BookOpen className="w-3 h-3 mr-1" /> {item.citation_style.toUpperCase()}
                                                    </span>
                                                )}
                                                {item.two_column && (
                                                    <span className="badge" style={{ background: 'var(--bg-muted)', color: 'var(--text-body)', borderColor: 'var(--border)' }}>
                                                        <AlignLeft className="w-3 h-3 mr-1" /> Two-Column
                                                    </span>
                                                )}
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            ))}
                        </div>
                    </div>

                    {/* Sidebar / Continue */}
                    <div className="lg:w-80 shrink-0">
                        <div className="sticky top-24">
                            <div className="card p-6 border-2" style={{ borderColor: selected ? 'var(--primary)' : 'var(--border)' }}>
                                <h3 className="text-sm font-bold uppercase tracking-wider mb-4" style={{ color: 'var(--text-muted)' }}>
                                    Active Selection
                                </h3>

                                {selected ? (
                                    <div className="animate-fade-in">
                                        <p className="text-lg font-bold leading-tight mb-2" style={{ color: 'var(--text-heading)' }}>
                                            {selected.name}
                                        </p>
                                        <div className="space-y-2 mt-4 text-sm" style={{ color: 'var(--text-body)' }}>
                                            <div className="flex justify-between py-2 border-b" style={{ borderColor: 'var(--border)' }}>
                                                <span className="font-medium">Citation Style</span>
                                                <span className="font-mono">{selected.citation_style || 'Default'}</span>
                                            </div>
                                            <div className="flex justify-between py-2 border-b" style={{ borderColor: 'var(--border)' }}>
                                                <span className="font-medium">Layout</span>
                                                <span className="font-mono">{selected.two_column ? '2-Column' : '1-Column'}</span>
                                            </div>
                                        </div>

                                        <button className="btn-primary w-full mt-6" onClick={() => onSelect(selected)}>
                                            Start Formatting Engine <ArrowRight className="w-4 h-4 ml-1" />
                                        </button>
                                    </div>
                                ) : (
                                    <div className="text-center py-8">
                                        <Type className="w-8 h-8 mx-auto mb-3 opacity-20" />
                                        <p className="text-sm" style={{ color: 'var(--text-faint)' }}>Select an output format from the list to continue.</p>
                                    </div>
                                )}
                            </div>

                            <div className="mt-6 text-center">
                                <button onClick={onBack} className="text-sm font-medium hover:underline" style={{ color: 'var(--text-muted)' }}>
                                    Change Uploaded File
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
