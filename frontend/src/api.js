/**
 * Magnetic Manuscript — API Client
 * Handles all backend communication including SSE streaming.
 */
const API_URL = import.meta.env.VITE_API_URL || '';

// ── FILE UPLOAD ──

export async function uploadFile(file) {
  const formData = new FormData();
  formData.append('file', file);

  const res = await fetch(`${API_URL}/api/upload`, {
    method: 'POST',
    body: formData,
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Upload failed');
  }

  return res.json();
}


// ── JOURNAL & FAMILY LISTS ──

export async function fetchJournals() {
  const res = await fetch(`${API_URL}/api/journals`);
  if (!res.ok) throw new Error('Failed to fetch journals');
  const data = await res.json();
  // Backend returns a raw array; wrap it for the frontend
  return Array.isArray(data) ? { journals: data } : data;
}

export async function fetchFamilies() {
  const res = await fetch(`${API_URL}/api/families`);
  if (!res.ok) throw new Error('Failed to fetch families');
  const data = await res.json();
  // Backend returns a raw array; wrap it for the frontend
  return Array.isArray(data) ? { families: data } : data;
}

export async function fetchJournalDetails(journalId) {
  const res = await fetch(`${API_URL}/api/journals/${journalId}`);
  if (!res.ok) throw new Error('Failed to fetch journal details');
  return res.json();
}

// Aliases used by JournalSelectionPage
export const getJournals = fetchJournals;
export const getFamilies = fetchFamilies;


// ── STANDARD PROCESSING (non-streaming) ──

export async function processManuscript(sessionId, journalName = null, familyName = null) {
  const body = { session_id: sessionId };
  if (journalName) body.journal_name = journalName;
  if (familyName) body.family_name = familyName;

  const res = await fetch(`${API_URL}/api/process`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Processing failed');
  }

  return res.json();
}


export function processManuscriptStream(sessionId, journalName, familyName, callbacks = {}) {
  // Parse the API_URL properly to construct the WebSocket URL.
  // E.g., if API_URL is "http://localhost:8000", wsUrl becomes "ws://localhost:8000/api/process/ws/..."
  const baseUrl = new URL(API_URL || window.location.origin);
  const wsProtocol = baseUrl.protocol === 'https:' ? 'wss:' : 'ws:';
  const wsHost = baseUrl.host; // e.g., "localhost:8000"

  const queryParams = new URLSearchParams();
  if (journalName) queryParams.append('journal', journalName);
  if (familyName) queryParams.append('family', familyName);

  const wsUrl = `${wsProtocol}//${wsHost}/api/process/ws/${sessionId}?${queryParams.toString()}`;

  const ws = new WebSocket(wsUrl);
  let isAborted = false;

  ws.onopen = () => {
    console.log('WebSocket connected for session:', sessionId, 'at', wsUrl);
  };

  let pipelineFinished = false;

  ws.onmessage = (event) => {
    if (isAborted) return;
    try {
      const msg = JSON.parse(event.data);
      const { type, data } = msg;

      switch (type) {
        case 'pipeline_start':
          callbacks.onPipelineStart?.(data);
          break;
        case 'agent_start':
          callbacks.onAgentStart?.(data);
          break;
        case 'agent_complete':
          callbacks.onAgentComplete?.(data);
          break;
        case 'pipeline_complete':
          callbacks.onPipelineComplete?.(data);
          break;
        case 'result':
          pipelineFinished = true;
          callbacks.onResult?.(data);
          ws.close();
          break;
        case 'error':
          pipelineFinished = true;
          callbacks.onError?.(data);
          ws.close();
          break;
      }
    } catch (err) {
      console.warn('WS parse error:', err);
    }
  };

  ws.onerror = (err) => {
    if (!isAborted) callbacks.onError?.({ error: 'WebSocket connection error' });
  };

  ws.onclose = () => {
    console.log('WebSocket closed');
    // If socket closed before pipeline finished, treat as error
    if (!isAborted && !pipelineFinished) {
      callbacks.onError?.({ error: 'Connection lost. The server may have restarted.' });
    }
  };

  // Return abort function
  return () => {
    isAborted = true;
    if (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING) {
      ws.close();
    }
  };
}


// ── STATUS CHECK ──

export async function checkStatus(sessionId) {
  const res = await fetch(`${API_URL}/api/status/${sessionId}`);
  if (!res.ok) throw new Error('Failed to check status');
  return res.json();
}


// ── DOWNLOAD URLS ──

export function getDownloadUrl(sessionId, format = 'docx') {
  return `${API_URL}/api/download/${sessionId}/${format}`;
}
