import React, { useState } from 'react';
import { usePersona } from '../context';
import { Bot, FileText, LogOut, Send, Sparkles, Upload, User } from 'lucide-react';
import {
  analyticsService,
  type AssistantChatResponse,
  type CommercialExecutionTraceEvent,
  type CommercialWorkflowResponse,
  type UploadedRagDocument,
} from '../services/analyticsService';
import { ApiClientError, type ApiCredentials } from '../services/apiClient';

interface ChatMessage {
  id: string;
  sender: 'user' | 'assistant';
  text: string;
  timestamp: string;
  response?: CommercialWorkflowResponse;
  executionTrace?: CommercialExecutionTraceEvent[];
}

function getErrorExecutionTrace(error: unknown): CommercialExecutionTraceEvent[] {
  if (
    !(error instanceof ApiClientError)
    || typeof error.details !== 'object'
    || error.details === null
  ) {
    return [];
  }
  const trace = (error.details as { execution_trace?: unknown }).execution_trace;
  if (!Array.isArray(trace)) return [];
  return trace.filter((event): event is CommercialExecutionTraceEvent => {
    if (typeof event !== 'object' || event === null) return false;
    const candidate = event as Partial<CommercialExecutionTraceEvent>;
    return (
      typeof candidate.node_id === 'string'
      && ['completed', 'warning', 'error'].includes(candidate.status ?? '')
      && typeof candidate.duration_ms === 'number'
    );
  });
}

function ExecutionTrace({
  events,
}: {
  events: CommercialExecutionTraceEvent[];
}) {
  if (events.length === 0) return null;
  const hasIssue = events.some((event) => event.status !== 'completed');
  return (
    <details
      open={hasIssue}
      style={{ borderTop: '1px solid var(--gv-border-subtle)', paddingTop: '0.55rem' }}
    >
      <summary style={{ cursor: 'pointer', fontWeight: 700 }}>
        LangGraph orchestration · {events.length} steps{hasIssue ? ' · attention needed' : ''}
      </summary>
      <ol style={{ display: 'grid', gap: '0.4rem', paddingLeft: '1.4rem', marginBottom: 0 }}>
        {events.map((event, index) => (
          <li key={`${event.node_id}-${index}`}>
            <strong>{event.node_id.replace(/_/g, ' ')}</strong>
            {' — '}
            {event.status}
            {' · '}
            {event.duration_ms.toFixed(1)} ms
            {event.message && (
              <p style={{
                margin: '0.2rem 0 0',
                color: event.status === 'completed'
                  ? 'var(--gv-text-secondary)'
                  : '#b42318',
              }}>
                {event.message}
              </p>
            )}
          </li>
        ))}
      </ol>
    </details>
  );
}

const DEMO_SCHEDULE = JSON.stringify(
  {
    horizon_hours: 4,
    prices_inr_per_kwh: [12, 8, 7, 10],
    jobs: [
      {
        job_id: 'press-01',
        machine_id: 'press',
        power_kw: 30,
        duration_hours: 1,
        release_hour: 0,
        deadline_hour: 4,
      },
      {
        job_id: 'cnc-01',
        machine_id: 'cnc',
        power_kw: 20,
        duration_hours: 2,
        release_hour: 0,
        deadline_hour: 4,
      },
    ],
    demand_limit_kw: 45,
    maintenance_windows: [{ machine_id: 'press', start_hour: 0, end_hour: 1 }],
    battery: {
      capacity_kwh: 40,
      initial_soc_kwh: 20,
      min_soc_kwh: 5,
      terminal_soc_kwh: 10,
      max_charge_kw: 10,
      max_discharge_kw: 10,
      charge_efficiency: 0.95,
      discharge_efficiency: 0.95,
    },
  },
  null,
  2,
);

function errorMessage(error: unknown): string {
  if (error instanceof ApiClientError && error.status === 401) {
    return 'The demo user ID or password is incorrect.';
  }
  if (
    error instanceof ApiClientError
    && error.status === 422
    && Array.isArray(error.details)
  ) {
    const issues = error.details
      .map((issue) => {
        if (typeof issue !== 'object' || issue === null) return '';
        const detail = issue as { loc?: unknown[]; msg?: unknown };
        const location = Array.isArray(detail.loc)
          ? detail.loc.map(String).join('.')
          : '';
        const message = typeof detail.msg === 'string' ? detail.msg : '';
        return [location, message].filter(Boolean).join(': ');
      })
      .filter(Boolean);
    if (issues.length > 0) {
      return `Please check the request details: ${issues.join('; ')}`;
    }
  }
  if (error instanceof ApiClientError && error.requestId) {
    return `${error.message} (Request ID: ${error.requestId})`;
  }
  return error instanceof Error ? error.message : 'An unexpected error occurred.';
}

