import React from 'react';
import { TimeRange } from '../../types/analytics';

interface TimeRangeSelectorProps {
  selectedRange: TimeRange;
  onChange: (range: TimeRange) => void;
  options?: TimeRange[];
}

export const TimeRangeSelector: React.FC<TimeRangeSelectorProps> = ({
  selectedRange,
  onChange,
  options = ['24h', '7d', '30d'],
}) => {
  return (
    <div
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        background: 'var(--gv-bg-surface-subtle)',
        padding: '3px',
        borderRadius: 'var(--gv-radius-md)',
        border: '1px solid var(--gv-border-subtle)',
      }}
    >
      {options.map((range) => {
        const isSelected = selectedRange === range;
        return (
          <button
            key={range}
            type="button"
            onClick={() => onChange(range)}
            style={{
              padding: '0.35rem 0.75rem',
              fontSize: '0.75rem',
              fontWeight: isSelected ? 700 : 500,
              borderRadius: 'var(--gv-radius-sm)',
              color: isSelected ? 'var(--gv-color-midnight-navy)' : 'var(--gv-text-secondary)',
              background: isSelected ? 'var(--gv-bg-surface)' : 'transparent',
              boxShadow: isSelected ? 'var(--gv-shadow-sm)' : 'none',
              border: isSelected ? '1px solid var(--gv-border-accent)' : '1px solid transparent',
              transition: 'all var(--gv-transition-fast)',
              cursor: 'pointer',
            }}
          >
            {range.toUpperCase()}
          </button>
        );
      })}
    </div>
  );
};
