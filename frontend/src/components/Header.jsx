import { Sun, Moon, BookMarked, Check } from 'lucide-react';
import { useState, useEffect } from 'react';

const STEPS = [
    { num: 1, label: 'Upload' },
    { num: 2, label: 'Configure' },
    { num: 3, label: 'Processing' },
    { num: 4, label: 'Results' },
];

export default function Header({ currentStep }) {
    const [theme, setTheme] = useState(localStorage.getItem('theme') || 'light');

    useEffect(() => {
        document.documentElement.setAttribute('data-theme', theme);
        localStorage.setItem('theme', theme);
    }, [theme]);

    const toggleTheme = () => setTheme(theme === 'light' ? 'dark' : 'light');

    return (
        <header className="sticky top-0 z-50 transition-colors duration-300 backdrop-blur-md bg-white/80"
            style={{ borderBottom: '1px solid var(--border)' }}>
            <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">

                {/* Logo */}
                <div className="flex items-center gap-3">
                    <div className="w-8 h-8 rounded-lg flex items-center justify-center bg-indigo-600 shadow-sm" style={{ background: 'var(--primary)' }}>
                        <BookMarked className="w-4 h-4 text-white" />
                    </div>
                    <div>
                        <h1 className="text-base font-bold tracking-tight" style={{ color: 'var(--text-heading)' }}>
                            Magnetic Manuscript
                        </h1>
                    </div>
                </div>

                {/* Stepper (SaaS style) */}
                <div className="hidden md:flex items-center gap-8">
                    {STEPS.map((step, idx) => {
                        const isPast = currentStep > step.num;
                        const isCurrent = currentStep === step.num;
                        const isFuture = currentStep < step.num;

                        return (
                            <div key={step.num} className="flex items-center gap-3">
                                <div
                                    className={`w-6 h-6 rounded-full flex items-center justify-center text-[11px] font-bold transition-all
                    ${isCurrent ? 'ring-4 ring-indigo-50/50' : ''}
                  `}
                                    style={{
                                        background: isPast ? 'var(--primary)' : isCurrent ? 'var(--primary)' : 'var(--bg-muted)',
                                        color: isPast || isCurrent ? '#FFFFFF' : 'var(--text-muted)'
                                    }}
                                >
                                    {isPast ? <Check className="w-3.5 h-3.5" /> : step.num}
                                </div>
                                <span
                                    className={`text-sm font-semibold ${isCurrent ? '' : 'text-slate-400'}`}
                                    style={{ color: isCurrent ? 'var(--text-heading)' : 'var(--text-muted)' }}
                                >
                                    {step.label}
                                </span>

                                {idx < STEPS.length - 1 && (
                                    <div className="w-10 h-[1.5px] ml-5 rounded"
                                        style={{ background: isPast ? 'var(--primary)' : 'var(--border)' }} />
                                )}
                            </div>
                        );
                    })}
                </div>

                {/* Theme Toggle */}
                <button
                    onClick={toggleTheme}
                    className="p-2 rounded-md hover:bg-slate-100 transition-colors"
                    style={{ color: 'var(--text-muted)' }}
                    title={theme === 'light' ? 'Switch to Dark Mode' : 'Switch to Light Mode'}
                >
                    {theme === 'light' ? <Moon className="w-4 h-4" /> : <Sun className="w-4 h-4" />}
                </button>

            </div>
        </header>
    );
}
