import React, { useState, useEffect, useMemo, useRef } from 'react';
import { usePersona } from '../context';
import { analyticsService } from '../services/analyticsService';
import { ChatMessageRenderer } from '../components/chat/ChatMessageRenderer';
import {
  ResidentialFeatureId,
  QuestionnaireSchema,
  HouseEnergyPlanningResult,
  ApplianceScenarioResult,
  CostManagementResult,
  DocumentCitation,
} from '../types/residentialFeatures';
import { FeatureEntryCards } from '../components/residential/FeatureEntryCards';
import { SchemaQuestionnaire } from '../components/residential/SchemaQuestionnaire';
import { HousePlanningResultsView } from '../components/residential/HousePlanningResultsView';
import { ApplianceAnalysisResultsView } from '../components/residential/ApplianceAnalysisResultsView';
import { CostManagementResultsView } from '../components/residential/CostManagementResultsView';
import {
  Bot,
  Send,
  Sparkles,
  User,
  Copy,
  Check,
  Sliders,
  MessageSquare,
  AlertTriangle,
} from 'lucide-react';

interface ChatMessage {
  id: string;
  sender: 'user' | 'assistant';
  text: string;
  timestamp: string;
  mode?: string;
  citations?: DocumentCitation[];
  provenance?: any;
  assumptions?: string[];
  limitations?: string[];
  missingInformation?: string[];
}

