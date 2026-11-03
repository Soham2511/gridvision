import React, { useState, useEffect, useRef } from 'react';
import {
  QuestionnaireSchema,
  QuestionField,
} from '../../types/residentialFeatures';
import { Sparkles, RotateCcw, AlertCircle, HelpCircle } from 'lucide-react';

interface SchemaQuestionnaireProps {
  schema: QuestionnaireSchema;
  defaultValues?: Record<string, any>;
  onSubmit: (formData: Record<string, any>) => void;
  isSubmitting?: boolean;
}

const buildInitialFormData = (
  schema: QuestionnaireSchema,
  defaults?: Record<string, any>
): Record<string, any> => {
  const initial: Record<string, any> = {};
  schema.fields.forEach((field) => {
    if (defaults && defaults[field.field_id] !== undefined && defaults[field.field_id] !== null) {
      initial[field.field_id] = defaults[field.field_id];
    } else if (field.default_value !== undefined && field.default_value !== null) {
      initial[field.field_id] = field.default_value;
    } else {
      if (field.input_type === 'boolean') initial[field.field_id] = false;
      else if (field.input_type === 'multi_select') initial[field.field_id] = field.default_value || [];
      else if (field.input_type === 'number' || field.input_type === 'currency') initial[field.field_id] = '';
      else initial[field.field_id] = '';
    }
  });
  return initial;
};

const FieldTooltip: React.FC<{ tooltipText: string; fieldLabel: string }> = ({ tooltipText, fieldLabel }) => {
  const [visible, setVisible] = useState(false);

  return (
    <div
      style={{ position: 'relative', display: 'inline-flex', alignItems: 'center', marginLeft: '4px' }}
      onMouseEnter={() => setVisible(true)}
      onMouseLeave={() => setVisible(false)}
      onFocus={() => setVisible(true)}
      onBlur={() => setVisible(false)}
    >
      <button
        type="button"
        aria-label={`Standards info for ${fieldLabel}`}
        title={tooltipText}
        onClick={(e) => {
          e.preventDefault();
          setVisible((prev) => !prev);
        }}
        style={{
          background: 'none',
          border: 'none',
          padding: '2px',
          cursor: 'pointer',
          display: 'inline-flex',
          alignItems: 'center',
          color: visible ? '#00B8A9' : '#94A3B8',
          transition: 'color 0.15s ease',
        }}
      >
        <HelpCircle size={14} />
      </button>

      {visible && (
        <div
          role="tooltip"
          style={{
            position: 'absolute',
            bottom: 'calc(100% + 7px)',
            left: '50%',
            transform: 'translateX(-50%)',
            width: '280px',
            backgroundColor: '#0B1F33',
            color: '#F8FAFC',
            fontSize: '0.73rem',
            lineHeight: 1.45,
            padding: '0.6rem 0.75rem',
            borderRadius: '6px',
            boxShadow: '0 4px 14px rgba(11, 31, 51, 0.28)',
            zIndex: 100,
            pointerEvents: 'none',
            textAlign: 'left',
          }}
        >
          <div
            style={{
              fontWeight: 700,
              color: '#00B8A9',
              marginBottom: '3px',
              fontSize: '0.67rem',
              textTransform: 'uppercase',
              letterSpacing: '0.04em',
            }}
          >
            Engineering Norm & Sizing Impact
          </div>
          <div>{tooltipText}</div>
          <div
            style={{
              position: 'absolute',
              top: '100%',
              left: '50%',
              transform: 'translateX(-50%)',
              width: 0,
              height: 0,
              borderLeft: '5px solid transparent',
              borderRight: '5px solid transparent',
              borderTop: '5px solid #0B1F33',
            }}
          />
        </div>
      )}
    </div>
  );
};

