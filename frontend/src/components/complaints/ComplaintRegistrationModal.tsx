import React, { useState, useEffect } from 'react';
import {
  X,
  ArrowLeft,
  ArrowRight,
  ShieldAlert,
  AlertTriangle,
  CheckCircle,
  XCircle,
  Loader2,
  Sparkles,
  Info,
} from 'lucide-react';
import {
  Complaint,
  ComplaintCategory,
  CategoryFormField,
  SubmitComplaintPayload,
} from '../../types/complaints';
import { complaintService } from '../../services/complaintService';
import { getCategoryIcon } from './ComplaintCard';

interface ComplaintRegistrationModalProps {
  isOpen: boolean;
  onClose: () => void;
  onComplaintSubmitted: (complaint: Complaint) => void;
  categories: ComplaintCategory[];
  isLoadingCategories?: boolean;
}

export const ComplaintRegistrationModal: React.FC<ComplaintRegistrationModalProps> = ({
  isOpen,
  onClose,
  onComplaintSubmitted,
  categories,
  isLoadingCategories = false,
}) => {
  const [selectedCategory, setSelectedCategory] = useState<ComplaintCategory | null>(null);
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [categoryData, setCategoryData] = useState<Record<string, any>>({});
  const [formErrors, setFormErrors] = useState<Record<string, string>>({});

  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submissionStep, setSubmissionStep] = useState<string>('');
  const [submissionResult, setSubmissionResult] = useState<Complaint | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  useEffect(() => {
    if (!isOpen) {
      setSelectedCategory(null);
      setTitle('');
      setDescription('');
      setCategoryData({});
      setFormErrors({});
      setIsSubmitting(false);
      setSubmissionResult(null);
      setErrorMessage(null);
      setSubmissionStep('');
    }
  }, [isOpen]);

  if (!isOpen) return null;

  const handleSelectCategory = (cat: ComplaintCategory) => {
    setSelectedCategory(cat);
    const defaults: Record<string, any> = {};
    cat.fields.forEach((f) => {
      if (f.default_value !== undefined) {
        defaults[f.field_id] = f.default_value;
      }
    });
    setCategoryData(defaults);
    setFormErrors({});
    setErrorMessage(null);
  };

  const handleFieldChange = (fieldId: string, val: any) => {
    setCategoryData((prev) => ({ ...prev, [fieldId]: val }));
    if (formErrors[fieldId]) {
      setFormErrors((prev) => {
        const next = { ...prev };
        delete next[fieldId];
        return next;
      });
    }
  };

  const handleMultiSelectToggle = (fieldId: string, optionValue: string) => {
    const current: string[] = Array.isArray(categoryData[fieldId]) ? categoryData[fieldId] : [];
    const next = current.includes(optionValue)
      ? current.filter((x) => x !== optionValue)
      : [...current, optionValue];
    handleFieldChange(fieldId, next);
  };

  const validateForm = (): boolean => {
    const errors: Record<string, string> = {};
    if (!title.trim()) {
      errors.title = 'Complaint title is required.';
    } else if (title.trim().length < 5) {
      errors.title = 'Title must be at least 5 characters.';
    }

    if (!description.trim()) {
      errors.description = 'Please provide a detailed description of the issue.';
    } else if (description.trim().length < 15) {
      errors.description = 'Description should be at least 15 characters to allow proper evaluation.';
    }

    if (selectedCategory) {
      selectedCategory.fields.forEach((field) => {
        if (field.required) {
          const val = categoryData[field.field_id];
          if (val === undefined || val === null || val === '' || (Array.isArray(val) && val.length === 0)) {
            errors[field.field_id] = `${field.label} is required.`;
          }
        }
      });
    }

    setFormErrors(errors);
    return Object.keys(errors).length === 0;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedCategory) return;
    if (!validateForm()) return;

    setIsSubmitting(true);
    setErrorMessage(null);
    setSubmissionStep('Validating with AI telemetry agent...');

    const payload: SubmitComplaintPayload = {
      category_id: selectedCategory.category_id,
      title: title.trim(),
      description: description.trim(),
      category_data: categoryData,
      customer_segment: 'RESIDENTIAL',
    };

    try {
      const stepTimer = setTimeout(() => {
        setSubmissionStep('Evaluating severity and scoring benchmark factors...');
      }, 1500);

      const result = await complaintService.submitComplaint(payload);
      clearTimeout(stepTimer);

      setSubmissionResult(result);
      onComplaintSubmitted(result);
    } catch (err: any) {
      setErrorMessage(
        err?.message || 'Failed to submit complaint. Please check your connection and try again.'
      );
    } finally {
      setIsSubmitting(false);
      setSubmissionStep('');
    }
  };

  const renderFieldInput = (field: CategoryFormField) => {
    const val = categoryData[field.field_id];
    const hasError = !!formErrors[field.field_id];

    const inputBaseStyle: React.CSSProperties = {
      width: '100%',
      padding: '0.6rem 0.85rem',
      borderRadius: '8px',
      border: hasError ? '1px solid #EF4444' : '1px solid var(--gv-border-medium)',
      background: hasError ? '#FEF2F2' : '#FFFFFF',
      fontSize: '0.82rem',
      color: 'var(--gv-text-primary)',
      outline: 'none',
      boxSizing: 'border-box',
    };

    switch (field.field_type) {
      case 'select':
        return (
          <select
            value={val || ''}
            onChange={(e) => handleFieldChange(field.field_id, e.target.value)}
            style={inputBaseStyle}
          >
            <option value="">Select an option...</option>
            {field.options?.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        );

      case 'multi_select':
        const selectedList: string[] = Array.isArray(val) ? val : [];
        return (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem', paddingTop: '0.25rem' }}>
            {field.options?.map((opt) => {
              const isSelected = selectedList.includes(opt.value);
              return (
                <button
                  type="button"
                  key={opt.value}
                  onClick={() => handleMultiSelectToggle(field.field_id, opt.value)}
                  style={{
                    padding: '0.4rem 0.75rem',
                    borderRadius: '6px',
                    fontSize: '0.75rem',
                    fontWeight: 600,
                    border: isSelected ? '1px solid #00B8A9' : '1px solid var(--gv-border-subtle)',
                    background: isSelected ? '#00B8A9' : 'var(--gv-bg-surface-subtle)',
                    color: isSelected ? '#FFFFFF' : 'var(--gv-text-secondary)',
                    cursor: 'pointer',
                    transition: 'all 0.15s ease',
                  }}
                >
                  {opt.label}
                </button>
              );
            })}
          </div>
        );

      case 'boolean':
        return (
          <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', cursor: 'pointer', marginTop: '0.25rem' }}>
            <input
              type="checkbox"
              checked={!!val}
              onChange={(e) => handleFieldChange(field.field_id, e.target.checked)}
              style={{ width: '16px', height: '16px', accentColor: '#00B8A9', cursor: 'pointer' }}
            />
            <span style={{ fontSize: '0.82rem', color: 'var(--gv-text-secondary)' }}>
              {field.helper_text || 'Yes / Applicable'}
            </span>
          </label>
        );

      case 'number':
        return (
          <input
            type="number"
            min={field.min_value}
            max={field.max_value}
            placeholder={field.placeholder || 'Enter number...'}
            value={val !== undefined ? val : ''}
            onChange={(e) =>
              handleFieldChange(
                field.field_id,
                e.target.value === '' ? '' : Number(e.target.value)
              )
            }
            style={inputBaseStyle}
          />
        );

      case 'datetime':
        return (
          <input
            type="datetime-local"
            value={val || ''}
            onChange={(e) => handleFieldChange(field.field_id, e.target.value)}
            style={inputBaseStyle}
          />
        );

      case 'textarea':
        return (
          <textarea
            rows={3}
            placeholder={field.placeholder || ''}
            value={val || ''}
            onChange={(e) => handleFieldChange(field.field_id, e.target.value)}
            style={{ ...inputBaseStyle, resize: 'vertical' }}
          />
        );

      case 'text':
      default:
        return (
          <input
            type="text"
            placeholder={field.placeholder || ''}
            value={val || ''}
            onChange={(e) => handleFieldChange(field.field_id, e.target.value)}
            style={inputBaseStyle}
          />
        );
    }
  };

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        background: 'rgba(11, 31, 51, 0.65)',
        backdropFilter: 'blur(4px)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 1000,
        padding: '1.5rem',
        fontFamily: 'var(--gv-font-sans)',
      }}
    >
      <div
        style={{
          background: '#FFFFFF',
          borderRadius: '16px',
          boxShadow: '0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04)',
          border: '1px solid var(--gv-border-subtle)',
          width: '100%',
          maxWidth: '780px',
          maxHeight: '90vh',
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
        }}
      >
        {/* Header */}
        <div
          style={{
            padding: '1.25rem 1.5rem',
            background: 'var(--gv-bg-surface-subtle)',
            borderBottom: '1px solid var(--gv-border-subtle)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
            {selectedCategory && !submissionResult && (
              <button
                type="button"
                onClick={() => setSelectedCategory(null)}
                style={{
                  width: '32px',
                  height: '32px',
                  borderRadius: '6px',
                  border: '1px solid var(--gv-border-medium)',
                  background: '#FFFFFF',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  cursor: 'pointer',
                  color: 'var(--gv-text-secondary)',
                }}
                title="Back to categories"
              >
                <ArrowLeft size={16} />
              </button>
            )}
            <div>
              <h2
                style={{
                  fontSize: '1.2rem',
                  fontWeight: 800,
                  color: 'var(--gv-color-midnight-navy)',
                  margin: 0,
                  lineHeight: 1.2,
                }}
              >
                {submissionResult
                  ? 'Complaint Submission Result'
                  : selectedCategory
                  ? `Register: ${selectedCategory.label}`
                  : 'Register a New Complaint'}
              </h2>
              <p style={{ fontSize: '0.75rem', color: 'var(--gv-text-muted)', margin: '0.2rem 0 0 0' }}>
                {submissionResult
                  ? `Ticket Reference: ${submissionResult.id}`
                  : selectedCategory
                  ? 'Fill in category details for AI telemetry validation and severity scoring.'
                  : 'Select the category that best describes your electrical or service issue.'}
              </p>
            </div>
          </div>

          <button
            onClick={onClose}
            style={{
              width: '32px',
              height: '32px',
              borderRadius: '6px',
              border: 'none',
              background: 'transparent',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: 'var(--gv-text-muted)',
              cursor: 'pointer',
            }}
          >
            <X size={20} />
          </button>
        </div>

        {/* Modal Body */}
        <div style={{ padding: '1.5rem', overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
          {/* STAGE 3: Submission Result View */}
          {submissionResult ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
              {submissionResult.status === 'REGISTERED' ? (
                <div
                  style={{
                    padding: '1.25rem',
                    borderRadius: '12px',
                    background: '#ECFDF5',
                    border: '1px solid #A7F3D0',
                    color: '#065F46',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'flex-start', gap: '0.75rem' }}>
                    <CheckCircle color="#059669" size={24} style={{ flexShrink: 0, marginTop: '2px' }} />
                    <div>
                      <h3 style={{ fontWeight: 800, fontSize: '1rem', margin: 0, color: '#065F46' }}>
                        Complaint Registered Successfully
                      </h3>
                      <p style={{ fontSize: '0.8rem', color: '#047857', margin: '0.35rem 0 0 0', lineHeight: 1.5 }}>
                        Your complaint has passed automated telemetry verification and has been assigned an initial priority based on the GridVision Severity Benchmark.
                      </p>
                    </div>
                  </div>

                  {submissionResult.severity_result && (
                    <div style={{ marginTop: '1rem', paddingTop: '1rem', borderTop: '1px solid #A7F3D0', display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <div>
                          <span style={{ fontSize: '0.7rem', fontWeight: 700, textTransform: 'uppercase', color: '#047857', display: 'block' }}>
                            Assigned Priority
                          </span>
                          <span style={{ fontSize: '1.15rem', fontWeight: 800, color: '#064E3B' }}>
                            {submissionResult.severity_result.severity_level} (Score: {submissionResult.severity_result.severity_score.toFixed(1)}/100)
                          </span>
                        </div>
                        <div style={{ textAlign: 'right' }}>
                          <span style={{ fontSize: '0.7rem', fontWeight: 700, textTransform: 'uppercase', color: '#047857', display: 'block' }}>
                            Benchmark Version
                          </span>
                          <span style={{ fontSize: '0.75rem', fontFamily: 'var(--gv-font-mono)', color: '#064E3B' }}>
                            {submissionResult.severity_result.benchmark_version}
                          </span>
                        </div>
                      </div>
                      <div style={{ fontSize: '0.78rem', background: 'rgba(255,255,255,0.8)', padding: '0.75rem', borderRadius: '8px', border: '1px solid #A7F3D0' }}>
                        <strong>Rationale: </strong>
                        {submissionResult.severity_result.scoring_rationale}
                      </div>
                    </div>
                  )}
                </div>
              ) : (
                <div
                  style={{
                    padding: '1.25rem',
                    borderRadius: '12px',
                    background: '#FFF1F2',
                    border: '1px solid #FECDD3',
                    color: '#9F1239',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'flex-start', gap: '0.75rem' }}>
                    <XCircle color="#E11D48" size={24} style={{ flexShrink: 0, marginTop: '2px' }} />
                    <div>
                      <h3 style={{ fontWeight: 800, fontSize: '1rem', margin: 0, color: '#9F1239' }}>
                        Automated Validation Finding: Contradicted / Invalid
                      </h3>
                      <p style={{ fontSize: '0.8rem', color: '#BE123C', margin: '0.35rem 0 0 0', lineHeight: 1.5 }}>
                        The complaint could not be registered automatically because active energy was continuously recorded on your smart meter during the reported outage window.
                      </p>
                    </div>
                  </div>

                  {submissionResult.validation_result && (
                    <div style={{ marginTop: '0.85rem', padding: '0.75rem', borderRadius: '8px', background: '#FFFFFF', border: '1px solid #FECDD3', fontSize: '0.78rem', color: '#9F1239' }}>
                      <strong>AI Telemetry Explanation: </strong>
                      {submissionResult.validation_result.explanation}
                    </div>
                  )}

                  {submissionResult.customer_care_escalation && (
                    <div style={{ marginTop: '0.85rem', paddingTop: '0.85rem', borderTop: '1px solid #FECDD3', fontSize: '0.78rem' }}>
                      <span style={{ fontWeight: 800, display: 'block', marginBottom: '2px' }}>Escalation Advice:</span>
                      <p style={{ margin: 0 }}>{submissionResult.customer_care_escalation.advisory}</p>
                      {submissionResult.customer_care_escalation.customer_care_contact && (
                        <p style={{ fontWeight: 700, margin: '4px 0 0 0' }}>
                          Customer Care Phone: {submissionResult.customer_care_escalation.customer_care_contact}
                        </p>
                      )}
                    </div>
                  )}
                </div>
              )}

              <div style={{ display: 'flex', justifyContent: 'flex-end', paddingTop: '1rem', borderTop: '1px solid var(--gv-border-subtle)' }}>
                <button
                  type="button"
                  onClick={onClose}
                  style={{
                    padding: '0.6rem 1.25rem',
                    borderRadius: '8px',
                    background: 'var(--gv-color-midnight-navy)',
                    color: '#FFFFFF',
                    fontWeight: 700,
                    fontSize: '0.8rem',
                    border: 'none',
                    cursor: 'pointer',
                  }}
                >
                  View in Complaints History
                </button>
              </div>
            </div>
          ) : !selectedCategory ? (
            /* STAGE 1: Category Selection Grid */
            <div>
              {isLoadingCategories ? (
                <div style={{ padding: '3rem 1rem', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: '0.5rem', color: 'var(--gv-text-muted)' }}>
                  <Loader2 className="animate-spin" color="#00B8A9" size={32} />
                  <span style={{ fontSize: '0.8rem' }}>Loading available complaint categories...</span>
                </div>
              ) : (
                <div
                  style={{
                    display: 'grid',
                    gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))',
                    gap: '0.85rem',
                  }}
                >
                  {categories.map((cat) => {
                    const isSafety = cat.safety_critical;
                    return (
                      <div
                        key={cat.category_id}
                        onClick={() => handleSelectCategory(cat)}
                        style={{
                          padding: '1.15rem',
                          borderRadius: '12px',
                          border: isSafety ? '1px solid #FECACA' : '1px solid var(--gv-border-subtle)',
                          background: isSafety ? '#FEF2F2' : '#FFFFFF',
                          cursor: 'pointer',
                          display: 'flex',
                          flexDirection: 'column',
                          justifyContent: 'space-between',
                          boxShadow: 'var(--gv-shadow-sm)',
                          transition: 'all 0.18s ease',
                        }}
                      >
                        <div>
                          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.65rem' }}>
                            <div
                              style={{
                                width: '36px',
                                height: '36px',
                                borderRadius: '8px',
                                background: isSafety ? '#FEE2E2' : 'var(--gv-bg-surface-subtle)',
                                border: '1px solid var(--gv-border-subtle)',
                                display: 'flex',
                                alignItems: 'center',
                                justifyContent: 'center',
                              }}
                            >
                              {getCategoryIcon(cat.icon_name, cat.category_id, 20)}
                            </div>
                            {isSafety && (
                              <span
                                style={{
                                  fontSize: '0.68rem',
                                  fontWeight: 800,
                                  color: '#DC2626',
                                  background: '#FEE2E2',
                                  border: '1px solid #FCA5A5',
                                  padding: '2px 7px',
                                  borderRadius: '999px',
                                  display: 'inline-flex',
                                  alignItems: 'center',
                                  gap: '0.25rem',
                                }}
                              >
                                <ShieldAlert size={11} color="#DC2626" /> Safety Critical
                              </span>
                            )}
                          </div>

                          <h3 style={{ fontSize: '0.92rem', fontWeight: 800, color: 'var(--gv-color-midnight-navy)', margin: '0 0 0.35rem 0' }}>
                            {cat.label}
                          </h3>
                          <p style={{ fontSize: '0.78rem', color: 'var(--gv-text-secondary)', lineHeight: 1.5, margin: 0 }}>
                            {cat.description}
                          </p>
                        </div>

                        <div
                          style={{
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'flex-end',
                            gap: '0.25rem',
                            fontSize: '0.75rem',
                            fontWeight: 700,
                            color: '#00B8A9',
                            marginTop: '0.85rem',
                            paddingTop: '0.65rem',
                            borderTop: '1px solid rgba(0,0,0,0.06)',
                          }}
                        >
                          <span>Select Category</span>
                          <ArrowRight size={13} />
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          ) : (
            /* STAGE 2: Dynamic Category Form */
            <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
              {/* Safety Precaution Banner */}
              {selectedCategory.safety_critical && (
                <div
                  style={{
                    padding: '1.15rem',
                    borderRadius: '12px',
                    background: '#FEF2F2',
                    border: '1px solid #FECACA',
                    color: '#991B1B',
                    display: 'flex',
                    alignItems: 'flex-start',
                    gap: '0.75rem',
                  }}
                >
                  <ShieldAlert color="#DC2626" size={24} style={{ flexShrink: 0, marginTop: '2px' }} />
                  <div style={{ fontSize: '0.78rem', lineHeight: 1.5 }}>
                    <h4 style={{ fontWeight: 800, fontSize: '0.9rem', color: '#991B1B', margin: '0 0 0.25rem 0' }}>
                      Immediate Electrical Danger Notice
                    </h4>
                    <p style={{ margin: 0 }}>
                      If you observe active sparking, burning smell, arcing, exposed conductors, or immediate risk of fire or electric shock,
                      <strong> do not rely on an asynchronous ticket</strong>. Switch off the main circuit breaker if safe to do so, evacuate the area, and immediately call emergency services or our 24/7 hotline.
                    </p>
                  </div>
                </div>
              )}

              {/* Error Message Alert */}
              {errorMessage && (
                <div
                  style={{
                    padding: '0.85rem',
                    borderRadius: '8px',
                    background: '#FEF2F2',
                    border: '1px solid #FECACA',
                    color: '#991B1B',
                    fontSize: '0.8rem',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '0.5rem',
                  }}
                >
                  <AlertTriangle size={16} color="#DC2626" />
                  <span>{errorMessage}</span>
                </div>
              )}

              {/* Title Input */}
              <div>
                <label style={{ display: 'block', fontSize: '0.75rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.04em', color: 'var(--gv-text-primary)', marginBottom: '0.35rem' }}>
                  Complaint Title <span style={{ color: '#EF4444' }}>*</span>
                </label>
                <input
                  type="text"
                  placeholder="e.g., Sudden complete power outage in entire house"
                  value={title}
                  onChange={(e) => {
                    setTitle(e.target.value);
                    if (formErrors.title) {
                      setFormErrors((prev) => {
                        const next = { ...prev };
                        delete next.title;
                        return next;
                      });
                    }
                  }}
                  style={{
                    width: '100%',
                    padding: '0.65rem 0.85rem',
                    borderRadius: '8px',
                    border: formErrors.title ? '1px solid #EF4444' : '1px solid var(--gv-border-medium)',
                    background: formErrors.title ? '#FEF2F2' : '#FFFFFF',
                    fontSize: '0.85rem',
                    color: 'var(--gv-text-primary)',
                    outline: 'none',
                    boxSizing: 'border-box',
                  }}
                />
                {formErrors.title && (
                  <span style={{ fontSize: '0.72rem', color: '#EF4444', marginTop: '3px', display: 'block' }}>{formErrors.title}</span>
                )}
              </div>

              {/* Detailed Description */}
              <div>
                <label style={{ display: 'block', fontSize: '0.75rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.04em', color: 'var(--gv-text-primary)', marginBottom: '0.35rem' }}>
                  Detailed Description <span style={{ color: '#EF4444' }}>*</span>
                </label>
                <textarea
                  rows={4}
                  placeholder="Provide detailed context: start time, whether neighbors are affected, appliances involved, observed smells or sounds..."
                  value={description}
                  onChange={(e) => {
                    setDescription(e.target.value);
                    if (formErrors.description) {
                      setFormErrors((prev) => {
                        const next = { ...prev };
                        delete next.description;
                        return next;
                      });
                    }
                  }}
                  style={{
                    width: '100%',
                    padding: '0.65rem 0.85rem',
                    borderRadius: '8px',
                    border: formErrors.description ? '1px solid #EF4444' : '1px solid var(--gv-border-medium)',
                    background: formErrors.description ? '#FEF2F2' : '#FFFFFF',
                    fontSize: '0.85rem',
                    color: 'var(--gv-text-primary)',
                    outline: 'none',
                    resize: 'vertical',
                    boxSizing: 'border-box',
                  }}
                />
                {formErrors.description ? (
                  <span style={{ fontSize: '0.72rem', color: '#EF4444', marginTop: '3px', display: 'block' }}>{formErrors.description}</span>
                ) : (
                  <span style={{ fontSize: '0.72rem', color: 'var(--gv-text-muted)', marginTop: '3px', display: 'block' }}>
                    Our AI validation agent checks this description against your smart meter telemetry. Please mention approximate times.
                  </span>
                )}
              </div>

              {/* Dynamic Category Fields */}
              {selectedCategory.fields && selectedCategory.fields.length > 0 && (
                <div style={{ paddingTop: '1rem', borderTop: '1px solid var(--gv-border-subtle)', display: 'flex', flexDirection: 'column', gap: '0.85rem' }}>
                  <h4 style={{ fontSize: '0.75rem', fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.04em', color: 'var(--gv-text-secondary)', margin: 0 }}>
                    {selectedCategory.label} Specific Details
                  </h4>
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: '0.85rem' }}>
                    {selectedCategory.fields.map((field) => (
                      <div key={field.field_id}>
                        <label style={{ display: 'block', fontSize: '0.75rem', fontWeight: 600, color: 'var(--gv-text-primary)', marginBottom: '0.25rem' }}>
                          {field.label} {field.required && <span style={{ color: '#EF4444' }}>*</span>}
                        </label>
                        {renderFieldInput(field)}
                        {field.helper_text && field.field_type !== 'boolean' && (
                          <span style={{ fontSize: '0.7rem', color: 'var(--gv-text-muted)', marginTop: '2px', display: 'block' }}>
                            {field.helper_text}
                          </span>
                        )}
                        {formErrors[field.field_id] && (
                          <span style={{ fontSize: '0.72rem', color: '#EF4444', marginTop: '2px', display: 'block' }}>
                            {formErrors[field.field_id]}
                          </span>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Guidance Notes */}
              {selectedCategory.guidance_notes && (
                <div
                  style={{
                    padding: '0.75rem 1rem',
                    borderRadius: '8px',
                    background: 'var(--gv-bg-surface-subtle)',
                    border: '1px solid var(--gv-border-subtle)',
                    fontSize: '0.75rem',
                    color: 'var(--gv-text-secondary)',
                    display: 'flex',
                    alignItems: 'flex-start',
                    gap: '0.5rem',
                  }}
                >
                  <Info size={16} color="var(--gv-text-muted)" style={{ flexShrink: 0, marginTop: '1px' }} />
                  <span>{selectedCategory.guidance_notes}</span>
                </div>
              )}

              {/* Action Buttons */}
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', paddingTop: '1rem', borderTop: '1px solid var(--gv-border-subtle)' }}>
                <button
                  type="button"
                  onClick={() => setSelectedCategory(null)}
                  disabled={isSubmitting}
                  style={{
                    padding: '0.55rem 1rem',
                    borderRadius: '6px',
                    fontSize: '0.78rem',
                    fontWeight: 600,
                    color: 'var(--gv-text-secondary)',
                    background: 'transparent',
                    border: 'none',
                    cursor: 'pointer',
                  }}
                >
                  Change Category
                </button>

                <button
                  type="submit"
                  disabled={isSubmitting}
                  style={{
                    padding: '0.65rem 1.35rem',
                    borderRadius: '8px',
                    background: 'var(--gv-color-smart-teal)',
                    color: '#FFFFFF',
                    fontWeight: 700,
                    fontSize: '0.82rem',
                    border: 'none',
                    cursor: isSubmitting ? 'not-allowed' : 'pointer',
                    boxShadow: '0 2px 4px rgba(0, 184, 169, 0.25)',
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '0.5rem',
                    opacity: isSubmitting ? 0.7 : 1,
                  }}
                >
                  {isSubmitting ? (
                    <>
                      <Loader2 size={16} className="animate-spin" />
                      <span>{submissionStep || 'Processing with AI Agents...'}</span>
                    </>
                  ) : (
                    <>
                      <Sparkles size={16} />
                      <span>Submit for AI Validation</span>
                    </>
                  )}
                </button>
              </div>
            </form>
          )}
        </div>
      </div>
    </div>
  );
};
