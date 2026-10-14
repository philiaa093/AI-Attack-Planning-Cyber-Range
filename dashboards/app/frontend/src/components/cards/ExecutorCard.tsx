import React from 'react';
import { Terminal, CheckCircle2, XCircle } from 'lucide-react';
import type { SystemStatus } from '../../api/types';
import { StatusBadge } from '../StatusBadge';
import { useLanguage } from '../../i18n/LanguageContext';

interface ExecutorCardProps {
  system: SystemStatus;
}

export const ExecutorCard: React.FC<ExecutorCardProps> = ({ system }) => {
  const { lang, t } = useLanguage();
  const { safety, run, pipeline, agent } = system;
  const isSafetyDenied = pipeline.steps.SAFETY === 'DENIED' || safety.denials_count > 0;
  const dispatches = run.network_dispatches ?? safety.network_dispatches ?? 0;

  let executorState = 'IDLE';
  if (pipeline.steps.EXECUTE === 'RUNNING') {
    executorState = 'RUNNING';
  } else if (isSafetyDenied && dispatches === 0) {
    executorState = 'NOT CALLED';
  } else if (pipeline.steps.EXECUTE === 'BLOCKED') {
    executorState = 'BLOCKED';
  } else if (pipeline.steps.EXECUTE === 'PASS') {
    executorState = 'COMPLETED';
  } else if (pipeline.steps.EXECUTE === 'FAILED') {
    executorState = 'FAILED';
  }

  return (
    <div className="bg-[#111724] border border-slate-800/80 rounded-lg p-4 flex flex-col justify-between shadow-sm hover:border-slate-700/60 transition-colors">
      <div className="flex items-center justify-between pb-3 border-b border-slate-800/60">
        <div className="flex items-center space-x-2 text-slate-300">
          <Terminal className="w-4 h-4 text-cyan-400" />
          <span className="text-xs font-semibold tracking-wider uppercase text-slate-400">{t('controlledExecutor')}</span>
        </div>
        <StatusBadge
          status={executorState}
          variant={
            executorState === 'NOT CALLED'
              ? 'neutral'
              : executorState === 'RUNNING'
              ? 'running'
              : executorState === 'COMPLETED'
              ? 'pass'
              : executorState === 'BLOCKED'
              ? 'blocked'
              : 'neutral'
          }
        />
      </div>

      <div className="mt-3 space-y-2.5 text-xs">
        <div className="flex justify-between items-center">
          <span className="text-slate-400">{t('networkDispatches')}</span>
          <span
            className={`font-mono text-sm font-bold ${
              dispatches === 0 && isSafetyDenied ? 'text-amber-400' : 'text-slate-200'
            }`}
          >
            {dispatches}
          </span>
        </div>

        <div className="flex justify-between items-center">
          <span className="text-slate-400">{lang === 'vi' ? "Hành động hiện tại" : "Current Action"}</span>
          <span className="font-mono text-slate-300 truncate max-w-[140px]" title={agent.current_action || (lang === 'vi' ? 'Chưa có' : 'None')}>
            {agent.current_action || '—'}
          </span>
        </div>

        <div className="flex justify-between items-center">
          <span className="text-slate-400">{lang === 'vi' ? "Mục tiêu giới hạn" : "Target Bound"}</span>
          <span className="font-mono text-slate-300 truncate max-w-[140px]">
            {run.target || 'lab-ecommerce'}
          </span>
        </div>

        {isSafetyDenied && dispatches === 0 && (
          <div className="mt-1 p-2 rounded bg-slate-900 border border-slate-800 text-slate-300 text-[11px] flex items-center space-x-1.5">
            <XCircle className="w-3.5 h-3.5 text-rose-400 shrink-0" />
            <span className="font-mono text-[10px] text-rose-300 font-medium">
              {lang === 'vi' ? "Không có yêu cầu mạng nào được gửi (cổng an toàn đã chặn)" : "Zero network dispatch (Safety Gate blocked)"}
            </span>
          </div>
        )}

        {dispatches > 0 && (
          <div className="mt-1 p-2 rounded bg-emerald-950/30 border border-emerald-900/40 text-emerald-300 text-[11px] flex items-center space-x-1.5">
            <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
            <span className="font-mono text-[10px]">{lang === 'vi' ? "Đã ghi nhận các yêu cầu HTTP trong giới hạn" : "Bounded HTTP dispatches recorded"}</span>
          </div>
        )}
      </div>

      <div className="mt-3 pt-2 border-t border-slate-800/40 text-[10px] text-slate-400 flex justify-between">
        <span>{lang === 'vi' ? "Giới hạn thực thi" : "Execution Boundary"}</span>
        <span className="font-mono text-cyan-400/90 font-medium">{lang === 'vi' ? "Chỉ dùng REST có định kiểu" : "TYPED REST ONLY"}</span>
      </div>
    </div>
  );
};
