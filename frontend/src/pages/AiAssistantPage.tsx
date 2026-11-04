import React, { useState } from 'react';
import { usePersona } from '../context';
import { analyticsService } from '../services/analyticsService';
import {
  Bot,
  Send,
  Sparkles,
  User,
} from 'lucide-react';

interface ChatMessage {
  id: string;
  sender: 'user' | 'assistant';
  text: string;
  timestamp: string;
  citations?: Array<{ title: string; sourceUrl?: string | null; page?: number | null; publisher?: string | null }>;
  downloads?: Array<{ format: string; label: string; url: string }>;
  artifacts?: Array<{ format: string; label: string; url: string }>;
  runReferences?: string[];
  charts?: Array<{
    title: string;
    kind?: 'map';
    points?: Array<{ id: string; latitude: number; longitude: number; severity: number; scope: string }>;
    series?: Array<{ label: string; items: Record<string, number> }>;
  }>;
}

export const AiAssistantPage: React.FC = () => {
  const { currentPersona, activeEntity } = usePersona();
  const persona = currentPersona || 'household';

  const suggestedPromptsMap: Record<string, string[]> = {
    household: [
      'Summarize my consumption over the selected period.',
      'What was my peak consumption day?',
      'Explain how my month-end bill is calculated.',
      'How can I lower my electricity bill under Time-of-Use tariffs?',
    ],
    commercial: [
      "Show the building's peak observed demand.",
      "How does the building's demand compare with the previous period?",
      "What features most influence this building's electricity demand?",
      'What is the cooling degree hours impact on HVAC load?',
    ],
    government: [
      'Show the redistribution plan for 2018-09-24.',
      'Show the model-predicted government grid demand for 2018-09-25.',
      'Compare the available regions by observed demand.',
      'How has aggregate demand changed over the selected period?',
      'Are any regions currently missing from aggregate reporting?',
      'What is our reserve margin against the 460 MW warning line?',
    ],
  };

  const suggestedPrompts = suggestedPromptsMap[persona] || suggestedPromptsMap.household;

  const [inputPrompt, setInputPrompt] = useState('');
  const [conversationId] = useState(() =>
    typeof crypto !== 'undefined' && 'randomUUID' in crypto
      ? crypto.randomUUID()
      : `conversation-${Date.now()}`
  );
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: 'init-1',
      sender: 'assistant',
      text: `Hello! I am GridVision Assistant, operating in **${persona.toUpperCase()}** scope for **${activeEntity}**. How can I help you analyze telemetry, forecast trends, or explain tariff calculations today?`,
      timestamp: 'Just now',
    },
  ]);

  const [isTyping, setIsTyping] = useState<boolean>(false);

  const handleSend = async (text: string) => {
    if (!text.trim()) return;

    const trimmed = text.trim();
    const userMsg: ChatMessage = {
      id: `usr-${Date.now()}`,
      sender: 'user',
      text: trimmed,
      timestamp: 'Just now',
    };

    setMessages((prev) => [...prev, userMsg]);
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
      const replyMsg: ChatMessage = {
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
      {/* Header */}
      <div
        style={{
          background: 'var(--gv-bg-surface)',
          border: '1px solid var(--gv-border-subtle)',
          borderRadius: 'var(--gv-radius-lg)',
          padding: '1.5rem',
          boxShadow: 'var(--gv-shadow-sm)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.65rem' }}>
          <div
            style={{
              width: '40px',
              height: '40px',
              borderRadius: 'var(--gv-radius-md)',
              background: 'linear-gradient(135deg, var(--gv-color-smart-teal), var(--gv-color-grid-blue))',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            <Bot size={22} color="#FFFFFF" />
          </div>
          <div>
            <h2 style={{ fontSize: '1.35rem', fontWeight: 800, color: 'var(--gv-color-midnight-navy)', margin: 0 }}>
              AI Energy Assistant
            </h2>
            <p style={{ fontSize: '0.82rem', color: 'var(--gv-text-secondary)', margin: '0.2rem 0 0 0' }}>
              Conversational intelligence grounded in verified historical data and machine learning telemetry ({persona.toUpperCase()} scope).
            </p>
          </div>
        </div>
      </div>

      {/* Suggested Prompts Strip */}
      <div>
        <div style={{ fontSize: '0.75rem', fontWeight: 700, textTransform: 'uppercase', color: 'var(--gv-text-muted)', letterSpacing: '0.05em', marginBottom: '0.5rem' }}>
          Suggested Prompts for {persona.toUpperCase()}
        </div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem' }}>
          {suggestedPrompts.map((prompt, idx) => (
            <button
              key={idx}
              type="button"
              onClick={() => handleSend(prompt)}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '0.35rem',
                padding: '0.45rem 0.85rem',
                borderRadius: '999px',
                background: 'var(--gv-bg-surface)',
                border: '1px solid var(--gv-border-accent)',
                fontSize: '0.78rem',
                fontWeight: 600,
                color: 'var(--gv-text-primary)',
                cursor: 'pointer',
                transition: 'all 0.15s ease',
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.borderColor = 'var(--gv-color-smart-teal)';
                e.currentTarget.style.color = 'var(--gv-color-smart-teal)';
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.borderColor = 'var(--gv-border-accent)';
                e.currentTarget.style.color = 'var(--gv-text-primary)';
              }}
            >
              <Sparkles size={13} color="var(--gv-color-smart-teal)" />
              <span>{prompt}</span>
            </button>
          ))}
        </div>
      </div>

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

            {m.sender === 'user' && (
              <div
                style={{
                  width: '32px',
                  height: '32px',
                  borderRadius: '50%',
                  background: 'var(--gv-color-grid-blue)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  flexShrink: 0,
                }}
              >
                <User size={18} color="#FFFFFF" />
              </div>
            )}
          </div>
        ))}
        {isTyping && (
          <div style={{ display: 'flex', gap: '0.75rem', alignSelf: 'flex-start', alignItems: 'center' }}>
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
            <div style={{ fontStyle: 'italic', color: 'var(--gv-text-muted)', fontSize: '0.85rem' }}>
              GridVision Assistant is analyzing telemetry...
            </div>
          </div>
        )}
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
    </div>
  );
};
