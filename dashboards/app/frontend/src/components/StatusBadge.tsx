import React from 'react';
import { useLanguage } from '../i18n/LanguageContext';
import { displayValue } from '../i18n/displayValue';

export type StatusVariant =
  | 'healthy'
  | 'pass'
  | 'completed'
  | 'verified'
  | 'running'
  | 'starting'
  | 'active'
  | 'pending'
  | 'warning'
  | 'denied'
  | 'failed'
  | 'blocked'
  | 'unhealthy'
  | 'stopped'
  | 'unavailable'
  | 'not_run'
  | 'neutral';

interface StatusBadgeProps {
  status: string | null | undefined;
  variant?: StatusVariant;
  pulse?: boolean;
  size?: 'sm' | 'md' | 'lg';
  className?: string;
}

export const StatusBadge: React.FC<StatusBadgeProps> = ({
  status,
  variant,
  pulse = false,
  size = 'md',
  className = '',
}) => {
  const { lang } = useLanguage();
  const normalized = (status ?? 'UNKNOWN').toUpperCase();

  const getVariant = (): StatusVariant => {
    if (variant) return variant;
    switch (normalized) {
      case 'HEALTHY':
      case 'PASS':
      case 'COMPLETED':
      case 'VERIFIED':
      case 'PREFLIGHT_READY':
        return 'pass';
      case 'RUNNING':
      case 'STARTING':
      case 'CONNECTED':
      case 'LIVE':
        return 'running';
      case 'PENDING':
      case 'RECONNECTING':
      case 'CONNECTING':
      case 'WARNING':
      case 'RECORDING':
        return 'pending';
      case 'DENIED':
      case 'FAILED':
      case 'BLOCKED':
      case 'UNHEALTHY':
      case 'ERROR':
      case 'DISCONNECTED':
      case 'PREFLIGHT_BLOCKED':
        return 'failed';
      case 'STOPPED':
      case 'UNAVAILABLE':
      case 'NOT_RUN':
      case 'NOT_STARTED':
      case 'IDLE':
      default:
        return 'neutral';
    }
  };

  const currentVariant = getVariant();

  const variantStyles: Record<StatusVariant, { bg: string; dot: string }> = {
    pass: {
      bg: 'bg-emerald-950/70 text-emerald-300 border-emerald-800/60',
      dot: 'bg-emerald-400',
    },
    healthy: {
      bg: 'bg-emerald-950/70 text-emerald-300 border-emerald-800/60',
      dot: 'bg-emerald-400',
    },
    completed: {
      bg: 'bg-emerald-950/70 text-emerald-300 border-emerald-800/60',
      dot: 'bg-emerald-400',
    },
    verified: {
      bg: 'bg-emerald-950/70 text-emerald-300 border-emerald-800/60',
      dot: 'bg-emerald-400',
    },
    running: {
      bg: 'bg-blue-950/70 text-blue-300 border-blue-800/60',
      dot: 'bg-blue-400',
    },
    starting: {
      bg: 'bg-blue-950/70 text-blue-300 border-blue-800/60',
      dot: 'bg-blue-400',
    },
    active: {
      bg: 'bg-blue-950/70 text-blue-300 border-blue-800/60',
      dot: 'bg-blue-400',
    },
    pending: {
      bg: 'bg-amber-950/70 text-amber-300 border-amber-800/60',
      dot: 'bg-amber-400',
    },
    warning: {
      bg: 'bg-amber-950/70 text-amber-300 border-amber-800/60',
      dot: 'bg-amber-400',
    },
    denied: {
      bg: 'bg-rose-950/70 text-rose-300 border-rose-800/60',
      dot: 'bg-rose-400',
    },
    failed: {
      bg: 'bg-rose-950/70 text-rose-300 border-rose-800/60',
      dot: 'bg-rose-400',
    },
    blocked: {
      bg: 'bg-rose-950/70 text-rose-300 border-rose-800/60',
      dot: 'bg-rose-400',
    },
    unhealthy: {
      bg: 'bg-rose-950/70 text-rose-300 border-rose-800/60',
      dot: 'bg-rose-400',
    },
    stopped: {
      bg: 'bg-slate-900/90 text-slate-400 border-slate-750',
      dot: 'bg-slate-500',
    },
    unavailable: {
      bg: 'bg-slate-900/90 text-slate-400 border-slate-750',
      dot: 'bg-slate-500',
    },
    not_run: {
      bg: 'bg-slate-900/90 text-slate-400 border-slate-750',
      dot: 'bg-slate-500',
    },
    neutral: {
      bg: 'bg-slate-900/90 text-slate-400 border-slate-750',
      dot: 'bg-slate-500',
    },
  };

  const style = variantStyles[currentVariant];
  const sizeClasses = {
    sm: 'text-xs px-2 py-0.5 space-x-1.5',
    md: 'text-xs font-medium px-2.5 py-1 space-x-2',
    lg: 'text-sm font-medium px-3 py-1.5 space-x-2',
  }[size];

  const shouldPulse = pulse || currentVariant === 'running' || currentVariant === 'starting';

  return (
    <span
      className={`inline-flex items-center rounded-md border font-mono uppercase tracking-wider ${style.bg} ${sizeClasses} ${className}`}
      role="status"
    >
      <span
        className={`h-1.5 w-1.5 rounded-full ${style.dot} ${
          shouldPulse ? 'animate-subtle-pulse' : ''
        }`}
        aria-hidden="true"
      />
      <span title={normalized}>{displayValue(normalized, lang)}</span>
    </span>
  );
};
