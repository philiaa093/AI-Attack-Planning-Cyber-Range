import React from 'react';
import {
  ClipboardCheck,
  Server,
  Eye,
  Layers,
  Brain,
  Shield,
  Terminal,
  FileText,
  Lock,
  Flag,
  ArrowRight,
} from 'lucide-react';
import type { PipelineStatus, PipelineStepKey, StepState } from '../../api/types';
import { StatusBadge } from '../StatusBadge';
import { useLanguage } from '../../i18n/LanguageContext';
import { displayValue } from '../../i18n/displayValue';

interface PipelineProps {
  pipeline: PipelineStatus;
}

interface StepMeta {
  key: PipelineStepKey;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
}

const PIPELINE_ORDER: StepMeta[] = [
  { key: 'PREFLIGHT', label: 'PREFLIGHT', icon: ClipboardCheck },
  { key: 'RANGE', label: 'RANGE', icon: Server },
  { key: 'OBSERVE', label: 'OBSERVE', icon: Eye },
  { key: 'STATE', label: 'STATE', icon: Layers },
  { key: 'PLAN', label: 'PLAN', icon: Brain },
  { key: 'SAFETY', label: 'SAFETY', icon: Shield },
  { key: 'EXECUTE', label: 'EXECUTE', icon: Terminal },
  { key: 'EVIDENCE', label: 'EVIDENCE', icon: FileText },
  { key: 'VERIFY', label: 'VERIFY', icon: Lock },
  { key: 'COMPLETE', label: 'COMPLETE', icon: Flag },
];

const STEP_LABELS_VI: Record<PipelineStepKey, string> = {
  PREFLIGHT: 'Kiểm tra',
  RANGE: 'Môi trường',
  OBSERVE: 'Quan sát',
  STATE: 'Trạng thái',
  PLAN: 'Kế hoạch',
  SAFETY: 'An toàn',
  EXECUTE: 'Thực thi',
  EVIDENCE: 'Bằng chứng',
  VERIFY: 'Xác minh',
  COMPLETE: 'Hoàn tất',
};

export const Pipeline: React.FC<PipelineProps> = ({ pipeline }) => {
  const { lang, t } = useLanguage();
  const steps = pipeline.steps || {};

  const getNodeColors = (state: StepState) => {
    switch (state) {
      case 'PASS':
      case 'COMPLETED':
        return {
          border: 'border-emerald-600/70',
          bg: 'bg-emerald-950/40',
          icon: 'text-emerald-400',
        };
      case 'RUNNING':
        return {
          border: 'border-blue-500/80',
          bg: 'bg-blue-950/40',
          icon: 'text-blue-400',
        };
      case 'DENIED':
      case 'BLOCKED':
      case 'FAILED':
        return {
          border: 'border-rose-600/80',
          bg: 'bg-rose-950/40',
          icon: 'text-rose-400',
        };
      case 'PENDING':
        return {
          border: 'border-amber-600/60',
          bg: 'bg-amber-950/30',
          icon: 'text-amber-400',
        };
      case 'NOT_RUN':
      default:
        return {
          border: 'border-slate-800',
          bg: 'bg-slate-900/60',
          icon: 'text-slate-500',
        };
    }
  };

  return (
    <div className="bg-[#111724] border border-slate-800/80 rounded-lg p-5 shadow-sm">
      <div className="flex items-center justify-between pb-3 border-b border-slate-800/60 mb-4">
        <div className="flex items-center space-x-2">
          <span className="text-xs font-semibold tracking-wider uppercase text-slate-400">
            {t('pipelineTitle')}
          </span>
          <span className="text-[11px] text-slate-500 font-mono">
            [{lang === 'vi' ? 'Trình tự tất định và rào chắn an toàn' : 'Deterministic Sequence & Safety Gate Barrier'}]
          </span>
        </div>
        {pipeline.current_step && (
          <div className="flex items-center space-x-2 text-xs">
            <span className="text-slate-400">{lang === 'vi' ? 'Bước hiện tại:' : 'Active Node:'}</span>
            <span className="font-mono text-blue-400 font-semibold">{displayValue(pipeline.current_step, lang)}</span>
          </div>
        )}
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-5 lg:grid-cols-10 gap-2 items-center">
        {PIPELINE_ORDER.map((step, idx) => {
          const state: StepState = (steps[step.key] as StepState) || 'NOT_RUN';
          const colors = getNodeColors(state);
          const Icon = step.icon;
          const isRunning = state === 'RUNNING';

          return (
            <div key={step.key} className="flex items-center">
              <div
                className={`w-full flex flex-col items-center justify-center p-2.5 rounded-lg border text-center transition-all ${
                  colors.border
                } ${colors.bg} ${isRunning ? 'ring-1 ring-blue-500/50 animate-subtle-pulse' : ''}`}
              >
                <div className="p-1.5 rounded-full mb-1 bg-slate-900/80">
                  <Icon className={`w-4 h-4 ${colors.icon}`} />
                </div>
                <span className="text-[11px] font-mono font-medium text-slate-200 tracking-tight">
                  {lang === 'vi' ? STEP_LABELS_VI[step.key] : step.label}
                </span>
                <div className="mt-1.5 scale-90 origin-center">
                  <StatusBadge status={state} size="sm" pulse={isRunning} />
                </div>
              </div>
              {idx < PIPELINE_ORDER.length - 1 && (
                <div className="hidden lg:flex items-center justify-center px-1 text-slate-600">
                  <ArrowRight className="w-3 h-3 text-slate-600" />
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};
