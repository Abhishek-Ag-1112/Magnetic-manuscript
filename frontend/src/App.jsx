import { useState, useRef } from 'react';
import Header from './components/Header';
import UploadPage from './pages/UploadPage';
import JournalSelectionPage from './pages/JournalSelectionPage';
import ProcessingPage from './pages/ProcessingPage';
import ResultsPage from './pages/ResultsPage';
import { uploadFile, processManuscriptStream } from './api';

export default function App() {
  const [currentStep, setCurrentStep] = useState(1);
  const [sessionId, setSessionId] = useState(null);
  const [fileName, setFileName] = useState('');
  const [selectedJournal, setSelectedJournal] = useState(null);
  const [result, setResult] = useState(null);
  const [uploadError, setUploadError] = useState('');

  const [agentEvents, setAgentEvents] = useState([]);
  const [pipelineStatus, setPipelineStatus] = useState('idle');
  const abortRef = useRef(null);

  const handleUpload = async (file) => {
    try {
      setUploadError('');
      const data = await uploadFile(file);
      setSessionId(data.session_id);
      setFileName(data.file_name);
      setCurrentStep(2);
    } catch (err) {
      setUploadError(err.message || 'Upload failed. Please try again.');
    }
  };

  const handleJournalSelect = (selection) => {
    setSelectedJournal(selection);
    setCurrentStep(3);
    setAgentEvents([]);
    setPipelineStatus('running');

    const journalName = selection.selectionType === 'journal' ? selection.id : null;
    const familyName = selection.selectionType === 'family' ? selection.id : null;

    // Use WebSocket streaming for real-time progress
    const abort = processManuscriptStream(sessionId, journalName, familyName, {
      onPipelineStart: (data) => {
        setAgentEvents((prev) => [...prev, { type: 'pipeline_start', data }]);
      },
      onAgentStart: (data) => {
        setAgentEvents((prev) => [...prev, { type: 'agent_start', data }]);
      },
      onAgentComplete: (data) => {
        setAgentEvents((prev) => [...prev, { type: 'agent_complete', data }]);
      },
      onPipelineComplete: (data) => {
        setAgentEvents((prev) => [...prev, { type: 'pipeline_complete', data }]);
        setPipelineStatus('complete');
      },
      onResult: (data) => {
        setResult(data);
        setTimeout(() => setCurrentStep(4), 2000);
      },
      onError: (data) => {
        setPipelineStatus('error');
        setResult({
          status: 'error',
          compliance_report: { score: 0, violations: [], warnings: [], summary: 'Processing failed.' },
          errors: [data?.error || 'Processing failed. Check API logs.'],
        });
        setTimeout(() => setCurrentStep(4), 2000);
      },
    });

    abortRef.current = abort;
  };

  const handleReset = () => {
    if (abortRef.current) abortRef.current();
    setCurrentStep(1);
    setSessionId(null);
    setFileName('');
    setSelectedJournal(null);
    setResult(null);
    setUploadError('');
    setAgentEvents([]);
    setPipelineStatus('idle');
  };

  const handleBack = () => {
    if (currentStep > 1) setCurrentStep(currentStep - 1);
  };

  return (
    <div className="min-h-screen flex flex-col font-sans text-body transition-colors duration-300" style={{ background: 'var(--bg-page)' }}>
      <Header currentStep={currentStep} />

      <main className="flex-1 w-full relative">
        {currentStep === 1 && <UploadPage onUpload={handleUpload} error={uploadError} />}
        {currentStep === 2 && <JournalSelectionPage onSelect={handleJournalSelect} onBack={handleBack} />}
        {currentStep === 3 && (
          <ProcessingPage
            fileName={fileName}
            journalName={selectedJournal?.name || ''}
            agentEvents={agentEvents}
            pipelineStatus={pipelineStatus}
          />
        )}
        {currentStep === 4 && <ResultsPage result={result} sessionId={sessionId} onReset={handleReset} />}
      </main>

      <footer className="py-8 text-center" style={{ borderTop: '1px solid var(--border)' }}>
        <p className="text-sm font-medium" style={{ color: 'var(--text-muted)' }}>
          Magnetic Manuscript — Academic Formatting Engine
        </p>
      </footer>
    </div>
  );
}
