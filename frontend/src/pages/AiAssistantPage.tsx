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
      'Compare the available regions by observed demand.',
      'How has aggregate demand changed over the selected period?',
      'Are any regions currently missing from aggregate reporting?',
      'What is our reserve margin against the 460 MW warning line?',
    ],
  };

  const suggestedPrompts = suggestedPromptsMap[persona] || suggestedPromptsMap.household;

  const [inputPrompt, setInputPrompt] = useState('');
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

    try {
      const res = await analyticsService.askAssistant(trimmed, persona, activeEntity);
      const replyMsg: ChatMessage = {
        id: `ast-${Date.now() + 1}`,
        sender: 'assistant',
        text: res.answer,
        timestamp: 'Just now',
      };
      setMessages((prev) => [...prev, replyMsg]);
    } catch (err) {
      const replyMsg: ChatMessage = {
        id: `ast-${Date.now() + 1}`,
        sender: 'assistant',
        text: `The assistant service did not return an answer: ${
          err instanceof Error ? err.message : 'Unknown service error.'
        } Please try again when the backend is available.`,
        timestamp: 'Just now',
      };
      setMessages((prev) => [...prev, replyMsg]);
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
          placeholder={`Ask about ${persona} energy consumption, forecasts, or billing equations...`}
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
        AI Assistant answers are generated from local deterministic models and historical benchmark fixtures.
      </div>
    </div>
  );
};