const AssistantMessageBubble: React.FC<{ message: ChatMessage }> = ({ message }) => {
  const [copied, setCopied] = useState(false);
  const [showCitations, setShowCitations] = useState(true);

  const handleCopy = () => {
    navigator.clipboard.writeText(message.text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const citations = message.citations || [];
  const limitations = message.limitations || [];
  const assumptions = message.assumptions || [];

  return (
    <div
      style={{
        display: 'flex',
        gap: '0.75rem',
        alignSelf: 'flex-start',
        maxWidth: '92%',
        width: '100%',
      }}
    >
      {/* Bot Avatar */}
      <div
        style={{
          width: '34px',
          height: '34px',
          borderRadius: '50%',
          background: 'linear-gradient(135deg, #00B8A9, #087EBD)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          flexShrink: 0,
          boxShadow: '0 2px 4px rgba(0, 184, 169, 0.2)',
          marginTop: '2px',
        }}
      >
        <Bot size={18} color="#FFFFFF" />
      </div>

      {/* Message Card */}
      <div
        style={{
          flex: 1,
          backgroundColor: '#FFFFFF',
          borderRadius: '12px',
          border: '1px solid #E2E8F0',
          boxShadow: '0 1px 3px rgba(11, 31, 51, 0.04)',
          padding: '1rem 1.25rem',
          display: 'flex',
          flexDirection: 'column',
          gap: '0.5rem',
          minWidth: 0,
        }}
      >
        {/* Card Header */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            borderBottom: '1px solid #F1F5F9',
            paddingBottom: '0.4rem',
            marginBottom: '0.2rem',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.45rem' }}>
            <span style={{ fontSize: '0.8rem', fontWeight: 700, color: '#0B1F33' }}>
              GridVision Assistant
            </span>
            <span
              style={{
                fontSize: '0.68rem',
                fontWeight: 600,
                color: '#00A396',
                backgroundColor: '#E0F7F5',
                padding: '1px 6px',
                borderRadius: '4px',
              }}
            >
              Verified Telemetry
            </span>
          </div>

          <button
            type="button"
            onClick={handleCopy}
            title="Copy full response"
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '0.3rem',
              padding: '2px 8px',
              borderRadius: '4px',
              backgroundColor: copied ? '#E0F7F5' : 'transparent',
              color: copied ? '#00A396' : '#64748B',
              fontSize: '0.72rem',
              fontWeight: 500,
              cursor: 'pointer',
              transition: 'all 0.15s ease',
              border: copied ? '1px solid #00B8A9' : '1px solid transparent',
            }}
          >
            {copied ? <Check size={12} color="#00A396" /> : <Copy size={12} />}
            <span>{copied ? 'Copied' : 'Copy'}</span>
          </button>
        </div>

        {/* Formatted Markdown Content */}
        <ChatMessageRenderer content={message.text} isUser={false} />

        {/* Verified Regulatory Citations */}
        {citations.length > 0 && (
          <div
            style={{
              marginTop: '0.6rem',
              borderTop: '1px solid #E2E8F0',
              paddingTop: '0.45rem',
            }}
          >
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                cursor: 'pointer',
                userSelect: 'none',
                marginBottom: '0.35rem',
              }}
              onClick={() => setShowCitations((prev) => !prev)}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
                <span style={{ fontSize: '0.74rem', fontWeight: 700, color: '#0F766E' }}>
                  📜 Verified Standards & Citations ({citations.length})
                </span>
              </div>
              <span style={{ fontSize: '0.68rem', color: '#64748B' }}>
                {showCitations ? 'Hide ▲' : 'Show ▼'}
              </span>
            </div>

            {showCitations && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.35rem' }}>
                {citations.map((c, idx) => (
                  <div
                    key={`${c.source_id}-${idx}`}
                    style={{
                      backgroundColor: '#F8FAFC',
                      border: '1px solid #E2E8F0',
                      borderRadius: '6px',
                      padding: '0.4rem 0.6rem',
                      fontSize: '0.72rem',
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', marginBottom: '0.15rem' }}>
                      <span
                        style={{
                          backgroundColor:
                            c.publisher === 'BEE'
                              ? '#EFF6FF'
                              : c.publisher === 'BIS'
                              ? '#FDF2F8'
                              : '#F0FDF4',
                          color:
                            c.publisher === 'BEE'
                              ? '#1D4ED8'
                              : c.publisher === 'BIS'
                              ? '#BE185D'
                              : '#15803D',
                          fontWeight: 700,
                          fontSize: '0.65rem',
                          padding: '1px 5px',
                          borderRadius: '3px',
                        }}
                      >
                        {c.publisher}
                      </span>
                      <strong style={{ color: '#0F172A' }}>{c.document_identifier}</strong>
                      <span style={{ color: '#64748B' }}>— {c.section} (Page {c.page})</span>
                    </div>
                    <div style={{ color: '#334155', fontStyle: 'italic', fontSize: '0.70rem', lineHeight: 1.4 }}>
                      "{c.text_snippet}"
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Modeling Assumptions */}
        {assumptions.length > 0 && (
          <div
            style={{
              marginTop: '0.35rem',
              backgroundColor: '#F0FDF4',
              border: '1px solid #BBF7D0',
              borderRadius: '6px',
              padding: '0.35rem 0.6rem',
              fontSize: '0.72rem',
              color: '#166534',
            }}
          >
            <strong>Modeling Assumptions: </strong>
            {assumptions.join(' ')}
          </div>
        )}

        {/* Safety Limitations & Engineering Caveats */}
        {limitations.length > 0 && (
          <div
            style={{
              marginTop: '0.35rem',
              backgroundColor: '#FEF3C7',
              border: '1px solid #FCD34D',
              borderRadius: '6px',
              padding: '0.35rem 0.6rem',
              fontSize: '0.72rem',
              color: '#92400E',
              display: 'flex',
              alignItems: 'flex-start',
              gap: '0.4rem',
            }}
          >
            <AlertTriangle size={14} style={{ flexShrink: 0, marginTop: '2px' }} />
            <div>
              <strong>Engineering & Safety Caveat: </strong>
              {limitations.join(' ')}
            </div>
          </div>
        )}

        {/* Card Footer */}
        <div
          style={{
            fontSize: '0.7rem',
            color: '#94A3B8',
            marginTop: '0.2rem',
            textAlign: 'right',
          }}
        >
          {message.timestamp}
        </div>
      </div>
    </div>
  );
};

export const AiAssistantPage: React.FC = () => {
  const { currentPersona, activeEntity } = usePersona();
  const persona = currentPersona || 'household';
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Active Feature Mode for Household Scope
  const [activeFeature, setActiveFeature] = useState<ResidentialFeatureId>('general_chat');
  const [activeTab, setActiveTab] = useState<'workflow' | 'chat'>('workflow');

  // Questionnaires cache
  const [questionnaireSchemas, setQuestionnaireSchemas] = useState<Record<string, QuestionnaireSchema>>({});
  const [isLoadingSchema, setIsLoadingSchema] = useState(false);
  const [schemaError, setSchemaError] = useState<string | null>(null);

  // Calculation results
  const [isCalculating, setIsCalculating] = useState(false);
  const [housePlanningResult, setHousePlanningResult] = useState<HouseEnergyPlanningResult | null>(null);
  const [applianceResult, setApplianceResult] = useState<ApplianceScenarioResult | null>(null);
  const [costResult, setCostResult] = useState<CostManagementResult | null>(null);
  const [calculationError, setCalculationError] = useState<string | null>(null);
  const [savedFormData, setSavedFormData] = useState<Record<string, Record<string, any>>>({});

  const suggestedPromptsMap: Record<string, string[]> = {
    household: [
      'Summarize my consumption over the selected period.',
      'Explain how my month-end bill is calculated.',
      'What was my daily average consumption?',
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

  const residentName = useMemo(() => {
    const numPart = (activeEntity || '2254213').replace(/METER-/i, '').replace(/meter-/i, '');
    return `OBJECTID ${numPart}`;
  }, [activeEntity]);

  const [inputPrompt, setInputPrompt] = useState('');
  const [messages, setMessages] = useState<ChatMessage[]>(() => {
    const initialGreeting =
      persona === 'household'
        ? `Hello **${residentName}**! I am GridVision Assistant, operating in **RESIDENTIAL** scope for **OBJECTID ${(activeEntity || '2254213').replace(/METER-/i, '')}**. How can I help you analyze your household consumption, review forecasts, or explain your tariff bill today?`
        : `Hello! I am GridVision Assistant, operating in **${persona.toUpperCase()}** scope for **${activeEntity}**. How can I help you analyze telemetry, forecast trends, or explain tariff calculations today?`;
    return [
      {
        id: 'init-1',
        sender: 'assistant',
        text: initialGreeting,
        timestamp: 'Just now',
      },
    ];
  });

  const [isTyping, setIsTyping] = useState<boolean>(false);

  // Auto-scroll on new message or typing state change
  useEffect(() => {
    if (activeTab === 'chat' || activeFeature === 'general_chat') {
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages, isTyping, activeTab, activeFeature]);

  // Load questionnaire when switching to a dedicated feature
  useEffect(() => {
    if (persona !== 'household' || activeFeature === 'general_chat') return;

    if (!questionnaireSchemas[activeFeature]) {
      setIsLoadingSchema(true);
      setSchemaError(null);
      analyticsService
        .getResidentialQuestionnaire(activeFeature)
        .then((schema) => {
          setQuestionnaireSchemas((prev) => ({ ...prev, [activeFeature]: schema }));
        })
        .catch((err) => {
          setSchemaError(err instanceof Error ? err.message : 'Failed to load feature questionnaire.');
        })
        .finally(() => {
          setIsLoadingSchema(false);
        });
    }
  }, [activeFeature, persona, questionnaireSchemas]);

  const handleSend = async (text: string) => {
    if (!text.trim() || isTyping) return;

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

    const formattedHistory = messages
      .filter((m) => m.id !== 'init-1' && !m.id.startsWith('init-'))
      .slice(-6)
      .map((m) => ({
        role: m.sender === 'user' ? ('user' as const) : ('assistant' as const),
        content: m.text,
      }));

    try {
      const res = await analyticsService.askAssistant(trimmed, persona, activeEntity, formattedHistory);
      const replyMsg: ChatMessage = {
        id: `ast-${Date.now() + 1}`,
        sender: 'assistant',
        text: res.answer,
        timestamp: 'Just now',
        mode: res.mode,
        citations: res.citations || [],
        provenance: res.provenance,
        assumptions: res.assumptions || [],
        limitations: res.limitations || [],
        missingInformation: res.missing_information || [],
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

  // Run feature calculations
  const handleFeatureSubmit = async (formData: Record<string, any>) => {
    setSavedFormData((prev) => ({ ...prev, [activeFeature]: formData }));
    setIsCalculating(true);
    setCalculationError(null);

    const meterId = (activeEntity || '2254213').replace(/METER-/i, '');

    try {
      if (activeFeature === 'house_energy_planning') {
        const payload = {
          ...formData,
          meter_id: meterId,
        };
        const raw = await analyticsService.planHouseEnergy(payload);
        const result: HouseEnergyPlanningResult = (raw as any)?.results || raw;
        setHousePlanningResult(result);

        const rec = result.recommended_plan;
        const summaryText = `🏠 **New House Energy Plan Calculated**:\n- **Preliminary Connected Load:** ${Number(result.preliminary_connected_load_kw || 0).toFixed(2)} kW\n- **Diversified Peak Demand (IS 732):** ${Number(result.diversified_maximum_demand_kw || 0).toFixed(2)} kW\n- **Recommended Tier:** ${rec?.tier_name || 'Recommended'} (≈ ${Math.round(rec?.estimated_monthly_consumption_kwh || 0)} kWh/month, ₹${Math.round(rec?.estimated_monthly_bill_inr || 0).toLocaleString('en-IN')}/month)\n${result.solar_potential_analysis ? `- **Rooftop Solar PV:** ${result.solar_potential_analysis.recommendedSystemKwp} kWp generating ≈ ${result.solar_potential_analysis.estimatedMonthlyGenerationKwh} kWh/mo with payback of ${result.solar_potential_analysis.simplePaybackYears || 'N/A'} years\n` : ''}\nYou can review the complete equipment schedules and load details above, or ask me any questions!`;
        setMessages((prev) => [
          ...prev,
          {
            id: `plan-${Date.now()}`,
            sender: 'assistant',
            text: summaryText,
            timestamp: 'Just now',
          },
        ]);
      } else if (activeFeature === 'appliance_analysis') {
        const payload = {
          ...formData,
          meter_id: meterId,
        };
        const raw = await analyticsService.analyzeApplianceScenario(payload);
        const result: ApplianceScenarioResult = (raw as any)?.results || raw;
        setApplianceResult(result);

        const summaryText = `⚡ **Appliance Scenario Assessment Completed**:\n- **Verdict:** ${result.recommendation_verdict || 'Completed'}\n- **Net Upfront Outlay:** ₹${Math.round(result.net_upfront_investment_inr || 0).toLocaleString('en-IN')}\n- **Annual Bill Savings:** ₹${Math.round(result.annual_cost_savings_inr || 0).toLocaleString('en-IN')} (${Math.round(result.annual_energy_savings_kwh || 0)} kWh/yr)\n- **Simple Payback:** ${result.simple_payback_years !== undefined ? `${result.simple_payback_years} years` : 'Immediate'}\n- **7-Year Net Lifetime Savings:** ₹${Math.round(result.net_lifetime_savings_inr || 0).toLocaleString('en-IN')}\n- **CO₂ Reduction:** ${Number(result.co2_reduction_kg_per_year || 0).toFixed(1)} kg CO₂/year (CEA benchmark)\n\nAsk me anytime for guidance on appliance models or rebate programs!`;
        setMessages((prev) => [
          ...prev,
          {
            id: `appliance-${Date.now()}`,
            sender: 'assistant',
            text: summaryText,
            timestamp: 'Just now',
          },
        ]);
      } else if (activeFeature === 'cost_management') {
        const payload = {
          ...formData,
          meter_id: meterId,
        };
        const raw = await analyticsService.manageEnergyCost(payload);
        const result: CostManagementResult = (raw as any)?.results || raw;
        setCostResult(result);

        const pkg = result.package_recommendations;
        const summaryText = `📉 **Personalized Energy Cost Management Plan**:\n- **Current Baseline:** ${Math.round(result.current_monthly_baseline_kwh || 0)} kWh/mo (≈ ₹${Math.round(result.current_monthly_bill_inr || 0).toLocaleString('en-IN')}/mo)\n- **Achievable Monthly Savings:** ₹${Math.round(result.achievable_monthly_savings_inr || 0).toLocaleString('en-IN')}/mo (₹${Math.round(result.achievable_annual_savings_inr || 0).toLocaleString('en-IN')}/year)\n- **Recommended Package:** ${pkg?.packageName || 'Optimized Strategy'} (Cuts bill by ${pkg?.estimatedBillReductionPct || 0}% with blended payback of ${pkg?.blendedPaybackYears || 'Immediate'} yrs)\n- **Identified Strategies:** ${result.strategies?.length || 0} verified actions across Zero-Cost Behavioral, Quick Wins, and Equipment Retrofits.\n\nAsk me how to implement any specific strategy!`;
        setMessages((prev) => [
          ...prev,
          {
            id: `cost-${Date.now()}`,
            sender: 'assistant',
            text: summaryText,
            timestamp: 'Just now',
          },
        ]);
      }
    } catch (err) {
      setCalculationError(err instanceof Error ? err.message : 'Calculation failed in backend analytics engine.');
    } finally {
      setIsCalculating(false);
    }
  };

  const handleAskFollowUpFromResults = (promptText: string) => {
    setActiveTab('chat');
    handleSend(promptText);
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem', maxWidth: '1050px', margin: '0 auto', width: '100%', padding: '0.5rem 0 2rem 0' }}>
      {/* Header */}
      <div
        style={{
          background: 'var(--gv-bg-surface)',
          border: '1px solid var(--gv-border-subtle)',
          borderRadius: 'var(--gv-radius-lg)',
          padding: '1.5rem 1.75rem',
          boxShadow: 'var(--gv-shadow-sm)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.85rem' }}>
          <div
            style={{
              width: '44px',
              height: '44px',
              borderRadius: 'var(--gv-radius-md)',
              background: 'linear-gradient(135deg, var(--gv-color-smart-teal), var(--gv-color-grid-blue))',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              flexShrink: 0,
            }}
          >
            <Bot size={24} color="#FFFFFF" />
          </div>
          <div>
            <h1 style={{ fontSize: '1.45rem', fontWeight: 800, color: 'var(--gv-color-midnight-navy)', margin: 0, letterSpacing: '-0.02em' }}>
              Residential Energy Intelligence Platform
            </h1>
            <p style={{ fontSize: '0.85rem', color: 'var(--gv-text-secondary)', margin: '0.25rem 0 0 0' }}>
              Conversational intelligence & dedicated engineering analytics grounded in verified telemetry ({persona.toUpperCase()} scope • OBJECTID {(activeEntity || '2254213').replace(/METER-/i, '')}).
            </p>
          </div>
        </div>
      </div>

      {/* Feature Selector Cards for Residential Persona */}
      {persona === 'household' && (
        <FeatureEntryCards
          activeFeature={activeFeature}
          onSelectFeature={(featId) => {
            setActiveFeature(featId);
            setActiveTab('workflow');
            setCalculationError(null);
          }}
        />
      )}

      {/* Active Dedicated Feature View */}
      {persona === 'household' && activeFeature !== 'general_chat' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          {/* Sub-view Navigation Bar */}
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              backgroundColor: '#FFFFFF',
              borderRadius: '10px',
              border: '1px solid #E2E8F0',
              padding: '0.6rem 1rem',
            }}
          >
            <div style={{ display: 'flex', gap: '0.5rem' }}>
              <button
                type="button"
                onClick={() => setActiveTab('workflow')}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.35rem',
                  padding: '0.45rem 0.85rem',
                  borderRadius: '6px',
                  border: activeTab === 'workflow' ? '2px solid #00B8A9' : '1px solid #CBD5E1',
                  backgroundColor: activeTab === 'workflow' ? '#E0F7F5' : '#FFFFFF',
                  color: activeTab === 'workflow' ? '#00A396' : '#475569',
                  fontWeight: activeTab === 'workflow' ? 700 : 500,
                  fontSize: '0.8rem',
                  cursor: 'pointer',
                }}
              >
                <Sliders size={14} />
                <span>Feature Workflow</span>
              </button>

              <button
                type="button"
                onClick={() => setActiveTab('chat')}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.35rem',
                  padding: '0.45rem 0.85rem',
                  borderRadius: '6px',
                  border: activeTab === 'chat' ? '2px solid #00B8A9' : '1px solid #CBD5E1',
                  backgroundColor: activeTab === 'chat' ? '#E0F7F5' : '#FFFFFF',
                  color: activeTab === 'chat' ? '#00A396' : '#475569',
                  fontWeight: activeTab === 'chat' ? 700 : 500,
                  fontSize: '0.8rem',
                  cursor: 'pointer',
                }}
              >
                <MessageSquare size={14} />
                <span>Assistant Chat</span>
              </button>
            </div>

            <button
              type="button"
              onClick={() => setActiveFeature('general_chat')}
              style={{
                fontSize: '0.75rem',
                color: '#64748B',
                background: 'transparent',
                border: 'none',
                cursor: 'pointer',
                textDecoration: 'underline',
              }}
            >
              Switch to General Chat
            </button>
          </div>

          {/* Workflow View Container */}
          {activeTab === 'workflow' && (
            <div>
              {calculationError && (
                <div
                  style={{
                    backgroundColor: '#FEF2F2',
                    border: '1px solid #FECACA',
                    borderRadius: '8px',
                    padding: '0.85rem',
                    color: '#B91C1C',
                    fontSize: '0.82rem',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '0.5rem',
                    marginBottom: '1rem',
                  }}
                >
                  <AlertTriangle size={16} />
                  <span>{calculationError}</span>
                </div>
              )}

              {/* Feature 1: New House Energy Planning */}
              {activeFeature === 'house_energy_planning' && (
                housePlanningResult ? (
                  <HousePlanningResultsView
                    result={housePlanningResult}
                    onAskFollowUp={handleAskFollowUpFromResults}
                    onEditInputs={() => setHousePlanningResult(null)}
                  />
                ) : questionnaireSchemas.house_energy_planning ? (
                  <SchemaQuestionnaire
                    schema={questionnaireSchemas.house_energy_planning}
                    defaultValues={savedFormData.house_energy_planning}
                    onSubmit={handleFeatureSubmit}
                    isSubmitting={isCalculating}
                  />
                ) : (
                  <div style={{ padding: '2rem', textAlign: 'center', color: '#64748B', fontSize: '0.85rem' }}>
                    {isLoadingSchema ? 'Loading House Energy Planning Specifications...' : schemaError || 'Initializing...'}
                  </div>
                )
              )}

              {/* Feature 2: Appliance Purchase, Sale & Upgrade */}
              {activeFeature === 'appliance_analysis' && (
                applianceResult ? (
                  <ApplianceAnalysisResultsView
                    result={applianceResult}
                    onAskFollowUp={handleAskFollowUpFromResults}
                    onEditInputs={() => setApplianceResult(null)}
                  />
                ) : questionnaireSchemas.appliance_analysis ? (
                  <SchemaQuestionnaire
                    schema={questionnaireSchemas.appliance_analysis}
                    defaultValues={savedFormData.appliance_analysis}
                    onSubmit={handleFeatureSubmit}
                    isSubmitting={isCalculating}
                  />
                ) : (
                  <div style={{ padding: '2rem', textAlign: 'center', color: '#64748B', fontSize: '0.85rem' }}>
                    {isLoadingSchema ? 'Loading Appliance Scenario Specifications...' : schemaError || 'Initializing...'}
                  </div>
                )
              )}

              {/* Feature 3: Personalized Energy Cost Management */}
              {activeFeature === 'cost_management' && (
                costResult ? (
                  <CostManagementResultsView
                    result={costResult}
                    onAskFollowUp={handleAskFollowUpFromResults}
                    onEditInputs={() => setCostResult(null)}
                  />
                ) : questionnaireSchemas.cost_management ? (
                  <SchemaQuestionnaire
                    schema={questionnaireSchemas.cost_management}
                    defaultValues={savedFormData.cost_management}
                    onSubmit={handleFeatureSubmit}
                    isSubmitting={isCalculating}
                  />
                ) : (
                  <div style={{ padding: '2rem', textAlign: 'center', color: '#64748B', fontSize: '0.85rem' }}>
                    {isLoadingSchema ? 'Loading Cost Management Strategy Specifications...' : schemaError || 'Initializing...'}
                  </div>
                )
              )}
            </div>
          )}
        </div>
      )}

      {/* Conversational Assistant Log (shown when on chat tab or in general_chat) */}
      {(activeFeature === 'general_chat' || activeTab === 'chat' || persona !== 'household') && (
        <>
          {/* Suggested Prompts Strip */}
          <div>
            <div style={{ fontSize: '0.72rem', fontWeight: 700, textTransform: 'uppercase', color: 'var(--gv-text-muted)', letterSpacing: '0.05em', marginBottom: '0.5rem' }}>
              Suggested Prompts for {persona.toUpperCase()}
            </div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem' }}>
              {suggestedPrompts.map((prompt, idx) => (
                <button
                  key={idx}
                  type="button"
                  disabled={isTyping}
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
                    cursor: isTyping ? 'not-allowed' : 'pointer',
                    opacity: isTyping ? 0.6 : 1,
                    transition: 'all 0.15s ease',
                  }}
                  onMouseEnter={(e) => {
                    if (!isTyping) {
                      e.currentTarget.style.borderColor = 'var(--gv-color-smart-teal)';
                      e.currentTarget.style.color = 'var(--gv-color-smart-teal)';
                    }
                  }}
                  onMouseLeave={(e) => {
                    if (!isTyping) {
                      e.currentTarget.style.borderColor = 'var(--gv-border-accent)';
                      e.currentTarget.style.color = 'var(--gv-text-primary)';
                    }
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
              minHeight: '440px',
              maxHeight: '600px',
              overflowY: 'auto',
              display: 'flex',
              flexDirection: 'column',
              gap: '1.25rem',
            }}
          >
            {messages.map((m) => {
              if (m.sender === 'assistant') {
                return <AssistantMessageBubble key={m.id} message={m} />;
              }

              return (
                <div
                  key={m.id}
                  style={{
                    display: 'flex',
                    gap: '0.75rem',
                    alignSelf: 'flex-end',
                    maxWidth: '85%',
                    alignItems: 'flex-start',
                  }}
                >
                  <div
                    style={{
                      background: 'var(--gv-color-midnight-navy)',
                      color: '#FFFFFF',
                      padding: '0.85rem 1.15rem',
                      borderRadius: '12px',
                      fontSize: '0.88rem',
                      lineHeight: 1.5,
                      boxShadow: '0 1px 2px rgba(11, 31, 51, 0.08)',
                    }}
                  >
                    <ChatMessageRenderer content={m.text} isUser={true} />
                  </div>

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
                      marginTop: '2px',
                    }}
                  >
                    <User size={18} color="#FFFFFF" />
                  </div>
                </div>
              );
            })}

            {isTyping && (
              <div style={{ display: 'flex', gap: '0.75rem', alignSelf: 'flex-start', alignItems: 'center' }}>
                <div
                  style={{
                    width: '34px',
                    height: '34px',
                    borderRadius: '50%',
                    background: 'linear-gradient(135deg, #00B8A9, #087EBD)',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    flexShrink: 0,
                  }}
                >
                  <Bot size={18} color="#FFFFFF" />
                </div>
                <div
                  style={{
                    padding: '0.65rem 1rem',
                    backgroundColor: '#F8FAFC',
                    borderRadius: '8px',
                    border: '1px solid #E2E8F0',
                    fontStyle: 'italic',
                    color: 'var(--gv-text-muted)',
                    fontSize: '0.82rem',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '0.5rem',
                  }}
                >
                  <Sparkles size={14} color="#00B8A9" />
                  <span>GridVision Assistant is analyzing telemetry and formulating response...</span>
                </div>
              </div>
            )}

            <div ref={messagesEndRef} />
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
              disabled={isTyping}
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
              disabled={isTyping || !inputPrompt.trim()}
              style={{
                padding: '0 1.5rem',
                borderRadius: 'var(--gv-radius-md)',
                background: isTyping || !inputPrompt.trim() ? '#94A3B8' : 'var(--gv-color-smart-teal)',
                color: '#FFFFFF',
                fontWeight: 700,
                fontSize: '0.88rem',
                border: 'none',
                cursor: isTyping || !inputPrompt.trim() ? 'not-allowed' : 'pointer',
                display: 'flex',
                alignItems: 'center',
                gap: '0.5rem',
                transition: 'background-color 0.15s ease',
              }}
            >
              <span>Send</span>
              <Send size={15} />
            </button>
          </form>

          {/* Verified Telemetry Footnote */}
          <div style={{ textAlign: 'center', fontSize: '0.72rem', color: 'var(--gv-text-muted)' }}>
            AI Assistant answers are strictly grounded in verified telemetry and machine learning demand projections.
          </div>
        </>
      )}
    </div>
  );
};
