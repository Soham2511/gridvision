import React, { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import {
  ResponsiveContainer,
  LineChart,
  Line,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
} from 'recharts';
import { Check, Copy, Code, BarChart2, Calculator } from 'lucide-react';

interface ChatMessageRendererProps {
  content: string;
  isUser?: boolean;
}

interface ChartConfig {
  type?: 'line' | 'bar';
  title?: string;
  xAxisKey?: string;
  yAxisUnit?: string;
  data: Record<string, any>[];
  series?: {
    key: string;
    name?: string;
    color?: string;
  }[];
}

/**
 * Pre-processes raw mathematical formulas in markdown strings.
 * Converts LaTeX display blocks ($$...$$, \[...\], \(...\)) into clean markdown callouts.
 */
function normalizeMathFormulas(text: string): string {
  if (!text) return '';

  // 1. Normalize $$ ... $$ display math
  let result = text.replace(/\$\$([\s\S]*?)\$\$/g, (_, mathContent) => {
    const cleaned = mathContent
      .replace(/\\text\{([^}]+)\}/g, '$1')
      .replace(/\\times/g, '×')
      .replace(/\\div/g, '÷')
      .replace(/\\pm/g, '±')
      .replace(/\\le/g, '≤')
      .replace(/\\ge/g, '≥')
      .replace(/\\neq/g, '≠')
      .replace(/\\approx/g, '≈')
      .replace(/\\,/g, ' ')
      .replace(/\\;/g, ' ')
      .trim();
    return '\n\n```math\n' + cleaned + '\n```\n\n';
  });

  // 2. Normalize \[ ... \] display math
  result = result.replace(/\\\[([\s\S]*?)\\\]/g, (_, mathContent) => {
    const cleaned = mathContent
      .replace(/\\text\{([^}]+)\}/g, '$1')
      .replace(/\\times/g, '×')
      .replace(/\\div/g, '÷')
      .replace(/\\,/g, ' ')
      .trim();
    return '\n\n```math\n' + cleaned + '\n```\n\n';
  });

  // 3. Normalize inline \( ... \) math
  result = result.replace(/\\\(([\s\S]*?)\\\)/g, (_, mathContent) => {
    const cleaned = mathContent
      .replace(/\\text\{([^}]+)\}/g, '$1')
      .replace(/\\times/g, '×')
      .replace(/\\div/g, '÷')
      .replace(/\\,/g, ' ')
      .trim();
    return `\`${cleaned}\``;
  });

  return result;
}

interface ChartErrorBoundaryProps {
  children: React.ReactNode;
  fallbackValue?: string;
}

interface ChartErrorBoundaryState {
  hasError: boolean;
}

class ChartErrorBoundary extends React.Component<ChartErrorBoundaryProps, ChartErrorBoundaryState> {
  constructor(props: ChartErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError(): ChartErrorBoundaryState {
    return { hasError: true };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    console.warn('GridVision: Chart rendering error prevented by boundary:', error, info);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div
          style={{
            margin: '0.75rem 0',
            padding: '0.85rem 1rem',
            backgroundColor: '#F8FAFC',
            borderRadius: '6px',
            border: '1px dashed #CBD5E1',
            fontSize: '0.8rem',
            color: '#64748B',
            display: 'flex',
            alignItems: 'center',
            gap: '0.5rem',
          }}
        >
          <BarChart2 size={16} color="#94A3B8" />
          <span>Chart visualization could not be displayed due to incomplete data payload.</span>
        </div>
      );
    }
    return this.props.children;
  }
}

function validateChartConfig(raw: any): ChartConfig | null {
  if (!raw || typeof raw !== 'object') return null;
  if (!Array.isArray(raw.data) || raw.data.length === 0) return null;
  for (const item of raw.data) {
    if (!item || typeof item !== 'object') return null;
  }
  const type = raw.type === 'bar' ? 'bar' : 'line';
  const xAxisKey =
    typeof raw.xAxisKey === 'string' && raw.xAxisKey.trim()
      ? raw.xAxisKey.trim()
      : Object.keys(raw.data[0])[0];

  if (!xAxisKey) return null;

  let seriesList: { key: string; name?: string; color?: string }[] = [];
  if (Array.isArray(raw.series) && raw.series.length > 0) {
    seriesList = raw.series.filter(
      (s: any) => s && typeof s.key === 'string' && s.key.trim().length > 0
    );
  }
  if (seriesList.length === 0) {
    seriesList = Object.keys(raw.data[0])
      .filter((k) => k !== xAxisKey)
      .map((key, i) => ({
        key,
        name: key,
        color: i === 0 ? '#00B8A9' : i === 1 ? '#087EBD' : '#FFC247',
      }));
  }
  if (seriesList.length === 0) return null;

  return {
    type,
    title: typeof raw.title === 'string' ? raw.title : undefined,
    xAxisKey,
    yAxisUnit: typeof raw.yAxisUnit === 'string' ? raw.yAxisUnit : undefined,
    data: raw.data,
    series: seriesList,
  };
}