export const SchemaQuestionnaire: React.FC<SchemaQuestionnaireProps> = ({
  schema,
  defaultValues,
  onSubmit,
  isSubmitting = false,
}) => {
  // Initialize state once per feature schema
  const [formData, setFormData] = useState<Record<string, any>>(() =>
    buildInitialFormData(schema, defaultValues)
  );
  const [validationErrors, setValidationErrors] = useState<Record<string, string>>({});
  const activeFeatureIdRef = useRef<string>(schema.feature_id);

  // Only reset the form if the user switches to a different feature questionnaire
  useEffect(() => {
    if (activeFeatureIdRef.current !== schema.feature_id) {
      activeFeatureIdRef.current = schema.feature_id;
      setFormData(buildInitialFormData(schema, defaultValues));
      setValidationErrors({});
    }
  }, [schema.feature_id, defaultValues, schema]);

  const handleChange = (fieldId: string, val: any) => {
    setFormData((prev) => ({ ...prev, [fieldId]: val }));
    if (validationErrors[fieldId]) {
      setValidationErrors((prev) => {
        const next = { ...prev };
        delete next[fieldId];
        return next;
      });
    }
  };

  const isFieldVisible = (field: QuestionField): boolean => {
    if (!field.conditional_visibility) return true;
    const cond = field.conditional_visibility;
    const depVal = formData[cond.depends_on_field];

    switch (cond.operator) {
      case 'equals':
        return depVal === cond.expected_value;
      case 'not_equals':
        return depVal !== cond.expected_value;
      case 'in':
        return Array.isArray(cond.expected_value) && cond.expected_value.includes(depVal);
      case 'greater_than':
        return Number(depVal) > Number(cond.expected_value);
      default:
        return true;
    }
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const errors: Record<string, string> = {};

    schema.fields.forEach((field) => {
      if (!isFieldVisible(field)) return;
      const rawVal = formData[field.field_id];

      if (field.required) {
        if (rawVal === undefined || rawVal === null || rawVal === '') {
          errors[field.field_id] = `${field.label} is required.`;
          return;
        }
      }

      if (rawVal !== undefined && rawVal !== null && rawVal !== '') {
        if (field.input_type === 'number' || field.input_type === 'currency') {
          const num = Number(rawVal);
          if (isNaN(num)) {
            errors[field.field_id] = `${field.label} must be a valid number.`;
          } else {
            if (field.min_value !== undefined && field.min_value !== null && num < field.min_value) {
              errors[field.field_id] = `${field.label} must be at least ${field.min_value} ${field.unit || ''}`.trim() + '.';
            }
            if (field.max_value !== undefined && field.max_value !== null && num > field.max_value) {
              errors[field.field_id] = `${field.label} cannot exceed ${field.max_value} ${field.unit || ''}`.trim() + '.';
            }
          }
        }
      }
    });

    if (Object.keys(errors).length > 0) {
      setValidationErrors(errors);
      return;
    }

    // Prepare clean payload containing only visible fields
    const payload: Record<string, any> = {};
    schema.fields.forEach((field) => {
      if (isFieldVisible(field)) {
        let val = formData[field.field_id];
        if ((field.input_type === 'number' || field.input_type === 'currency') && val !== '' && val !== undefined) {
          val = Number(val);
        }
        payload[field.field_id] = val;
      }
    });

    onSubmit(payload);
  };

  const handleReset = () => {
    const initial: Record<string, any> = {};
    schema.fields.forEach((field) => {
      if (field.default_value !== undefined && field.default_value !== null) {
        initial[field.field_id] = field.default_value;
      } else {
        if (field.input_type === 'boolean') initial[field.field_id] = false;
        else if (field.input_type === 'multi_select') initial[field.field_id] = field.default_value || [];
        else if (field.input_type === 'number' || field.input_type === 'currency') initial[field.field_id] = '';
        else initial[field.field_id] = '';
      }
    });
    setFormData(initial);
    setValidationErrors({});
  };

  return (
    <form
      onSubmit={handleSubmit}
      style={{
        backgroundColor: '#FFFFFF',
        borderRadius: '12px',
        border: '1px solid #E2E8F0',
        padding: '1.5rem',
        boxShadow: '0 1px 3px rgba(11, 31, 51, 0.05)',
      }}
    >
      {/* Title & Description */}
      <div style={{ borderBottom: '1px solid #F1F5F9', paddingBottom: '1rem', marginBottom: '1.25rem' }}>
        <h2 style={{ fontSize: '1.15rem', fontWeight: 800, color: '#0B1F33', margin: 0 }}>
          {schema.title}
        </h2>
        <p style={{ fontSize: '0.8rem', color: '#64748B', margin: '0.25rem 0 0 0' }}>
          {schema.description}
        </p>
      </div>

      {/* Field Groups */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
        {schema.field_groups.map((groupName) => {
          const groupFields = schema.fields.filter(
            (f) => f.category === groupName && isFieldVisible(f)
          );
          if (groupFields.length === 0) return null;

          return (
            <div
              key={groupName}
              style={{
                backgroundColor: '#F8FAFC',
                borderRadius: '8px',
                border: '1px solid #E2E8F0',
                padding: '1.1rem',
              }}
            >
              <div
                style={{
                  fontSize: '0.78rem',
                  fontWeight: 700,
                  textTransform: 'uppercase',
                  color: '#087EBD',
                  letterSpacing: '0.04em',
                  marginBottom: '1rem',
                  borderBottom: '1px solid #E2E8F0',
                  paddingBottom: '0.35rem',
                }}
              >
                {groupName}
              </div>

              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
                  gap: '1rem',
                }}
              >
                {groupFields.map((field) => {
                  const error = validationErrors[field.field_id];
                  const value = formData[field.field_id] ?? '';

                  return (
                    <div
                      key={field.field_id}
                      style={{
                        display: 'flex',
                        flexDirection: 'column',
                        gap: '0.35rem',
                      }}
                    >
                      <label
                        htmlFor={`input-${field.field_id}`}
                        style={{
                          fontSize: '0.8rem',
                          fontWeight: 600,
                          color: '#1E293B',
                          display: 'flex',
                          alignItems: 'center',
                          gap: '0.3rem',
                        }}
                      >
                        <span>{field.label}</span>
                        {field.required && (
                          <span style={{ color: '#EF4444', fontSize: '0.75rem' }}>*</span>
                        )}
                        {field.unit && (
                          <span
                            style={{
                              fontSize: '0.68rem',
                              fontWeight: 500,
                              color: '#64748B',
                              backgroundColor: '#E2E8F0',
                              padding: '1px 5px',
                              borderRadius: '4px',
                            }}
                          >
                            {field.unit}
                          </span>
                        )}
                        {(field.tooltip || field.description) && (
                          <FieldTooltip
                            tooltipText={field.tooltip || field.description || ''}
                            fieldLabel={field.label}
                          />
                        )}
                      </label>

                      {/* Input based on input_type */}
                      {field.input_type === 'dropdown' ? (
                        <select
                          id={`input-${field.field_id}`}
                          value={value ?? ''}
                          onChange={(e) => handleChange(field.field_id, e.target.value)}
                          style={{
                            width: '100%',
                            padding: '0.55rem 0.75rem',
                            borderRadius: '6px',
                            border: error ? '1px solid #EF4444' : '1px solid #CBD5E1',
                            backgroundColor: '#FFFFFF',
                            fontSize: '0.85rem',
                            color: '#0F172A',
                            outline: 'none',
                            cursor: 'pointer',
                          }}
                        >
                          <option value="">Select option...</option>
                          {field.options?.map((opt) => (
                            <option key={opt.value} value={opt.value}>
                              {opt.label}
                            </option>
                          ))}
                        </select>
                      ) : field.input_type === 'boolean' ? (
                        <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center', marginTop: '0.2rem' }}>
                          <button
                            type="button"
                            onClick={() => handleChange(field.field_id, true)}
                            style={{
                              flex: 1,
                              padding: '0.45rem',
                              borderRadius: '6px',
                              border: value === true ? '2px solid #00B8A9' : '1px solid #CBD5E1',
                              backgroundColor: value === true ? '#E0F7F5' : '#FFFFFF',
                              color: value === true ? '#00A396' : '#64748B',
                              fontWeight: 600,
                              fontSize: '0.82rem',
                              cursor: 'pointer',
                            }}
                          >
                            Yes
                          </button>
                          <button
                            type="button"
                            onClick={() => handleChange(field.field_id, false)}
                            style={{
                              flex: 1,
                              padding: '0.45rem',
                              borderRadius: '6px',
                              border: value === false ? '2px solid #00B8A9' : '1px solid #CBD5E1',
                              backgroundColor: value === false ? '#E0F7F5' : '#FFFFFF',
                              color: value === false ? '#00A396' : '#64748B',
                              fontWeight: 600,
                              fontSize: '0.82rem',
                              cursor: 'pointer',
                            }}
                          >
                            No
                          </button>
                        </div>
                      ) : field.input_type === 'radio' ? (
                        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.4rem', marginTop: '0.2rem' }}>
                          {field.options?.map((opt) => {
                            const isSelected = value === opt.value;
                            return (
                              <button
                                key={opt.value}
                                type="button"
                                onClick={() => handleChange(field.field_id, opt.value)}
                                style={{
                                  padding: '0.4rem 0.75rem',
                                  borderRadius: '6px',
                                  border: isSelected ? '2px solid #00B8A9' : '1px solid #CBD5E1',
                                  backgroundColor: isSelected ? '#E0F7F5' : '#FFFFFF',
                                  color: isSelected ? '#00A396' : '#334155',
                                  fontSize: '0.78rem',
                                  fontWeight: isSelected ? 700 : 500,
                                  cursor: 'pointer',
                                }}
                              >
                                {opt.label}
                              </button>
                            );
                          })}
                        </div>
                      ) : field.input_type === 'multi_select' ? (
                        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.4rem', marginTop: '0.2rem' }}>
                          {field.options?.map((opt) => {
                            const currentArr: string[] = Array.isArray(value) ? value : [];
                            const isSelected = currentArr.includes(opt.value);
                            return (
                              <button
                                key={opt.value}
                                type="button"
                                onClick={() => {
                                  if (isSelected) {
                                    handleChange(
                                      field.field_id,
                                      currentArr.filter((v) => v !== opt.value)
                                    );
                                  } else {
                                    handleChange(field.field_id, [...currentArr, opt.value]);
                                  }
                                }}
                                style={{
                                  padding: '0.35rem 0.65rem',
                                  borderRadius: '6px',
                                  border: isSelected ? '2px solid #00B8A9' : '1px solid #CBD5E1',
                                  backgroundColor: isSelected ? '#E0F7F5' : '#FFFFFF',
                                  color: isSelected ? '#00A396' : '#475569',
                                  fontSize: '0.78rem',
                                  fontWeight: isSelected ? 700 : 500,
                                  cursor: 'pointer',
                                  display: 'inline-flex',
                                  alignItems: 'center',
                                  gap: '0.3rem',
                                }}
                              >
                                <span>{isSelected ? '✓' : '+'}</span>
                                <span>{opt.label}</span>
                              </button>
                            );
                          })}
                        </div>
                      ) : (
                        <div style={{ position: 'relative', display: 'flex', alignItems: 'center' }}>
                          {field.input_type === 'currency' && (
                            <span
                              style={{
                                position: 'absolute',
                                left: '10px',
                                fontSize: '0.85rem',
                                color: '#64748B',
                                fontWeight: 600,
                                pointerEvents: 'none',
                              }}
                            >
                              ₹
                            </span>
                          )}
                          <input
                            id={`input-${field.field_id}`}
                            type={field.input_type === 'number' || field.input_type === 'currency' ? 'number' : 'text'}
                            step="any"
                            value={value !== undefined && value !== null ? value : ''}
                            placeholder={field.placeholder || ''}
                            onChange={(e) => handleChange(field.field_id, e.target.value)}
                            style={{
                              width: '100%',
                              padding: '0.55rem 0.75rem',
                              paddingLeft: field.input_type === 'currency' ? '1.5rem' : '0.75rem',
                              borderRadius: '6px',
                              border: error ? '1px solid #EF4444' : '1px solid #CBD5E1',
                              backgroundColor: '#FFFFFF',
                              fontSize: '0.85rem',
                              color: '#0F172A',
                              outline: 'none',
                            }}
                          />
                        </div>
                      )}

                      {field.description && (
                        <div style={{ fontSize: '0.7rem', color: '#64748B', display: 'flex', alignItems: 'center', gap: '0.25rem' }}>
                          <HelpCircle size={12} color="#94A3B8" />
                          <span>{field.description}</span>
                        </div>
                      )}

                      {error && (
                        <div style={{ fontSize: '0.72rem', color: '#EF4444', display: 'flex', alignItems: 'center', gap: '0.25rem' }}>
                          <AlertCircle size={12} />
                          <span>{error}</span>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          );
        })}
      </div>

      {/* Action Buttons */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'flex-end',
          alignItems: 'center',
          gap: '0.75rem',
          marginTop: '1.5rem',
          paddingTop: '1rem',
          borderTop: '1px solid #F1F5F9',
        }}
      >
        <button
          type="button"
          onClick={handleReset}
          disabled={isSubmitting}
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '0.35rem',
            padding: '0.6rem 1rem',
            borderRadius: '6px',
            border: '1px solid #CBD5E1',
            backgroundColor: '#FFFFFF',
            color: '#475569',
            fontSize: '0.82rem',
            fontWeight: 600,
            cursor: isSubmitting ? 'not-allowed' : 'pointer',
          }}
        >
          <RotateCcw size={14} />
          <span>Reset Defaults</span>
        </button>

        <button
          type="submit"
          disabled={isSubmitting}
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '0.45rem',
            padding: '0.6rem 1.25rem',
            borderRadius: '6px',
            border: 'none',
            backgroundColor: isSubmitting ? '#94A3B8' : '#00B8A9',
            color: '#FFFFFF',
            fontSize: '0.85rem',
            fontWeight: 700,
            cursor: isSubmitting ? 'wait' : 'pointer',
            boxShadow: '0 2px 4px rgba(0, 184, 169, 0.25)',
            transition: 'background-color 0.15s ease',
          }}
        >
          <Sparkles size={16} />
          <span>{isSubmitting ? 'Calculating...' : 'Calculate Energy Plan'}</span>
        </button>
      </div>
    </form>
  );
};
