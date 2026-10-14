import React from 'react';
import { Server, ExternalLink, AlertTriangle } from 'lucide-react';
import type { RangeStatus } from '../../api/types';
import { StatusBadge } from '../StatusBadge';
import { useLanguage } from '../../i18n/LanguageContext';
import { displayValue } from '../../i18n/displayValue';

interface RangeCardProps {
  range: RangeStatus;
}

export const RangeCard: React.FC<RangeCardProps> = ({ range }) => {
  const { lang, t } = useLanguage();
  const isDockerUnavailable = range.message?.includes('DOCKER_UNAVAILABLE') || range.status === 'UNAVAILABLE';
  const runningServicesCount = Object.values(range.services || {}).filter(
    (s: unknown) => (s as { State?: { Running?: boolean } })?.State?.Running
  ).length;

  return (
    <div className="bg-[#111724] border border-slate-800/80 rounded-lg p-4 flex flex-col justify-between shadow-sm hover:border-slate-700/60 transition-colors">
      <div className="flex items-center justify-between pb-3 border-b border-slate-800/60">
        <div className="flex items-center space-x-2 text-slate-300">
          <Server className="w-4 h-4 text-blue-400" />
          <span className="text-xs font-semibold tracking-wider uppercase text-slate-400">{t('cyberRange')}</span>
        </div>
        <StatusBadge status={range.status} />
      </div>

      <div className="mt-3 space-y-2.5 text-xs">
        <div className="flex justify-between items-center">
          <span className="text-slate-400">{t('target')}</span>
          <span className="font-mono text-slate-200 font-medium">{range.target_id || 'lab-ecommerce'}</span>
        </div>

        <div className="flex justify-between items-center">
          <span className="text-slate-400">{t('gateway')}</span>
          <a
            href={range.origin}
            target="_blank"
            rel="noreferrer"
            className="font-mono text-blue-400 hover:text-blue-300 flex items-center space-x-1"
          >
            <span>{range.origin || 'http://127.0.0.1:18088'}</span>
            <ExternalLink className="w-3 h-3" />
          </a>
        </div>

        <div className="flex justify-between items-center">
          <span className="text-slate-400">{t('activeServices')}</span>
          <span className="font-mono text-slate-300">
            {runningServicesCount > 0 ? `${runningServicesCount} ${lang === 'vi' ? 'đang chạy' : 'active'}` : (lang === 'vi' ? '0 dịch vụ đang chạy' : '0 running')}
          </span>
        </div>

        {isDockerUnavailable && (
          <div className="mt-2 p-2 rounded bg-amber-950/40 border border-amber-900/60 text-amber-300/90 flex items-start space-x-2 text-[11px]">
            <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
            <div>
              <p className="font-medium text-amber-200">{t('dockerUnavailable')}</p>
              <p className="text-amber-300/70 text-[10px]">{t('dockerUnavailableDesc')}</p>
            </div>
          </div>
        )}

        {range.message && !isDockerUnavailable && (
          <div className="pt-1 text-[11px] text-slate-400 font-mono truncate" title={displayValue(range.message, lang)}>
            {displayValue(range.message, lang)}
          </div>
        )}
      </div>

      <div className="mt-3 pt-2 border-t border-slate-800/40 text-[10px] text-slate-400 flex justify-between">
        <span>{t('checked')}</span>
        <span className="font-mono">{range.checked_at_utc ? new Date(range.checked_at_utc).toLocaleTimeString() : '—'}</span>
      </div>
    </div>
  );
};