const CodeBlock: React.FC<{ language: string; value: string }> = ({ language, value }) => {
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    navigator.clipboard.writeText(value);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  // Check if this is a chart block
  if (language === 'chart' || language === 'json:chart') {
    try {
      const parsed = JSON.parse(value);
      const validatedConfig = validateChartConfig(parsed);
      if (validatedConfig) {
        const xAxisKey = validatedConfig.xAxisKey || Object.keys(validatedConfig.data[0])[0];
        const seriesList = validatedConfig.series || [];

        return (
          <ChartErrorBoundary fallbackValue={value}>
            <div
              style={{
                margin: '1rem 0',
                padding: '1rem',
                backgroundColor: '#FFFFFF',
                borderRadius: '8px',
                border: '1px solid #E2E8F0',
                boxShadow: '0 1px 3px rgba(0, 0, 0, 0.04)',
              }}
            >
              {validatedConfig.title && (
                <div
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '0.45rem',
                    fontSize: '0.85rem',
                    fontWeight: 700,
                    color: '#0B1F33',
                    marginBottom: '0.75rem',
                  }}
                >
                  <BarChart2 size={16} color="#00B8A9" />
                  <span>{validatedConfig.title}</span>
                </div>
              )}
              <div style={{ width: '100%', height: 240 }}>
                <ResponsiveContainer width="100%" height="100%">
                  {validatedConfig.type === 'bar' ? (
                    <BarChart data={validatedConfig.data} margin={{ top: 10, right: 10, left: -15, bottom: 0 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#F1F5F9" />
                      <XAxis dataKey={xAxisKey} tick={{ fontSize: 11, fill: '#64748B' }} />
                      <YAxis
                        tick={{ fontSize: 11, fill: '#64748B' }}
                        unit={validatedConfig.yAxisUnit ? ` ${validatedConfig.yAxisUnit}` : ''}
                      />
                      <Tooltip
                        contentStyle={{
                          borderRadius: '6px',
                          border: '1px solid #E2E8F0',
                          fontSize: '0.78rem',
                          boxShadow: '0 2px 4px rgba(0,0,0,0.06)',
                        }}
                      />
                      <Legend wrapperStyle={{ fontSize: '0.75rem' }} />
                      {seriesList.map((s) => (
                        <Bar key={s.key} dataKey={s.key} name={s.name || s.key} fill={s.color || '#00B8A9'} radius={[4, 4, 0, 0]} />
                      ))}
                    </BarChart>
                  ) : (
                    <LineChart data={validatedConfig.data} margin={{ top: 10, right: 10, left: -15, bottom: 0 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#F1F5F9" />
                      <XAxis dataKey={xAxisKey} tick={{ fontSize: 11, fill: '#64748B' }} />
                      <YAxis
                        tick={{ fontSize: 11, fill: '#64748B' }}
                        unit={validatedConfig.yAxisUnit ? ` ${validatedConfig.yAxisUnit}` : ''}
                      />
                      <Tooltip
                        contentStyle={{
                          borderRadius: '6px',
                          border: '1px solid #E2E8F0',
                          fontSize: '0.78rem',
                          boxShadow: '0 2px 4px rgba(0,0,0,0.06)',
                        }}
                      />
                      <Legend wrapperStyle={{ fontSize: '0.75rem' }} />
                      {seriesList.map((s) => (
                        <Line
                          key={s.key}
                          type="monotone"
                          dataKey={s.key}
                          name={s.name || s.key}
                          stroke={s.color || '#00B8A9'}
                          strokeWidth={2}
                          dot={{ r: 3 }}
                        />
                      ))}
                    </LineChart>
                  )}
                </ResponsiveContainer>
              </div>
            </div>
          </ChartErrorBoundary>
        );
      }
    } catch {
      // Incomplete streaming or invalid JSON falls back gracefully to code block
    }
  }


  // Check if this is a normalized math block
  if (language === 'math') {
    return (
      <div
        style={{
          margin: '0.75rem 0',
          padding: '0.85rem 1.15rem',
          backgroundColor: '#F8FAFC',
          borderLeft: '4px solid #00B8A9',
          borderTop: '1px solid #E2E8F0',
          borderRight: '1px solid #E2E8F0',
          borderBottom: '1px solid #E2E8F0',
          borderRadius: '6px',
          display: 'flex',
          alignItems: 'center',
          gap: '0.75rem',
        }}
      >
        <Calculator size={18} color="#00B8A9" style={{ flexShrink: 0 }} />
        <div
          style={{
            fontFamily: 'var(--gv-font-sans)',
            fontSize: '0.9rem',
            fontWeight: 600,
            color: '#0B1F33',
            lineHeight: 1.5,
            overflowX: 'auto',
          }}
        >
          {value}
        </div>
      </div>
    );
  }

  return (
    <div
      style={{
        margin: '0.85rem 0',
        borderRadius: '8px',
        overflow: 'hidden',
        border: '1px solid #CBD5E1',
        backgroundColor: '#0B1F33',
        color: '#F8FAFC',
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '0.4rem 0.85rem',
          backgroundColor: 'rgba(255, 255, 255, 0.06)',
          borderBottom: '1px solid rgba(255, 255, 255, 0.1)',
          fontSize: '0.75rem',
          color: '#94A3B8',
          fontFamily: 'monospace',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
          <Code size={13} color="#00B8A9" />
          <span>{language || 'code'}</span>
        </div>
        <button
          type="button"
          onClick={handleCopy}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '0.3rem',
            padding: '2px 8px',
            borderRadius: '4px',
            backgroundColor: copied ? 'rgba(0, 184, 169, 0.2)' : 'rgba(255, 255, 255, 0.1)',
            color: copied ? '#00B8A9' : '#CBD5E1',
            fontSize: '0.72rem',
            cursor: 'pointer',
            transition: 'all 0.15s ease',
          }}
        >
          {copied ? <Check size={12} /> : <Copy size={12} />}
          <span>{copied ? 'Copied' : 'Copy'}</span>
        </button>
      </div>
      <pre
        style={{
          margin: 0,
          padding: '0.85rem 1rem',
          fontSize: '0.82rem',
          fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
          lineHeight: 1.5,
          overflowX: 'auto',
        }}
      >
        <code>{value}</code>
      </pre>
    </div>
  );
};

export const ChatMessageRenderer: React.FC<ChatMessageRendererProps> = ({ content, isUser = false }) => {
  if (isUser) {
    return <div style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>{content}</div>;
  }

  const normalizedContent = normalizeMathFormulas(content);

  return (
    <div
      className="gv-chat-markdown"
      style={{
        lineHeight: 1.6,
        color: '#0B1F33',
        wordBreak: 'break-word',
        overflowWrap: 'break-word',
      }}
    >
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          // Headings
          h1: ({ children }) => (
            <h1
              style={{
                fontSize: '1.25rem',
                fontWeight: 800,
                color: '#0B1F33',
                margin: '0.75rem 0 0.35rem 0',
                lineHeight: 1.3,
                letterSpacing: '-0.02em',
              }}
            >
              {children}
            </h1>
          ),
          h2: ({ children }) => (
            <h2
              style={{
                fontSize: '1.1rem',
                fontWeight: 700,
                color: '#0B1F33',
                margin: '0.65rem 0 0.3rem 0',
                lineHeight: 1.3,
                letterSpacing: '-0.01em',
              }}
            >
              {children}
            </h2>
          ),
          h3: ({ children }) => (
            <h3
              style={{
                fontSize: '0.95rem',
                fontWeight: 700,
                color: '#0B1F33',
                margin: '0.5rem 0 0.25rem 0',
                lineHeight: 1.3,
              }}
            >
              {children}
            </h3>
          ),
          h4: ({ children }) => (
            <h4
              style={{
                fontSize: '0.88rem',
                fontWeight: 700,
                color: '#334155',
                margin: '0.45rem 0 0.2rem 0',
              }}
            >
              {children}
            </h4>
          ),

          // Paragraphs
          p: ({ children }) => (
            <p
              style={{
                margin: '0 0 0.65rem 0',
                lineHeight: 1.6,
              }}
            >
              {children}
            </p>
          ),

          // Lists
          ul: ({ children }) => (
            <ul
              style={{
                margin: '0.35rem 0 0.75rem 0',
                paddingLeft: '1.35rem',
                listStyleType: 'disc',
              }}
            >
              {children}
            </ul>
          ),
          ol: ({ children }) => (
            <ol
              style={{
                margin: '0.35rem 0 0.75rem 0',
                paddingLeft: '1.35rem',
                listStyleType: 'decimal',
              }}
            >
              {children}
            </ol>
          ),
          li: ({ children }) => (
            <li
              style={{
                margin: '0.2rem 0',
                lineHeight: 1.5,
              }}
            >
              {children}
            </li>
          ),

          // Blockquotes
          blockquote: ({ children }) => (
            <blockquote
              style={{
                margin: '0.75rem 0',
                padding: '0.65rem 1rem',
                borderLeft: '4px solid #00B8A9',
                backgroundColor: '#F0FDFA',
                borderRadius: '0 6px 6px 0',
                color: '#0F766E',
                fontSize: '0.85rem',
              }}
            >
              {children}
            </blockquote>
          ),

          // Tables (with horizontal scroll container and responsive cell alignment)
          table: ({ children }) => (
            <div
              style={{
                width: '100%',
                overflowX: 'auto',
                margin: '0.85rem 0',
                borderRadius: '8px',
                border: '1px solid #E2E8F0',
                boxShadow: '0 1px 2px rgba(0, 0, 0, 0.03)',
              }}
            >
              <table
                style={{
                  width: '100%',
                  borderCollapse: 'collapse',
                  fontSize: '0.82rem',
                  textAlign: 'left',
                }}
              >
                {children}
              </table>
            </div>
          ),
          thead: ({ children }) => (
            <thead
              style={{
                backgroundColor: '#F8FAFC',
                borderBottom: '2px solid #E2E8F0',
              }}
            >
              {children}
            </thead>
          ),
          tbody: ({ children }) => <tbody>{children}</tbody>,
          tr: ({ children }) => (
            <tr
              style={{
                borderBottom: '1px solid #F1F5F9',
                transition: 'background-color 0.1s ease',
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.backgroundColor = '#F8FAFC';
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.backgroundColor = 'transparent';
              }}
            >
              {children}
            </tr>
          ),
          th: ({ children }) => (
            <th
              style={{
                padding: '0.6rem 0.85rem',
                fontWeight: 700,
                color: '#0B1F33',
                whiteSpace: 'nowrap',
              }}
            >
              {children}
            </th>
          ),
          td: ({ children }) => (
            <td
              style={{
                padding: '0.55rem 0.85rem',
                color: '#334155',
                verticalAlign: 'middle',
              }}
            >
              {children}
            </td>
          ),

          // Strong & Emphasis
          strong: ({ children }) => (
            <strong style={{ fontWeight: 700, color: '#0B1F33' }}>{children}</strong>
          ),
          em: ({ children }) => <em style={{ fontStyle: 'italic' }}>{children}</em>,

          // Inline & Block Code
          code: ({ className, children, ...props }) => {
            const match = /language-(\w+)/.exec(className || '');
            const codeString = String(children).replace(/\n$/, '');
            const isMultiline = String(children).includes('\n') || match;

            if (isMultiline) {
              return <CodeBlock language={match ? match[1] : ''} value={codeString} />;
            }

            return (
              <code
                style={{
                  fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
                  fontSize: '0.8em',
                  padding: '2px 6px',
                  borderRadius: '4px',
                  backgroundColor: 'rgba(11, 31, 51, 0.06)',
                  color: '#087EBD',
                  fontWeight: 600,
                  border: '1px solid rgba(11, 31, 51, 0.08)',
                }}
                {...props}
              >
                {children}
              </code>
            );
          },

          // Links
          a: ({ href, children }) => (
            <a
              href={href}
              target="_blank"
              rel="noopener noreferrer"
              style={{
                color: '#00A396',
                textDecoration: 'underline',
                fontWeight: 600,
              }}
            >
              {children}
            </a>
          ),

          // Horizontal rule
          hr: () => (
            <hr
              style={{
                border: 'none',
                borderTop: '1px solid #E2E8F0',
                margin: '1rem 0',
              }}
            />
          ),
        }}
      >
        {normalizedContent}
      </ReactMarkdown>
    </div>
  );
};
