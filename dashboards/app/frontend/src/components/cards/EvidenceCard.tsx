import React from 'react';
import { Database, CheckCircle, Clock } from 'lucide-react';
import type { EvidenceStatus } from '../../api/types';
import { StatusBadge } from '../StatusBadge';
import { useLanguage } from '../../i18n/LanguageContext';

interface EvidenceCardProps {
  evidence: EvidenceStatus;
  onInspect?: () => void;
}

export const EvidenceCard: React.FC<EvidenceCardProps> = ({ evidence, onInspect }) => {
  const { lang, t } = useLanguage();
  const isVerified = evidence.integrity_status === 'VERIFIED';

  return (
    <div className="bg-[#111724] border border-slate-800/80 rounded-lg p-4 flex flex-col justify-between shadow-sm hover:border-slate-700/60 transition-colors">
      <div className="flex items-center justify-between pb-3 border-b border-slate-800/60">
        <div className="flex items-center space-x-2 text-slate-300">
          <Database className="w-4 h-4 text-emerald-400" />
          <span className="text-xs font-semibold tracking-wider uppercase text-slate-400">{t.evidenceVault}</span>
        </div>
        <div className="flex items-center space-x-2">
          {onInspect && (
            <button
              onClick={onInspect}
              aria-label={lang === 'vi' ? "Kiểm tra bằng chứng" : "Inspect evidence"}
              className="text-[10px] font-mono text-blue-400 hover:text-blue-300 bg-blue-500/10 hover:bg-blue-500/20 px-2 py-0.5 rounded border border-blue-500/20 transition-colors"
            >
              {t.inspect}
            </button>
          )}
          <StatusBadge
            status={evidence.integrity_status}
            variant={isVerified ? 'verified' : evidence.integrity_status === 'RECORDING' ? 'running' : 'neutral'}
          />
        </div>
      </div>

      <div className="mt-3 space-y-2.5 text-xs">
        <div className="flex justify-between items-center">
          <span className="text-slate-400">{t.totalArtifacts}</span>
          <span className="font-mono text-slate-200 font-semibold">{evidence.count}</span>
        </div>

        <div className="flex justify-between items-center">
          <span className="text-slate-400">{t.verifiedRecords}</span>
          <span className="font-mono text-emerald-400 font-semibold">{evidence.verified_count}</span>
        </div>

        <div className="flex justify-between items-center">
          <span className="text-slate-400">{t.integrityHash}</span>
          <span className="font-mono text-slate-300 flex items-center space-x-1">
            {isVerified ? (
              <>
                <CheckCircle className="w-3 h-3 text-emerald-400" />
                <span className="text-emerald-400 font-medium">{t.sha256Valid}</span>
              </>
            ) : (
              <>
                <Clock className="w-3 h-3 text-slate-400" />
                <span>{t.unverified}</span>
              </>
            )}
          </span>
        </div>

        <div className="flex flex-col pt-1">
          <span className="text-[10px] text-slate-400 mb-0.5">{t.latestEvidenceId}</span>
          <span
            className="font-mono text-[11px] text-slate-300 bg-slate-900 px-2 py-1 rounded border border-slate-800 truncate"
            title={evidence.last_evidence_id || (lang === 'vi' ? 'Chưa có' : 'None')}
          >
            {evidence.last_evidence_id || '—'}
          </span>
        </div>
      </div>

      <div className="mt-3 pt-2 border-t border-slate-800/40 text-[10px] text-slate-400 flex justify-between">
        <span>{t.storageMode}</span>
        <span className="font-mono text-emerald-400/90 font-medium">{lang === 'vi' ? "JSONL chỉ ghi thêm" : "APPEND-ONLY JSONL"}</span>
      </div>
    </div>
  );
};
