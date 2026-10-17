import React from 'react';
import { Bot, Target, Shield, Clock, Gauge, Zap } from 'lucide-react';
import type { AgentEvent, SystemStatus } from '../../api/types';
import { StatusBadge } from '../StatusBadge';
import { useLanguage } from '../../i18n/LanguageContext';
import { displayTool, displayValue } from '../../i18n/displayValue';

interface CurrentActivityProps {
  system: SystemStatus;
  latestEvent: AgentEvent | null;
}

export const CurrentActivity: React.FC<CurrentActivityProps> = ({
  system,
  latestEvent,
}) => {
  const { lang, t } = useLanguage();
  const { agent, run, safety } = system;
  const lastDecision = agent.last_decision;
  const budget = agent.budget_remaining || {};
  const execution = agent.current_execution;
  const verification = agent.last_verification;
  const isDenied = safety.denials_count > 0;

  return (
    <div className="bg-[#111724] border border-slate-800/80 rounded-lg p-4 flex flex-col h-[480px] shadow-sm justify-between">
      {/* Header */}
      <div className="flex items-center justify-between pb-3 border-b border-slate-800/60 shrink-0">
        <div className="flex items-center space-x-2">
          <Bot className="w-4 h-4 text-indigo-400" />
          <span className="text-xs font-semibold tracking-wider uppercase text-slate-400">
            {t.currentActivity}
          </span>
        </div>
        <StatusBadge status={agent.state} pulse={agent.state === 'RUNNING'} />
      </div>

      {/* Main Stats Grid */}
      <div className="grid grid-cols-2 gap-2 my-2 text-xs">
        <div className="p-2.5 rounded bg-slate-900/90 border border-slate-800/80">
          <span className="text-[10px] text-slate-400 uppercase tracking-wide block mb-1">
            {t.currentPhase}
          </span>
          <span className="font-mono text-sm font-semibold text-indigo-300">
            {displayValue(agent.current_phase || 'RECON', lang)}
          </span>
        </div>

        <div className="p-2.5 rounded bg-slate-900/90 border border-slate-800/80">
          <span className="text-[10px] text-slate-400 uppercase tracking-wide block mb-1">
            {t.iteration}
          </span>
          <span className="font-mono text-sm font-semibold text-slate-200">
            {latestEvent?.iteration ?? (run.state === 'RUNNING' ? 1 : '—')}
          </span>
        </div>

        <div className="p-2.5 rounded bg-slate-900/90 border border-slate-800/80">
          <span className="text-[10px] text-slate-400 uppercase tracking-wide block mb-1">
            {t.activePlanner}
          </span>
          <span className="font-mono text-sm font-semibold text-slate-200">
            {displayValue(agent.planner || 'rule', lang)} ({lang === 'vi' ? displayValue(agent.actual_mode || agent.requested_mode, lang) : (agent.actual_mode || agent.requested_mode)})
          </span>
        </div>

        <div className="p-2.5 rounded bg-slate-900/90 border border-slate-800/80">
          <span className="text-[10px] text-slate-400 uppercase tracking-wide block mb-1">
            {t.observedFacts}
          </span>
          <span className="font-mono text-sm font-semibold text-emerald-400">
            {agent.facts_count} {lang === 'vi' ? 'dữ kiện' : 'facts'}
          </span>
        </div>
      </div>

      {/* Detailed Current Focus */}
      <div className="space-y-2 text-xs flex-1 overflow-y-auto pr-1">
        {Object.entries(agent.scanner_status ?? {}).map(([tool, result]) => (
          <div key={tool} className="rounded border border-slate-700 bg-slate-900 p-2" role="status">
            <p className="text-slate-200">{tool}: {displayValue(String(result.status ?? 'NOT_RUN'), lang)}</p>
            <p className="text-amber-200">{lang === 'vi' ? 'Phạm vi' : 'Coverage'}: {String(result.coverage ?? 'IN_PROGRESS')}</p>
            {result.candidate_count !== undefined && <p>{String(result.candidate_count)} {lang === 'vi' ? 'candidate cần xác minh' : 'unconfirmed candidates'}</p>}
            {Boolean(result.reason) && <p className="break-all text-rose-300">{String(result.reason)}</p>}
          </div>
        ))}
        {/* Target */}
        <div className="p-2.5 rounded bg-slate-900/70 border border-slate-800 flex items-center justify-between">
          <div className="flex items-center space-x-2 text-slate-400">
            <Target className="w-3.5 h-3.5 text-blue-400" />
            <span>{t.targetHost}</span>
          </div>
          <span className="font-mono text-slate-200 font-medium">
            {run.target || 'lab-ecommerce'}
          </span>
        </div>

        {/* Action */}
        <div className="p-2.5 rounded bg-slate-900/70 border border-slate-800 flex items-center justify-between">
          <div className="flex items-center space-x-2 text-slate-400">
            <Zap className="w-3.5 h-3.5 text-amber-400" />
            <span>{t.proposedAction}</span>
          </div>
          <span className="font-mono text-slate-200 font-medium truncate max-w-[160px]" title={agent.current_action || (lang === 'vi' ? 'Chưa có' : 'None')}>
            {agent.current_action || '—'}
          </span>
        </div>

        {/* Safety Gate Outcome */}
        <div className="rounded border border-slate-800 bg-slate-900/70 p-2.5 space-y-1" aria-label={lang === 'vi' ? 'Công cụ và kiểm tra hiện tại' : 'Current tool and check'}>
          <p className="text-slate-400">{lang === 'vi' ? 'Công cụ / chức năng' : 'Tool / capability'}: <span className="break-all text-slate-200">{displayTool(String(execution?.tool ?? ''), lang)}</span></p>
          <p className="text-slate-400">{lang === 'vi' ? 'Loại kiểm tra' : 'Check family'}: <span className="text-slate-200">{displayValue(String(execution?.family ?? 'NOT_RUN'), lang)}</span></p>
          <p className="text-slate-400">{lang === 'vi' ? 'Trạng thái thực thi' : 'Execution status'}: <span className="text-slate-200">{displayValue(String(execution?.status ?? 'NOT_RUN'), lang)}</span></p>
          {Boolean(execution?.resource_ref) && <p className="break-all text-slate-300">{String(execution?.resource_ref)} · {String(execution?.parameter_name ?? '')}</p>}
          <p className="text-slate-400">{lang === 'vi' ? 'Kết quả kiểm tra gần nhất' : 'Latest verification result'}: <span className="text-amber-200">{displayValue(String(verification?.classification ?? 'NOT_RUN'), lang)}</span></p>
          <p className="text-[10px] text-slate-500">{lang === 'vi' ? 'Khám phá hoặc có tín hiệu chưa chứng minh đã khai thác được lỗ hổng.' : 'Discovery or a signal does not establish successful exploitation.'}</p>
        </div>

        <div className="p-2.5 rounded bg-slate-900/70 border border-slate-800 flex items-center justify-between">
          <div className="flex items-center space-x-2 text-slate-400">
            <Shield className="w-3.5 h-3.5 text-emerald-400" />
            <span>{t.safetyGateDecision}</span>
          </div>
          <span
            className={`font-mono text-xs font-bold ${
              isDenied ? 'text-rose-400' : safety.permits_count > 0 ? 'text-emerald-400' : 'text-slate-400'
            }`}
          >
            {isDenied ? t.denied : safety.permits_count > 0 ? t.permitted : t.pendingEvaluation}
          </span>
        </div>

        {/* Last Decision Details */}
        {lastDecision && (
          <div className="p-2 rounded bg-slate-950 border border-slate-800 text-[11px] font-mono space-y-1">
            <span className="text-slate-400 block text-[10px] uppercase font-sans">
              {t.lastDecisionDetail}
            </span>
            {Boolean(lastDecision.reason_code) && (
              <div className="text-amber-300">
                {lang === 'vi' ? "Mã lý do:" : "Code:"} <span className="text-slate-200">{displayValue(String(lastDecision.reason_code), lang)}</span>
              </div>
            )}
            {Boolean(lastDecision.intent) && (
              <div className="text-slate-400">
                {lang === 'vi' ? "Ý định:" : "Intent:"} <span className="text-slate-200">{displayValue(String(lastDecision.intent), lang)}</span>
              </div>
            )}
            {Boolean(lastDecision.reason) && (
              <div className="text-rose-400">
                {lang === 'vi' ? "Lý do:" : "Reason:"} <span className="text-slate-200">{displayValue(String(lastDecision.reason), lang)}</span>
              </div>
            )}
          </div>
        )}

        {/* Budget Tracker */}
        {Object.keys(budget).length > 0 && (
          <div className="p-2 rounded bg-slate-900/50 border border-slate-800/80 flex items-center justify-between text-[11px]">
            <div className="flex items-center space-x-1.5 text-slate-400">
              <Gauge className="w-3.5 h-3.5 text-indigo-400" />
              <span>{t.remainingBudget}</span>
            </div>
            <span className="font-mono text-slate-300">
              {JSON.stringify(budget)}
            </span>
          </div>
        )}
      </div>

      {/* Footer hint */}
      <div className="mt-2 pt-2 border-t border-slate-800/40 text-[10px] text-slate-500 font-mono flex items-center justify-between shrink-0">
        <span className="flex items-center space-x-1">
          <Clock className="w-3 h-3" />
          <span>{t.lastEvent}</span>
        </span>
        <span className="text-slate-400">
          {latestEvent ? `${displayValue(latestEvent.type, lang)} (${latestEvent.event_id})` : t.waitingForRun}
        </span>
      </div>
    </div>
  );
};
