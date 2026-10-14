import React from 'react';
import { ShieldCheck, ShieldAlert } from 'lucide-react';
import type { SafetyStatus, SystemStatus } from '../../api/types';
import { StatusBadge } from '../StatusBadge';
import { useLanguage } from '../../i18n/LanguageContext';
import { displayValue } from '../../i18n/displayValue';

interface SafetyCardProps {
  safety: SafetyStatus;
  system: SystemStatus;
}

export const SafetyCard: React.FC<SafetyCardProps> = ({ safety, system }) => {
  const { lang, t } = useLanguage();
  const isKillSwitchActive = safety.kill_switch_active;
  const isDenyActive = safety.denials_count > 0;
  const lastDecision = system.agent.last_decision;
  const reasonCode = (lastDecision?.reason_code || lastDecision?.reason || '') as string;

  return (
    <div
      className={`bg-[#111724] border rounded-lg p-4 flex flex-col justify-between shadow-sm transition-colors ${
        isKillSwitchActive
          ? 'border-rose-700/80 bg-rose-950/20'
          : isDenyActive
          ? 'border-rose-900/60'
          : 'border-slate-800/80 hover:border-slate-700/60'
      }`}
    >
      <div className="flex items-center justify-between pb-3 border-b border-slate-800/60">
        <div className="flex items-center space-x-2 text-slate-300">
          {isKillSwitchActive || isDenyActive ? (
            <ShieldAlert className="w-4 h-4 text-rose-400" />
          ) : (
            <ShieldCheck className="w-4 h-4 text-emerald-400" />
          )}
          <span className="text-xs font-semibold tracking-wider uppercase text-slate-400">{t('safetyGate')}</span>
        </div>
        <StatusBadge
          status={isKillSwitchActive ? 'BLOCKED' : 'ACTIVE'}
          variant={isKillSwitchActive ? 'blocked' : 'pass'}
        />
      </div>

      <div className="mt-3 space-y-2.5 text-xs">
        <div className="flex justify-between items-center">
          <span className="text-slate-400">{lang === 'vi' ? 'Công tắc dừng' : 'Kill Switch'}</span>
          <span
            className={`font-mono font-medium px-1.5 py-0.5 rounded text-[11px] border ${
              isKillSwitchActive
                ? 'bg-rose-950/70 text-rose-300 border-rose-800/60'
                : 'bg-slate-900 text-slate-300 border-slate-800'
            }`}
          >
            {isKillSwitchActive ? (lang === 'vi' ? 'ĐÃ KÍCH HOẠT' : 'ACTIVATED') : (lang === 'vi' ? 'SẴN SÀNG' : 'ARMED / INACTIVE')}
          </span>
        </div>

        <div className="flex justify-between items-center">
          <span className="text-slate-400">{t('permitsCount')}</span>
          <span className="font-mono text-emerald-400 font-semibold">{safety.permits_count}</span>
        </div>

        <div className="flex justify-between items-center">
          <span className="text-slate-400">{t('denialsCount')}</span>
          <span
            className={`font-mono font-semibold ${
              safety.denials_count > 0 ? 'text-rose-400' : 'text-slate-300'
            }`}
          >
            {safety.denials_count}
          </span>
        </div>

        <div className="flex justify-between items-center">
          <span className="text-slate-400">{t('allowedTargets')}</span>
          <span className="font-mono text-slate-300">
            {safety.target_allowlist.length > 0 ? `${safety.target_allowlist.length} ${lang === 'vi' ? 'mục tiêu' : 'target'}` : (lang === 'vi' ? '1 (cách ly)' : '1 (isolated)')}
          </span>
        </div>

        {safety.denials_count > 0 && (
          <div className="mt-1 p-2 rounded bg-rose-950/40 border border-rose-900/60 text-rose-300/90 text-[11px]">
            <span className="font-semibold text-rose-300">{lang === 'vi' ? 'Lý do từ chối gần nhất: ' : 'Last Denial Reason: '}</span>
            <span className="font-mono text-[10px] break-all">
              {displayValue(reasonCode || 'TARGET_NOT_ALLOWLISTED', lang)}
            </span>
          </div>
        )}
      </div>

      <div className="mt-3 pt-2 border-t border-slate-800/40 text-[10px] text-slate-400 flex justify-between">
        <span>{lang === 'vi' ? 'Cách ly môi trường thử nghiệm' : 'Lab Isolation'}</span>
        <span className="font-mono text-emerald-400/90 font-medium">{lang === 'vi' ? "Áp dụng bắt buộc (chỉ trong môi trường thử nghiệm)" : "ENFORCED (LAB ONLY)"}</span>
      </div>
    </div>
  );
};
