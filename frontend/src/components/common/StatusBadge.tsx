import React from 'react';
import { AlertCircle, AlertTriangle, CheckCircle2, Info } from 'lucide-react';
import { SeverityLevel } from '../../types/analytics';

interface StatusBadgeProps {
  status: SeverityLevel | 'neutral' | string;
  label?: string;
  showIcon?: boolean;
}

export const StatusBadge: React.FC<StatusBadgeProps> = ({
  status,
  label,
  showIcon = true,
}) => {
  const normalizedStatus = status.toLowerCase();

  const getStyleClass = () => {
    switch (normalizedStatus) {
      case 'critical':
      case 'danger':
        return 'gv-badge-danger';
      case 'warning':
      case 'elevated':
        return 'gv-badge-warning';
      case 'success':
      case 'resolved':
      case 'low':
        return 'gv-badge-success';
      case 'info':
      case 'investigating':
      case 'confirmed':
        return 'gv-badge-info';
      default:
        return 'gv-badge-neutral';
    }
  };

  const getIcon = () => {
    switch (normalizedStatus) {
      case 'critical':
      case 'danger':
        return <AlertCircle size={12} />;
      case 'warning':
      case 'elevated':
        return <AlertTriangle size={12} />;
      case 'success':
      case 'resolved':
        return <CheckCircle2 size={12} />;
      case 'info':
      case 'investigating':
      default:
        return <Info size={12} />;
    }
  };

  const displayLabel = label || status.charAt(0).toUpperCase() + status.slice(1);

  return (
    <span className={`gv-badge ${getStyleClass()}`}>
      {showIcon && getIcon()}
      <span>{displayLabel}</span>
    </span>
  );
};
