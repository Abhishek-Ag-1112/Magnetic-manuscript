import { useState, useCallback } from 'react';
import { UploadCloud, FileText, CheckCircle2, Bot, Sliders, Zap, ShieldCheck } from 'lucide-react';

const FEATURES = [
    { icon: Bot, title: '8 Specialized AI Agents', desc: 'A sophisticated pipeline of context-aware workers analyzing your manuscript.' },
    { icon: ShieldCheck, title: 'Journal Compliance', desc: '100% adherence to complex rulesets for IEEE, Springer, ACM, and tailored DOIs.' },
    { icon: Zap, title: 'Real-Time Telemetry', desc: 'Watch the formatting engine work via live WebSockets showing exact operations.' },
    { icon: Sliders, title: 'Multi-Format Build', desc: 'Generate publish-ready Word Documents, PDFs, and raw LaTeX source files.' },
];

export default function UploadPage({ onUpload, error }) {
    const [isDragging, setIsDragging] = useState(false);
    const [file, setFile] = useState(null);

    const handleDrag = useCallback((e) => {
        e.preventDefault();
        e.stopPropagation();
        if (e.type === 'dragenter' || e.type === 'dragover') setIsDragging(true);
        else if (e.type === 'dragleave') setIsDragging(false);
    }, []);

    const handleDrop = useCallback((e) => {
        e.preventDefault();
        e.stopPropagation();
        setIsDragging(false);
        if (e.dataTransfer.files && e.dataTransfer.files[0]) {
            setFile(e.dataTransfer.files[0]);
        }
    }, []);

    const handleFileChange = (e) => {
        if (e.target.files && e.target.files[0]) {
            setFile(e.target.files[0]);
        }
    };

    const handleUploadClick = () => {
        if (file && onUpload) onUpload(file);
    };

    return (
        <div className="max-w-[1400px] mx-auto px-6 py-12 md:py-20 animate-fade-in relative ext-layout">

            {/* 2-Column Dashboard Layout */}
            <div className="grid lg:grid-cols-12 gap-16 lg:gap-24 items-center">

                {/* Left Col: Copy & Features (5 columns) */}
                <div className="lg:col-span-5 text-left space-y-12">
                    <div>
                        <div className="inline-flex items-center gap-2 px-4 py-1.5 rounded-none border-2 border-indigo-600 bg-indigo-50 text-indigo-600 font-black text-xs uppercase tracking-widest mb-8 shadow-[4px_4px_0px_#4F46E5] translate-x-1 -translate-y-1">
                            <Zap className="w-4 h-4" /> Next-Gen Formatting
                        </div>
                        <h1 className="text-5xl lg:text-7xl font-black tracking-tighter text-slate-900 leading-[1.05] mb-6">
                            Format your <br />manuscript <br />
                            <span className="text-indigo-600 border-b-4 border-indigo-600 pb-1">instantly.</span>
                        </h1>
                        <p className="text-lg text-slate-600 font-medium leading-relaxed">
                            Stop wasting hours on manual formatting. Upload your research document, and our AI pipeline will restructure, rewrite, and cite it to meet strict publication guidelines automatically.
                        </p>
                    </div>

                    <div className="grid gap-6">
                        {FEATURES.map((feat, i) => (
                            <div key={i} className="flex gap-5 items-start p-4 border-2 border-slate-200 bg-white hover:border-indigo-600 transition-colors group">
                                <div className="w-12 h-12 flex flex-shrink-0 items-center justify-center border-2 border-indigo-600 bg-indigo-50 text-indigo-600 group-hover:bg-indigo-600 group-hover:text-white transition-colors">
                                    <feat.icon className="w-5 h-5" />
                                </div>
                                <div>
                                    <h3 className="text-sm font-black text-slate-900 mb-1">{feat.title}</h3>
                                    <p className="text-xs text-slate-500 font-medium leading-relaxed">{feat.desc}</p>
                                </div>
                            </div>
                        ))}
                    </div>
                </div>

                {/* Right Col: Interactive Upload Dropzone (7 columns) */}
                <div className="lg:col-span-7 w-full border-2 border-slate-900 bg-white p-2 shadow-[12px_12px_0px_#0F172A] relative">
                    <div className="absolute top-2 right-2 flex gap-1.5 p-2">
                        <div className="w-2.5 h-2.5 rounded-full border-2 border-slate-900 bg-red-400"></div>
                        <div className="w-2.5 h-2.5 rounded-full border-2 border-slate-900 bg-yellow-400"></div>
                        <div className="w-2.5 h-2.5 rounded-full border-2 border-slate-900 bg-emerald-400"></div>
                    </div>

                    <div className="p-4 border-b-2 border-slate-900 mb-2">
                        <h3 className="text-sm font-black uppercase tracking-widest text-slate-900">Input Source</h3>
                    </div>

                    <div
                        className={`w-full h-[500px] flex flex-col items-center justify-center p-12 text-center transition-all border-4 border-dashed ${isDragging
                            ? 'border-indigo-600 bg-indigo-50 scale-[0.98]'
                            : 'border-slate-300 bg-slate-50 hover:bg-slate-100 hover:border-slate-400'
                            }`}
                        onDragEnter={handleDrag}
                        onDragLeave={handleDrag}
                        onDragOver={handleDrag}
                        onDrop={handleDrop}
                    >
                        <input
                            type="file"
                            className="hidden"
                            id="file-upload"
                            onChange={handleFileChange}
                            accept=".txt,.md,.pdf,.docx"
                        />

                        {!file ? (
                            <>
                                <div className="w-24 h-24 flex items-center justify-center mb-8 border-4 border-slate-900 bg-white shadow-[6px_6px_0px_#0F172A]">
                                    <UploadCloud className="w-10 h-10 text-indigo-600" />
                                </div>
                                <h3 className="text-3xl font-black text-slate-900 mb-4 tracking-tight">
                                    Upload Manuscript
                                </h3>
                                <p className="text-slate-500 font-medium mb-10 text-lg">
                                    Drag & drop your file here, or click to browse
                                </p>

                                <div className="flex gap-3 mb-12">
                                    {['.DOCX', '.PDF', '.TXT', '.MD'].map(ext => (
                                        <span key={ext} className="px-3 py-1 text-xs font-black rounded-none bg-slate-200 text-slate-600 border-2 border-slate-300 tracking-widest">
                                            {ext}
                                        </span>
                                    ))}
                                </div>

                                <label htmlFor="file-upload" className="px-8 py-4 bg-indigo-600 text-white font-black uppercase tracking-widest text-sm border-2 border-slate-900 shadow-[4px_4px_0px_#0F172A] hover:translate-y-1 hover:translate-x-1 hover:shadow-none transition-all cursor-pointer">
                                    Select Local File
                                </label>
                            </>
                        ) : (
                            <div className="flex flex-col items-center w-full max-w-md animate-fade-in">
                                <FileText className="w-16 h-16 text-indigo-600 mb-6" />
                                <div className="w-full bg-white border-2 border-slate-900 p-6 mb-10 shadow-[6px_6px_0px_#0F172A] text-left">
                                    <p className="text-xs font-black uppercase tracking-widest text-slate-400 mb-2">Selected File</p>
                                    <div className="flex items-center justify-between">
                                        <div className="flex-1 min-w-0 pr-4">
                                            <p className="text-lg font-black truncate text-slate-900" title={file.name}>
                                                {file.name}
                                            </p>
                                            <p className="text-sm font-medium mt-1 text-slate-500">
                                                {(file.size / 1024 / 1024).toFixed(2)} MB • Ready for processing
                                            </p>
                                        </div>
                                        <div className="w-8 h-8 rounded-full bg-emerald-100 flex items-center justify-center shrink-0 border-2 border-emerald-500">
                                            <CheckCircle2 className="w-5 h-5 text-emerald-600" />
                                        </div>
                                    </div>
                                </div>

                                <div className="flex gap-4 w-full">
                                    <button
                                        className="flex-1 px-6 py-4 bg-white text-slate-900 font-black uppercase tracking-widest text-xs border-2 border-slate-900 shadow-[4px_4px_0px_#0F172A] hover:translate-y-1 hover:translate-x-1 hover:shadow-none transition-all"
                                        onClick={() => setFile(null)}
                                    >
                                        Change File
                                    </button>
                                    <button
                                        className="flex-1 px-6 py-4 bg-indigo-600 text-white font-black uppercase tracking-widest text-xs border-2 border-slate-900 shadow-[4px_4px_0px_#0F172A] hover:translate-y-1 hover:translate-x-1 hover:shadow-none transition-all flex items-center justify-center gap-2 group"
                                        onClick={handleUploadClick}
                                    >
                                        Init Pipeline <Zap className="w-4 h-4 group-hover:scale-125 transition-transform" />
                                    </button>
                                </div>
                            </div>
                        )}
                    </div>

                    {error && (
                        <div className="p-4 border-2 border-red-600 bg-red-50 text-red-700 font-bold text-sm mt-2">
                            ⚠ {error}
                        </div>
                    )}
                </div>

            </div>
        </div>
    );
}