const CommercialAssistantPage: React.FC = () => {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [credentials, setCredentials] = useState<ApiCredentials | null>(null);
  const [loginError, setLoginError] = useState('');
  const [isSigningIn, setIsSigningIn] = useState(false);
  const [inputPrompt, setInputPrompt] = useState('');
  const [scheduleJson, setScheduleJson] = useState('');
  const [scheduleError, setScheduleError] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadMessage, setUploadMessage] = useState('');
  const [uploadedDocuments, setUploadedDocuments] = useState<UploadedRagDocument[]>([]);
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: 'init-1',
      sender: 'assistant',
      text: 'Sign in with the locally configured demo account to use the master agent and shared document knowledge base.',
      timestamp: 'Just now',
    },
  ]);

  const prompts = [
    'What production constraints and maintenance windows are in the demo knowledge base?',
    'Estimate 5 kW rooftop solar generation, cost, payback, and peak-demand impact in Bengaluru.',
    'Optimize the production schedule using the supplied schedule data.',
    'What information is available about factory energy operations?',
  ];

  const handleLogin = async (event: React.FormEvent) => {
    event.preventDefault();
    setLoginError('');
    setIsSigningIn(true);
    const newCredentials = { username: username.trim(), password };
    try {
      await analyticsService.validateCommercialSession(newCredentials);
      setCredentials(newCredentials);
      setPassword('');
      setMessages([
        {
          id: `init-${Date.now()}`,
          sender: 'assistant',
          text: 'You are connected to the automotive-parts demo master agent. Ask about operations, renewable scenarios, or cost optimization; uploaded files are indexed into the shared RAG knowledge base.',
          timestamp: 'Just now',
        },
      ]);
      try {
        const ragData = await analyticsService.getCommercialRagDocuments(newCredentials);
        setUploadedDocuments(ragData.documents);
      } catch (error) {
        setUploadMessage(`Connected, but the document list could not be loaded: ${errorMessage(error)}`);
      }
    } catch (error) {
      setLoginError(errorMessage(error));
    } finally {
      setIsSigningIn(false);
    }
  };

  const handleSignOut = () => {
    setCredentials(null);
    setPassword('');
    setUsername('');
    setUploadedDocuments([]);
    setUploadMessage('');
    setMessages([
      {
        id: `signed-out-${Date.now()}`,
        sender: 'assistant',
        text: 'You have signed out. Sign in again to continue using the master agent.',
        timestamp: 'Just now',
      },
    ]);
  };

  const handleSend = async (text: string) => {
    if (!text.trim() || !credentials || isTyping) return;

    const trimmed = text.trim();
    const requestsOptimization = /\b(?:optimi[sz](?:e|ation|ing)?|scheduling|schedule|reschedule|dispatch)\b/i
      .test(trimmed);
    let optimizationInputs: Record<string, unknown> | undefined;
    if (scheduleJson.trim() && requestsOptimization) {
      try {
        const parsed: unknown = JSON.parse(scheduleJson);
        if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) {
          throw new Error('Schedule inputs must be a JSON object.');
        }
        optimizationInputs = parsed as Record<string, unknown>;
      } catch (error) {
        setScheduleError(
          error instanceof Error ? error.message : 'Schedule JSON is invalid.',
        );
        return;
      }
    }
    setScheduleError('');

    const userMsg: ChatMessage = {
      id: `usr-${Date.now()}`,
      sender: 'user',
      text: trimmed,
      timestamp: 'Just now',
    };
    setMessages((previous) => [...previous, userMsg]);
    setInputPrompt('');
    setIsTyping(true);

    try {
      const response = await analyticsService.askCommercialAssistant(
        trimmed,
        credentials,
        optimizationInputs,
      );
      if (response.execution_trace.length > 0) {
        console.info('LangGraph execution trace', {
          requestId: response.request_id,
          steps: response.execution_trace,
        });
      }
      setMessages((previous) => [
        ...previous,
        {
          id: `ast-${Date.now()}`,
          sender: 'assistant',
          text: response.summary,
          timestamp: 'Just now',
          response,
        },
      ]);
      if (optimizationInputs) setScheduleJson('');
    } catch (error) {
      const executionTrace = getErrorExecutionTrace(error);
      if (executionTrace.length > 0) {
        console.info('LangGraph execution trace', { steps: executionTrace });
      }
      setMessages((previous) => [
        ...previous,
        {
          id: `ast-${Date.now()}`,
          sender: 'assistant',
          text: `The master workflow could not complete this request: ${errorMessage(error)}`,
          timestamp: 'Just now',
          executionTrace,
        },
      ]);
    } finally {
      setIsTyping(false);
    }
  };

  const handleUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.currentTarget.files?.[0];
    event.currentTarget.value = '';
    if (!file || !credentials) return;
    setIsUploading(true);
    setUploadMessage('');
    try {
      const indexed = await analyticsService.uploadCommercialRagDocument(
        file,
        credentials,
      );
      setUploadMessage(`${file.name} uploaded and indexed for shared RAG retrieval.`);
      setMessages((previous) => [
        ...previous,
        {
          id: `upload-${Date.now()}`,
          sender: 'assistant',
          text: `Document indexed successfully: ${indexed.source_id} (${indexed.chunk_count ?? 0} searchable passages).`,
          timestamp: 'Just now',
        },
      ]);
      try {
        const ragData = await analyticsService.getCommercialRagDocuments(credentials);
        setUploadedDocuments(ragData.documents);
      } catch (error) {
        setUploadMessage(`Document was indexed, but the list could not be refreshed: ${errorMessage(error)}`);
      }
    } catch (error) {
      setUploadMessage(errorMessage(error));
    } finally {
      setIsUploading(false);
    }
  };

  const decideProposal = async (
    messageId: string,
    proposalId: string,
    decision: 'approved' | 'rejected',
  ) => {
    if (!credentials) return;
    try {
      const result = await analyticsService.decideScheduleProposal(
        proposalId,
        decision,
        credentials,
      );
      setMessages((previous) =>
        previous.map((message) =>
          message.id === messageId && message.response?.schedule_proposal
            ? {
                ...message,
                response: {
                  ...message.response,
                  schedule_proposal: {
                    ...message.response.schedule_proposal,
                    status: result.status,
                  },
                },
              }
            : message,
        ),
      );
    } catch (error) {
      setMessages((previous) => [
        ...previous,
        {
          id: `approval-error-${Date.now()}`,
          sender: 'assistant',
          text: `The proposal decision was not recorded: ${errorMessage(error)}`,
          timestamp: 'Just now',
        },
      ]);
    }
  };

  const surfaceStyle: React.CSSProperties = {
    background: 'var(--gv-bg-surface)',
    border: '1px solid var(--gv-border-subtle)',
    borderRadius: 'var(--gv-radius-lg)',
    padding: '1.25rem',
    boxShadow: 'var(--gv-shadow-sm)',
  };
  const fieldStyle: React.CSSProperties = {
    width: '100%',
    padding: '0.75rem',
    borderRadius: 'var(--gv-radius-md)',
    border: '1px solid var(--gv-border-accent)',
    background: 'var(--gv-bg-surface)',
    color: 'var(--gv-text-primary)',
    fontSize: '0.88rem',
    boxSizing: 'border-box',
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem', maxWidth: '1000px', margin: '0 auto', width: '100%' }}>
      <header style={surfaceStyle}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '1rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
            <div style={{ width: 42, height: 42, borderRadius: 'var(--gv-radius-md)', background: 'linear-gradient(135deg, var(--gv-color-smart-teal), var(--gv-color-grid-blue))', display: 'grid', placeItems: 'center' }}>
              <Bot size={23} color="#FFFFFF" />
            </div>
            <div>
              <h2 style={{ fontSize: '1.3rem', fontWeight: 800, color: 'var(--gv-color-midnight-navy)', margin: 0 }}>
                GridVision Master Agent
              </h2>
              <p style={{ fontSize: '0.82rem', color: 'var(--gv-text-secondary)', margin: '0.25rem 0 0' }}>
                LLM-assisted routing · operations · renewables · forecasts · cost optimization · shared RAG
              </p>
            </div>
          </div>
          {credentials && (
            <button type="button" onClick={handleSignOut} style={{ ...fieldStyle, width: 'auto', display: 'flex', alignItems: 'center', gap: '0.4rem', cursor: 'pointer' }}>
              <LogOut size={15} /> Sign out
            </button>
          )}
        </div>
        <p style={{ fontSize: '0.78rem', lineHeight: 1.5, color: 'var(--gv-text-muted)', margin: '0.9rem 0 0' }}>
          Fixed scope: automotive-parts demonstration factory. Demo sign-in is not production authentication; schedule decisions are audit records only and never control equipment.
        </p>
      </header>

      {!credentials ? (
        <form onSubmit={handleLogin} style={{ ...surfaceStyle, display: 'grid', gap: '0.8rem', maxWidth: '480px', width: '100%', alignSelf: 'center', boxSizing: 'border-box' }}>
          <h3 style={{ margin: 0, color: 'var(--gv-text-primary)' }}>Demo sign-in</h3>
          <label style={{ display: 'grid', gap: '0.35rem', color: 'var(--gv-text-secondary)', fontSize: '0.82rem' }}>
            Demo user ID
            <input autoComplete="username" value={username} onChange={(event) => setUsername(event.target.value)} style={fieldStyle} required />
          </label>
          <label style={{ display: 'grid', gap: '0.35rem', color: 'var(--gv-text-secondary)', fontSize: '0.82rem' }}>
            Password
            <input type="password" autoComplete="current-password" value={password} onChange={(event) => setPassword(event.target.value)} style={fieldStyle} required />
          </label>
          {loginError && <p role="alert" style={{ color: '#b42318', margin: 0, fontSize: '0.82rem' }}>{loginError}</p>}
          <button type="submit" disabled={isSigningIn} style={{ ...fieldStyle, background: 'var(--gv-color-smart-teal)', color: '#fff', fontWeight: 700, cursor: isSigningIn ? 'wait' : 'pointer' }}>
            {isSigningIn ? 'Connecting…' : 'Sign in'}
          </button>
          <p style={{ fontSize: '0.75rem', color: 'var(--gv-text-muted)', margin: 0 }}>
            Credentials are held in memory for this page session and sent only to the configured GridVision API.
          </p>
        </form>
      ) : (
        <>
          <section style={{ ...surfaceStyle, display: 'grid', gap: '0.75rem' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '1rem', flexWrap: 'wrap' }}>
              <div>
                <h3 style={{ margin: '0 0 0.25rem', fontSize: '0.95rem', color: 'var(--gv-text-primary)' }}>Shared RAG documents</h3>
                <p style={{ margin: 0, fontSize: '0.76rem', color: 'var(--gv-text-muted)' }}>PDF, MD, TXT, DOCX, PPTX, XLSX, HTML, and CSV · max 25 MB per file</p>
              </div>
              <label style={{ display: 'inline-flex', alignItems: 'center', gap: '0.45rem', padding: '0.65rem 0.9rem', borderRadius: 'var(--gv-radius-md)', background: 'var(--gv-color-grid-blue)', color: '#fff', fontWeight: 700, fontSize: '0.82rem', cursor: isUploading ? 'wait' : 'pointer' }}>
                <Upload size={15} /> {isUploading ? 'Uploading and indexing…' : 'Upload document'}
                <input type="file" accept=".pdf,.md,.txt,.docx,.pptx,.xlsx,.html,.csv" disabled={isUploading} onChange={handleUpload} style={{ display: 'none' }} />
              </label>
            </div>
            {uploadMessage && <p role="status" style={{ margin: 0, fontSize: '0.8rem', color: uploadMessage.includes('indexed') ? 'var(--gv-color-smart-teal)' : '#b42318' }}>{uploadMessage}</p>}
            {uploadedDocuments.length > 0 ? (
              <ul style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem', margin: 0, padding: 0, listStyle: 'none' }}>
                {uploadedDocuments.map((document) => (
                  <li key={document.source_id} style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', padding: '0.4rem 0.65rem', borderRadius: '999px', background: 'var(--gv-bg-surface-subtle)', color: 'var(--gv-text-secondary)', fontSize: '0.75rem' }}>
                    <FileText size={13} /> {document.source_id}
                  </li>
                ))}
              </ul>
            ) : (
              <p style={{ margin: 0, fontSize: '0.78rem', color: 'var(--gv-text-muted)' }}>No uploaded documents yet. Files are indexed locally and become available to all workflow queries.</p>
            )}
          </section>

          <section>
            <div style={{ fontSize: '0.72rem', fontWeight: 700, textTransform: 'uppercase', color: 'var(--gv-text-muted)', letterSpacing: '0.05em', marginBottom: '0.5rem' }}>
              Ask the master agent
            </div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem' }}>
              {prompts.map((prompt) => (
                <button key={prompt} type="button" onClick={() => handleSend(prompt)} disabled={isTyping} style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', padding: '0.45rem 0.75rem', borderRadius: '999px', background: 'var(--gv-bg-surface)', border: '1px solid var(--gv-border-accent)', fontSize: '0.75rem', fontWeight: 600, color: 'var(--gv-text-primary)', cursor: 'pointer' }}>
                  <Sparkles size={13} color="var(--gv-color-smart-teal)" /> {prompt}
                </button>
              ))}
            </div>
          </section>

          <section aria-live="polite" style={{ ...surfaceStyle, minHeight: '360px', maxHeight: '620px', overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '1.1rem' }}>
            {messages.map((message) => (
              <article key={message.id} style={{ display: 'flex', alignSelf: message.sender === 'user' ? 'flex-end' : 'flex-start', gap: '0.65rem', maxWidth: '95%', minWidth: 0 }}>
                {message.sender === 'assistant' && <div style={{ width: 30, height: 30, borderRadius: '50%', background: 'var(--gv-color-smart-teal)', display: 'grid', placeItems: 'center', flexShrink: 0 }}><Bot size={17} color="#fff" /></div>}
                <div style={{ minWidth: 0, background: message.sender === 'user' ? 'var(--gv-color-midnight-navy)' : 'var(--gv-bg-surface-subtle)', color: message.sender === 'user' ? '#fff' : 'var(--gv-text-primary)', padding: '0.8rem 1rem', borderRadius: 'var(--gv-radius-md)', fontSize: '0.83rem', lineHeight: 1.5, border: message.sender === 'user' ? 'none' : '1px solid var(--gv-border-subtle)', whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>
                  <p style={{ margin: 0 }}>{message.text}</p>
                  {message.response && (
                    <div style={{ display: 'grid', gap: '0.7rem', marginTop: '0.75rem' }}>
                      <strong>Workflow status: {message.response.status}</strong>
                      <ExecutionTrace events={message.response.execution_trace} />
                      {message.response.findings.length > 0 && (
                        <div><strong>Findings</strong><ul>{message.response.findings.map((finding, index) => <li key={`${index}-${finding}`}>{finding}</li>)}</ul></div>
                      )}
                      {message.response.evidence_refs.length > 0 && (
                        <div>
                          <strong>Evidence</strong>
                          <ul>{message.response.evidence_refs.map((reference, index) => (
                            <li key={`${reference.source_id}-${index}`}>
                              {reference.source_id}{reference.locator ? ` (${reference.locator})` : ''}{reference.synthetic ? ' — synthetic demo source' : ''}
                              {reference.excerpt && <blockquote style={{ margin: '0.25rem 0 0', color: 'var(--gv-text-secondary)' }}>{reference.excerpt}</blockquote>}
                            </li>
                          ))}</ul>
                        </div>
                      )}
                      {message.response.assumptions.length > 0 && <div><strong>Assumptions</strong><ul>{message.response.assumptions.map((item, index) => <li key={`${index}-${item}`}>{item}</li>)}</ul></div>}
                      {message.response.conflicts.length > 0 && <div><strong>Conflicts</strong><ul>{message.response.conflicts.map((item, index) => <li key={`${index}-${item}`}>{item}</li>)}</ul></div>}
                      {message.response.validation.issues.length > 0 && <div><strong>Validation notes</strong><ul>{message.response.validation.issues.map((item, index) => <li key={`${index}-${item}`}>{item}</li>)}</ul></div>}
                      {message.response.errors.length > 0 && <div><strong>Workflow errors</strong><ul>{message.response.errors.map((item, index) => <li key={`${index}-${item}`}>{item}</li>)}</ul></div>}
                      {Object.entries(message.response.specialist_results).map(([name, result]) => (
                        <details key={name}>
                          <summary>{name.replace(/_/g, ' ')} — {result.status}</summary>
                          {result.findings.length > 0 && <ul>{result.findings.map((finding, index) => <li key={`${index}-${finding}`}>{finding}</li>)}</ul>}
                          {Object.keys(result.data).length > 0 && <pre style={{ maxWidth: '100%', overflow: 'auto', fontSize: '0.72rem' }}>{JSON.stringify(result.data, null, 2)}</pre>}
                          {result.error && <p>{result.error.message}</p>}
                        </details>
                      ))}
                      {message.response.schedule_proposal && (
                        <div style={{ borderTop: '1px solid var(--gv-border-subtle)', paddingTop: '0.65rem' }}>
                          <strong>Schedule proposal — {message.response.schedule_proposal.status}</strong>
                          <p style={{ margin: '0.3rem 0' }}>Cost: ₹{message.response.schedule_proposal.calculated_cost_inr ?? 'not available'} · Savings: ₹{message.response.schedule_proposal.calculated_savings_inr ?? 'not available'}</p>
                          <pre style={{ maxWidth: '100%', overflow: 'auto', fontSize: '0.72rem' }}>{JSON.stringify(message.response.schedule_proposal.schedule, null, 2)}</pre>
                          {message.response.schedule_proposal.status === 'pending' && (
                            <div style={{ display: 'flex', gap: '0.5rem' }}>
                              <button type="button" onClick={() => decideProposal(message.id, message.response!.schedule_proposal!.proposal_id, 'approved')}>Record approval</button>
                              <button type="button" onClick={() => decideProposal(message.id, message.response!.schedule_proposal!.proposal_id, 'rejected')}>Reject</button>
                            </div>
                          )}
                          <small>Decision records are for the demo audit ledger only; no equipment is controlled.</small>
                        </div>
                      )}
                    </div>
                  )}
                  {message.executionTrace && (
                    <ExecutionTrace events={message.executionTrace} />
                  )}
                  <small style={{ display: 'block', marginTop: '0.35rem', opacity: 0.7 }}>{message.timestamp}</small>
                </div>
                {message.sender === 'user' && <div style={{ width: 30, height: 30, borderRadius: '50%', background: 'var(--gv-color-grid-blue)', display: 'grid', placeItems: 'center', flexShrink: 0 }}><User size={17} color="#fff" /></div>}
              </article>
            ))}
            {isTyping && <p style={{ color: 'var(--gv-text-muted)', fontStyle: 'italic', fontSize: '0.82rem' }}>The master agent is consulting the selected specialists…</p>}
          </section>

          <details style={surfaceStyle}>
            <summary style={{ cursor: 'pointer', fontWeight: 700, fontSize: '0.82rem' }}>Optional: provide structured schedule data for the cost optimizer</summary>
            <p style={{ color: 'var(--gv-text-muted)', fontSize: '0.76rem' }}>The demo below is fictional. Replace it with your schedule, hourly tariff, machine availability, maintenance windows, and battery constraints.</p>
            <button type="button" onClick={() => setScheduleJson(DEMO_SCHEDULE)} style={{ ...fieldStyle, width: 'auto', cursor: 'pointer', marginBottom: '0.5rem' }}>Load fictional example</button>
            <textarea aria-label="Schedule optimization inputs in JSON" value={scheduleJson} onChange={(event) => setScheduleJson(event.target.value)} rows={10} placeholder="Paste ScheduleInput JSON here…" style={{ ...fieldStyle, fontFamily: 'monospace', resize: 'vertical' }} />
            {scheduleError && <p role="alert" style={{ color: '#b42318', fontSize: '0.78rem' }}>{scheduleError}</p>}
          </details>

          <form onSubmit={(event) => { event.preventDefault(); void handleSend(inputPrompt); }} style={{ display: 'flex', gap: '0.65rem' }}>
            <input value={inputPrompt} onChange={(event) => setInputPrompt(event.target.value)} placeholder="Ask about operations, renewables, forecasts, or cost optimization…" disabled={isTyping} style={{ ...fieldStyle, flex: 1 }} />
            <button type="submit" disabled={isTyping || !inputPrompt.trim()} style={{ padding: '0 1.1rem', borderRadius: 'var(--gv-radius-md)', background: 'var(--gv-color-smart-teal)', color: '#fff', fontWeight: 700, border: 'none', cursor: isTyping ? 'wait' : 'pointer', display: 'flex', alignItems: 'center', gap: '0.45rem' }}>
              Send <Send size={15} />
            </button>
          </form>
        </>
      )}
      <footer style={{ textAlign: 'center', fontSize: '0.72rem', color: 'var(--gv-text-muted)' }}>
        Demo-only automotive-parts scope · uploaded documents are indexed locally with Docling · no production identity or equipment control
      </footer>
    </div>
  );
};

interface LegacyChatMessage {
  id: string;
  sender: 'user' | 'assistant';
  text: string;
  timestamp: string;
  citations?: AssistantChatResponse['citations'];
  runReferences?: string[];
  downloads?: AssistantChatResponse['downloads'];
  artifacts?: AssistantChatResponse['artifacts'];
  charts?: AssistantChatResponse['charts'];
}

const LegacyAssistantPage: React.FC = () => {
  const { currentPersona, activeEntity } = usePersona();
  const persona = currentPersona || 'household';
  const suggestedPromptsMap: Record<string, string[]> = {
    household: [
      'Summarize my consumption over the selected period.',
      'What was my peak consumption day?',
      'Explain how my month-end bill is calculated.',
      'How can I lower my electricity bill under Time-of-Use tariffs?',
      'Estimate 5 kW rooftop solar generation, cost, payback, and peak-demand impact in Bengaluru.',
    ],
    government: [
      'Show the redistribution plan for 2018-09-24.',
      'Show the model-predicted government grid demand for 2018-09-25.',
      'Compare the available regions by observed demand.',
      'How has aggregate demand changed over the selected period?',
      'Are any regions currently missing from aggregate reporting?',
      'What is our reserve margin against the 460 MW warning line?',
      'Estimate 5 kW rooftop solar generation, cost, payback, and peak-demand impact in Bengaluru.',
    ],
  };
  const suggestedPrompts =
    suggestedPromptsMap[persona] || suggestedPromptsMap.household;
  const [inputPrompt, setInputPrompt] = useState('');
  const [conversationId] = useState(() =>
    typeof crypto !== 'undefined' && 'randomUUID' in crypto
      ? crypto.randomUUID()
      : `conversation-${Date.now()}`
  );
  const [messages, setMessages] = useState<LegacyChatMessage[]>([
    {
      id: 'init-1',
      sender: 'assistant',
      text: `I can answer deterministically when an approved source is available for the selected ${persona} demo context. No approved telemetry source is currently configured, so I will not infer consumption, tariffs, forecasts, or anomaly causes.`,
      timestamp: 'Just now',
    },
  ]);
  const [isTyping, setIsTyping] = useState(false);

  const handleSend = async (text: string) => {
    if (!text.trim() || isTyping) return;
    const trimmed = text.trim();
    setMessages((previous) => [
      ...previous,
      {
        id: `usr-${Date.now()}`,
        sender: 'user',
        text: trimmed,
        timestamp: 'Just now',
      },
    ]);
    setInputPrompt('');
    setIsTyping(true);
    const assistantId = `ast-${typeof crypto !== 'undefined' && 'randomUUID' in crypto
      ? crypto.randomUUID()
      : Date.now()}`;

    try {
      const res = await analyticsService.askAssistantStream(
        trimmed,
        persona,
        activeEntity,
        conversationId,
        (token) => {
          setMessages((prev) => {
            const found = prev.some((message) => message.id === assistantId);
            return found
              ? prev.map((message) =>
                  message.id === assistantId
                    ? { ...message, text: message.text + token }
                    : message
                )
              : [
                  ...prev,
                  {
                    id: assistantId,
                    sender: 'assistant',
                    text: token,
                    timestamp: 'Just now',
                  },
                ];
          });
        },
      );
      setMessages((prev) => {
        const found = prev.some((message) => message.id === assistantId);
        return found
          ? prev.map((message) =>
              message.id === assistantId
                ? {
                    ...message,
                    text: res.answer,
                    citations: res.citations,
                    downloads: res.downloads,
                    artifacts: res.artifacts,
                    runReferences: res.runReferences,
                    charts: res.charts,
                  }
                : message
            )
          : [
              ...prev,
              {
                id: assistantId,
                sender: 'assistant',
                text: res.answer,
                timestamp: 'Just now',
                citations: res.citations,
                downloads: res.downloads,
                artifacts: res.artifacts,
                runReferences: res.runReferences,
                charts: res.charts,
              },
            ];
      });
    } catch (err) {
      const replyMsg: LegacyChatMessage = {
        id: `ast-${Date.now() + 1}`,
        sender: 'assistant',
        text: `The assistant service did not return an answer: ${
          err instanceof Error ? err.message : 'Unknown service error.'
        } Please try again when the backend is available.`,
        timestamp: 'Just now',
      };
      setMessages((prev) => [
        ...prev.filter((message) => message.id !== assistantId),
        replyMsg,
      ]);
    } finally {
      setIsTyping(false);
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem', maxWidth: '1000px', margin: '0 auto', width: '100%' }}>
      <header style={{ background: 'var(--gv-bg-surface)', border: '1px solid var(--gv-border-subtle)', borderRadius: 'var(--gv-radius-lg)', padding: '1.5rem', boxShadow: 'var(--gv-shadow-sm)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.65rem' }}>
          <div style={{ width: 40, height: 40, borderRadius: 'var(--gv-radius-md)', background: 'linear-gradient(135deg, var(--gv-color-smart-teal), var(--gv-color-grid-blue))', display: 'grid', placeItems: 'center' }}>
            <Bot size={22} color="#FFFFFF" />
          </div>
          <div>
            <h2 style={{ fontSize: '1.35rem', fontWeight: 800, color: 'var(--gv-color-midnight-navy)', margin: 0 }}>AI Energy Assistant</h2>
            <p style={{ fontSize: '0.82rem', color: 'var(--gv-text-secondary)', margin: '0.2rem 0 0' }}>
              Conversational intelligence grounded in verified historical data and machine learning telemetry ({persona.toUpperCase()} scope).
            </p>
          </div>
        </div>
      </header>

      <section>
        <div style={{ fontSize: '0.75rem', fontWeight: 700, textTransform: 'uppercase', color: 'var(--gv-text-muted)', letterSpacing: '0.05em', marginBottom: '0.5rem' }}>
          Suggested Prompts for {persona.toUpperCase()}
        </div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem' }}>
          {suggestedPrompts.map((prompt) => (
            <button key={prompt} type="button" onClick={() => void handleSend(prompt)} style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', padding: '0.45rem 0.85rem', borderRadius: '999px', background: 'var(--gv-bg-surface)', border: '1px solid var(--gv-border-accent)', fontSize: '0.78rem', fontWeight: 600, color: 'var(--gv-text-primary)', cursor: 'pointer' }}>
              <Sparkles size={13} color="var(--gv-color-smart-teal)" /> <span>{prompt}</span>
            </button>
          ))}
        </div>
      </section>

      {/* Chat Messages Log */}
      <div
        style={{
          background: 'var(--gv-bg-surface)',
          border: '1px solid var(--gv-border-subtle)',
          borderRadius: 'var(--gv-radius-lg)',
          padding: '1.5rem',
          minHeight: '400px',
          maxHeight: '550px',
          overflowY: 'auto',
          display: 'flex',
          flexDirection: 'column',
          gap: '1.25rem',
        }}
      >
        {messages.map((m) => (
          <div
            key={m.id}
            style={{
              display: 'flex',
              gap: '0.75rem',
              alignSelf: m.sender === 'user' ? 'flex-end' : 'flex-start',
              maxWidth: '85%',
            }}
          >
            {m.sender === 'assistant' && (
              <div
                style={{
                  width: '32px',
                  height: '32px',
                  borderRadius: '50%',
                  background: 'var(--gv-color-smart-teal)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  flexShrink: 0,
                }}
              >
                <Bot size={18} color="#FFFFFF" />
              </div>
            )}

            <div
              style={{
                background: m.sender === 'user' ? 'var(--gv-color-midnight-navy)' : 'var(--gv-bg-surface-subtle)',
                color: m.sender === 'user' ? '#FFFFFF' : 'var(--gv-text-primary)',
                padding: '0.85rem 1.15rem',
                borderRadius: 'var(--gv-radius-md)',
                fontSize: '0.85rem',
                lineHeight: 1.5,
                border: m.sender === 'user' ? 'none' : '1px solid var(--gv-border-subtle)',
                whiteSpace: 'pre-wrap',
              }}
            >
              {m.text}
              {m.runReferences && m.runReferences.length > 0 && (
                <div style={{ marginTop: '0.55rem', fontSize: '0.75rem' }}>
                  Saved run: {m.runReferences.join(', ')}
                </div>
              )}
              {m.charts?.map((chart) => (
                <div key={chart.title} style={{ marginTop: '0.75rem', padding: '0.75rem', background: '#fff', borderRadius: 8 }}>
                  <strong>{chart.title}</strong>
                  {chart.kind === 'map' ? (
                    chart.points?.length ? (() => {
                      const lats = chart.points!.map((point) => point.latitude);
                      const lons = chart.points!.map((point) => point.longitude);
                      const minLat = Math.min(...lats), maxLat = Math.max(...lats);
                      const minLon = Math.min(...lons), maxLon = Math.max(...lons);
                      const latSpan = maxLat - minLat || 0.001;
                      const lonSpan = maxLon - minLon || 0.001;
                      return (
                        <svg role="img" aria-label="Saved event cluster map" viewBox="0 0 480 280" style={{ width: '100%', maxWidth: 560, marginTop: '0.5rem', background: '#f1f5f9', borderRadius: 6 }}>
                          {chart.points!.map((point) => {
                            const x = 24 + ((point.longitude - minLon) / lonSpan) * 432;
                            const y = 24 + ((maxLat - point.latitude) / latSpan) * 232;
                            return <g key={point.id}><title>{`${point.id}: ${point.scope}, severity ${point.severity.toFixed(3)}`}</title><circle cx={x} cy={y} r={5 + Math.max(0, Math.min(1, point.severity)) * 5} fill="#0f766e" fillOpacity="0.78" stroke="#134e4a" /><text x={x + 7} y={y - 5} fontSize="9" fill="#0f172a">{point.id}</text></g>;
                          })}
                        </svg>
                      );
                    })() : <div style={{ marginTop: '0.5rem', fontSize: '0.8rem' }}>No saved events had usable coordinates for the map.</div>
                  ) : (
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: '1rem', marginTop: '0.5rem' }}>
                    {(chart.series || []).map((series) => {
                      const entries = Object.entries(series.items);
                      const max = Math.max(1, ...entries.map(([, value]) => value));
                      const rowHeight = 25;
                      return (
                        <div key={series.label} style={{ flex: '1 1 260px' }}>
                          <div style={{ fontSize: '0.75rem', fontWeight: 600 }}>{series.label}</div>
                          <svg role="img" aria-label={`${series.label} breakdown`} viewBox={`0 0 360 ${Math.max(30, entries.length * rowHeight)}`} style={{ width: '100%', maxWidth: 420 }}>
                            {entries.map(([label, value], index) => {
                              const y = index * rowHeight;
                              const barWidth = Math.max(2, (value / max) * 205);
                              return (
                                <g key={label}>
                                  <text x="0" y={y + 16} fontSize="11" fill="#334155">{label.slice(0, 22)}</text>
                                  <rect x="145" y={y + 4} width={barWidth} height="15" rx="3" fill="#0f766e" />
                                  <text x={153 + barWidth} y={y + 16} fontSize="11" fill="#0f172a">{value}</text>
                                </g>
                              );
                            })}
                          </svg>
                        </div>
                      );
                    })}
                  </div>
                  )}
                </div>
              ))}
              {m.citations && m.citations.length > 0 && (
                <div style={{ marginTop: '0.55rem', fontSize: '0.75rem' }}>
                  <strong>Sources</strong>
                  <ul style={{ margin: '0.25rem 0 0', paddingLeft: '1.2rem' }}>
                    {m.citations.map((citation, index) => (
                      <li key={`${citation.title}-${index}`}>
                        {citation.sourceUrl ? (
                          <a href={citation.sourceUrl} target="_blank" rel="noreferrer">
                            {citation.title}
                          </a>
                        ) : citation.title}
                        {citation.page ? `, p. ${citation.page}` : ''}
                        {citation.publisher ? ` — ${citation.publisher}` : ''}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              {m.downloads && m.downloads.length > 0 && (
                <div style={{ marginTop: '0.55rem', display: 'flex', gap: '0.8rem', flexWrap: 'wrap' }}>
                  {m.downloads.map((download) => (
                    <a
                      key={download.url}
                      href={new URL(download.url, analyticsService.getApiBaseUrl()).toString()}
                      download
                    >
                      {download.label} ({download.format})
                    </a>
                  ))}
                </div>
              )}
              {m.artifacts?.map((artifact) => artifact.format === 'png' && (
                <figure key={artifact.url} style={{ margin: '0.75rem 0 0', maxWidth: 720 }}>
                  <a href={new URL(artifact.url, analyticsService.getApiBaseUrl()).toString()} target="_blank" rel="noreferrer">
                    <img
                      src={new URL(artifact.url, analyticsService.getApiBaseUrl()).toString()}
                      alt={artifact.label}
                      style={{ display: 'block', width: '100%', height: 'auto', borderRadius: 8, border: '1px solid var(--gv-border-subtle)' }}
                    />
                  </a>
                  <figcaption style={{ marginTop: '0.3rem', fontSize: '0.75rem', color: 'var(--gv-text-secondary)' }}>{artifact.label}</figcaption>
                </figure>
              ))}
            </div>
            {m.sender === 'user' && <div style={{ width: 32, height: 32, borderRadius: '50%', background: 'var(--gv-color-grid-blue)', display: 'grid', placeItems: 'center', flexShrink: 0 }}><User size={18} color="#FFFFFF" /></div>}
          </div>
        ))}
        {isTyping && <div style={{ fontStyle: 'italic', color: 'var(--gv-text-muted)', fontSize: '0.85rem' }}>GridVision Assistant is analyzing telemetry...</div>}
      </div>

      {/* Input Box */}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          handleSend(inputPrompt);
        }}
        style={{
          display: 'flex',
          gap: '0.75rem',
        }}
      >
        <input
          type="text"
          value={inputPrompt}
          onChange={(e) => setInputPrompt(e.target.value)}
          placeholder={persona === 'government'
            ? 'Ask about anomalies, government-grid demand, or redistribution plans...'
            : `Ask about ${persona} energy consumption, forecasts, or billing equations...`}
          style={{
            flex: 1,
            padding: '0.85rem 1.15rem',
            borderRadius: 'var(--gv-radius-md)',
            border: '1px solid var(--gv-border-accent)',
            background: 'var(--gv-bg-surface)',
            fontSize: '0.88rem',
            color: 'var(--gv-text-primary)',
            outline: 'none',
          }}
        />
        <button
          type="submit"
          style={{
            padding: '0 1.5rem',
            borderRadius: 'var(--gv-radius-md)',
            background: 'var(--gv-color-smart-teal)',
            color: '#FFFFFF',
            fontWeight: 700,
            fontSize: '0.88rem',
            border: 'none',
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            gap: '0.5rem',
          }}
        >
          <span>Send</span>
          <Send size={15} />
        </button>
      </form>

      {/* Prototype Disclosure Footnote */}
      <div style={{ textAlign: 'center', fontSize: '0.72rem', color: 'var(--gv-text-muted)' }}>
        Government questions are routed by Ollama to the anomaly or government-grid assistant. Generated redistribution charts and data appear with the answer.
      </div>
      <footer style={{ textAlign: 'center', fontSize: '0.72rem', color: 'var(--gv-text-muted)' }}>
        Solar estimates show their assumptions and link Tavily web sources when available; figures are illustrative, not a quote.
      </footer>
    </div>
  );
};

export const AiAssistantPage: React.FC = () => {
  const { currentPersona } = usePersona();
  return currentPersona === 'commercial'
    ? <CommercialAssistantPage />
    : <LegacyAssistantPage />;
};
