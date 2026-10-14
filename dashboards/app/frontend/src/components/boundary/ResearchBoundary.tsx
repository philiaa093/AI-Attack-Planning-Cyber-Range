import React from 'react';
import { ShieldAlert, Globe, Server, Lock, CheckCircle2, FileCheck } from 'lucide-react';
import { useLanguage } from '../../i18n/LanguageContext';

export const ResearchBoundary: React.FC = () => {
  const { t } = useLanguage();

  const boundaries = [
    {
      label: t('envLabel'),
      value: t('isolatedLab'),
      icon: Server,
      color: 'text-emerald-400',
    },
    {
      label: t('publicInternet'),
      value: t('notAllowed'),
      icon: Globe,
      color: 'text-rose-400',
    },
    {
      label: t('externalTargets'),
      value: t('notAllowed'),
      icon: ShieldAlert,
      color: 'text-rose-400',
    },
    {
      label: t('execution'),
      value: t('typedBounded'),
      icon: Lock,
      color: 'text-cyan-400',
    },
    {
      label: t('safetyAuthority'),
      value: t('centralizedGate'),
      icon: CheckCircle2,
      color: 'text-emerald-400',
    },
    {
      label: t('evidence'),
      value: t('runtimeSourced'),
      icon: FileCheck,
      color: 'text-indigo-400',
    },
  ];

  return (
    <div className="bg-[#111724] border border-slate-800/80 rounded-lg p-4 shadow-sm">
      <div className="flex items-center justify-between pb-3 border-b border-slate-800/60 mb-3">
        <div className="flex items-center space-x-2">
          <ShieldAlert className="w-4 h-4 text-amber-400" />
          <span className="text-xs font-semibold tracking-wider uppercase text-slate-400">
            {t('researchBoundaryTitle')}
          </span>
        </div>
        <span className="text-[11px] font-mono text-emerald-400/90 font-medium bg-emerald-950/40 border border-emerald-900/40 px-2 py-0.5 rounded">
          {t('labIsolationEnforced')}
        </span>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
        {boundaries.map((b) => {
          const Icon = b.icon;
          return (
            <div
              key={b.label}
              className="bg-slate-900/80 border border-slate-800/80 rounded p-2.5 flex flex-col justify-between"
            >
              <div className="flex items-center space-x-1.5 text-slate-400 text-[10px] uppercase tracking-wider mb-1">
                <Icon className={`w-3 h-3 ${b.color}`} />
                <span>{b.label}</span>
              </div>
              <span className={`font-mono text-xs font-semibold ${b.color}`}>
                {b.value}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
};
