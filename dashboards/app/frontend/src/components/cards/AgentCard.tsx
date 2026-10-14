import React from 'react';
import { Cpu, Activity, AlertTriangle } from 'lucide-react';
import type { AgentStatus, RunStatus } from '../../api/types';
import { StatusBadge } from '../StatusBadge';
import { useLanguage } from '../../i18n/LanguageContext';
import { displayValue } from '../../i18n/displayValue';

interface AgentCardProps {
  agent: AgentStatus;
  run: RunStatus;
}

export const AgentCard: React.FC<AgentCardProps> = ({ agent, run }) => {
  const { lang, t } = useLanguage();
  const isFallback =
    agent.fallback_reason !== null ||
    (agent.requested_mode &&
      agent.actual_mode &&
      agent.requested_mode !== agent.actual_mode &&
      agent.actual_mode !== 'NOT_RUN');

  return (
    <div className="bg-[#111724] border border-slate-800/80 rounded-lg p-4 flex flex-col justify-between shadow-sm hover:border-slate-700/60 transition-colors">
      <div className="flex items-center justify-between pb-3 border-b border-slate-800/60">
        <div className="flex items-center space-x-2 text-slate-300">
          <Cpu className="w-4 h-4 text-indigo-400" />
          <span className="text-xs font-semibold tracking-wider uppercase text-slate-400">{t('autonomousAgent')}</span>
        </div>
        <StatusBadge status={agent.state} />
      </div>

      <div className="mt-3 space-y-2 text-xs">
        <div className="flex justify-between items-center">
          <span className="text-slate-400">{lang === 'vi' ? 'Chế độ điều khiển' : 'Control Mode'}</span>
          <span className="font-mono text-xs px-2 py-0.5 rounded font-semibold bg-blue-950/60 text-blue-300 border border-blue-900/40">
            {displayValue(agent.control_mode || run.control_mode || 'AUTONOMOUS', lang)}
          </span>
        </div>

        <div className="flex justify-between items-center">
          <span className="text-slate-400">{lang === 'vi' ? 'Bộ lập kế hoạch' : 'Planner (Req / Actual)'}</span>
          <span className="font-mono text-slate-200">
            <span className="text-indigo-300">{displayValue(agent.requested_mode || agent.planner || 'RULE', lang)}</span>
            <span className="text-slate-500 mx-1">→</span>
            <span className={isFallback ? 'text-amber-400 font-semibold' : 'text-slate-200'}>
              {displayValue(agent.actual_mode || 'NOT_RUN', lang)}
            </span>
          </span>
        </div>

        {isFallback && agent.fallback_reason && (
          <div className="p-1.5 rounded bg-amber-950/30 border border-amber-900/50 text-[10px] text-amber-300 flex items-center justify-between">
            <span className="flex items-center space-x-1">
              <AlertTriangle className="w-3 h-3 text-amber-400 shrink-0" />
              <span>{lang === 'vi' ? 'Dự phòng' : 'Fallback'}</span>
            </span>
            <span className="font-mono">{displayValue(agent.fallback_reason, lang)}</span>
          </div>
        )}

        {(agent.provider || agent.model) && (
          <div className="flex justify-between items-center text-[11px]">
            <span className="text-slate-400">{lang === 'vi' ? "Nhà cung cấp / Mô hình" : "Provider / Model"}</span>
            <span className="font-mono text-slate-300 truncate max-w-[150px]">
              {agent.provider || (lang === 'vi' ? 'mặc định' : 'default')}:{agent.model || (lang === 'vi' ? 'chưa rõ' : 'unknown')}
            </span>
          </div>
        )}

        <div className="flex justify-between items-center">
          <span className="text-slate-400">{t('phase')}</span>
          <span className="font-mono text-slate-300">{displayValue(agent.current_phase || '—', lang)}</span>
        </div>

        <div className="flex justify-between items-center">
          <span className="text-slate-400">{t('factsCount')}</span>
          <span className="font-mono text-slate-200 font-semibold">{agent.facts_count}</span>
        </div>

        <div className="flex justify-between items-center">
          <span className="text-slate-400">{t('decisionsCount')}</span>
          <span className="font-mono text-slate-200 font-semibold">{run.decisions_count}</span>
        </div>

        {((agent.pause_count ?? 0) > 0 || (agent.operator_approvals ?? 0) > 0) && (
          <div className="flex justify-between items-center text-[11px] text-slate-400 pt-1 border-t border-slate-800/40">
            <span>{lang === 'vi' ? "Lần tạm dừng / Phê duyệt" : "Pauses / Approvals"}</span>
            <span className="font-mono text-slate-300">
              {agent.pause_count ?? 0} / {agent.operator_approvals ?? 0}
            </span>
          </div>
        )}
      </div>

      <div className="mt-3 pt-2 border-t border-slate-800/40 text-[10px] text-slate-400 flex justify-between items-center">
        <span className="flex items-center space-x-1">
          <Activity className="w-3 h-3 text-slate-400" />
          <span>{lang === 'vi' ? "Hành động hiện tại" : "Current Action"}</span>
        </span>
        <span className="font-mono text-slate-300 truncate max-w-[130px]" title={agent.current_action || (lang === 'vi' ? 'Chưa có' : 'None')}>
          {agent.current_action || '—'}
        </span>
      </div>
    </div>
  );
};
