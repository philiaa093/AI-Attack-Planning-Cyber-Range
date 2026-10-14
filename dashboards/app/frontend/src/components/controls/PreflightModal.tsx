import React from 'react';
import { X, CheckCircle2, XCircle, AlertTriangle, RefreshCw } from 'lucide-react';
import type { PreflightResponse } from '../../api/types';
import { StatusBadge } from '../StatusBadge';
import { useLanguage } from '../../i18n/LanguageContext';
import { displayValue } from '../../i18n/displayValue';

interface PreflightModalProps {
  isOpen: boolean;
  onClose: () => void;
  result: PreflightResponse | null;
  isLoading: boolean;
  onRerun: () => void;
}

export const PreflightModal: React.FC<PreflightModalProps> = ({
  isOpen,
  onClose,
  result,
  isLoading,
  onRerun,
}) => {
  const { lang, t } = useLanguage();
  if (!isOpen) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-xs p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="preflight-title"
    >
      <div className="bg-[#111724] border border-slate-700/80 rounded-xl w-full max-w-lg shadow-2xl overflow-hidden animate-in fade-in duration-150">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-slate-800 bg-slate-900/60">
          <div className="flex items-center space-x-2">
            <AlertTriangle className="w-5 h-5 text-amber-400" />
            <h2 id="preflight-title" className="text-sm font-semibold tracking-wide text-slate-200">
              {t.preflightTitle}
            </h2>
          </div>
          <button
            onClick={onClose}
            aria-label={lang === 'vi' ? "Đóng hộp thoại kiểm tra trước khi chạy" : "Close Preflight modal"}
            className="p-1 rounded text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content */}
        <div className="p-5 space-y-4 max-h-[70vh] overflow-y-auto">
          {isLoading ? (
            <div className="py-8 flex flex-col items-center justify-center space-y-3 text-slate-400 font-mono text-xs">
              <RefreshCw className="w-6 h-6 animate-spin text-blue-400" />
              <span>{t.executingChecks}</span>
            </div>
          ) : result ? (
            <>
              {/* Overall Outcome Banner */}
              <div
                className={`p-3 rounded-lg border flex items-center justify-between ${
                  result.passed
                    ? 'bg-emerald-950/40 border-emerald-800/80 text-emerald-300'
                    : 'bg-rose-950/40 border-rose-800/80 text-rose-300'
                }`}
              >
                <div>
                  <span className="text-xs uppercase tracking-wider font-semibold block font-mono">
                    {displayValue(result.outcome, lang)}
                  </span>
                  <span className="text-[11px] opacity-80">
                    {result.passed ? t.preflightPassedDesc : t.preflightBlockedDesc}
                  </span>
                </div>
                <StatusBadge
                  status={result.passed ? 'PASS' : 'BLOCKED'}
                  variant={result.passed ? 'pass' : 'failed'}
                />
              </div>

              {/* Blockers list if any */}
              {result.blockers.length > 0 && (
                <div className="p-3 rounded bg-rose-950/30 border border-rose-900/50 space-y-1.5 text-xs">
                  <span className="font-semibold text-rose-300 uppercase tracking-wide text-[10px] block">
                    {t.identifiedBlockers} ({result.blockers.length}):
                  </span>
                  <ul className="list-disc list-inside space-y-0.5 text-rose-300/90 font-mono text-[11px]">
                    {result.blockers.map((b) => (
                      <li key={b}>{displayValue(b, lang)}</li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Detailed check items */}
              <div className="space-y-2">
                <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider block">
                  {t.executedChecks}
                </span>
                <div className="space-y-2">
                  {result.checks.map((chk) => (
                    <div
                      key={chk.name}
                      className="p-2.5 rounded bg-slate-900 border border-slate-800 flex items-start justify-between text-xs"
                    >
                      <div className="flex items-start space-x-2 truncate">
                        {chk.passed ? (
                          <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
                        ) : (
                          <XCircle className="w-4 h-4 text-rose-400 shrink-0 mt-0.5" />
                        )}
                        <div>
                          <span className="font-mono font-medium text-slate-200 block">
                            {displayValue(chk.name, lang)}
                          </span>
                          <span className="text-slate-400 text-[11px] font-mono break-all">
                            {chk.detail ? displayValue(chk.detail, lang) : (lang === 'vi' ? (chk.passed ? 'Đạt' : 'Không đạt') : (chk.passed ? 'OK' : 'Failed'))}
                          </span>
                        </div>
                      </div>
                      <span
                        className={`text-[10px] font-mono font-semibold px-2 py-0.5 rounded border shrink-0 ${
                          chk.passed
                            ? 'bg-emerald-950 text-emerald-300 border-emerald-800/60'
                            : 'bg-rose-950 text-rose-300 border-rose-800/60'
                        }`}
                      >
                        {lang === 'vi' ? (chk.passed ? 'ĐẠT' : 'KHÔNG ĐẠT') : (chk.passed ? 'PASSED' : 'FAILED')}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            </>
          ) : (
            <div className="text-center py-6 text-slate-400 text-xs">
              {t.noPreflightResult}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="p-4 border-t border-slate-800 bg-slate-900/60 flex items-center justify-between">
          <button
            onClick={onRerun}
            disabled={isLoading}
            aria-label={lang === 'vi' ? "Kiểm tra lại điều kiện trước khi chạy" : "Re-run Preflight"}
            className="px-3 py-1.5 rounded text-xs font-medium bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 disabled:opacity-50 flex items-center space-x-1.5"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? 'animate-spin' : ''}`} />
            <span>{t.rerunPreflight}</span>
          </button>
          <button
            onClick={onClose}
            aria-label={lang === 'vi' ? "Đóng" : "Close"}
            className="px-4 py-1.5 rounded text-xs font-medium bg-blue-600 hover:bg-blue-500 text-white"
          >
            {t.close}
          </button>
        </div>
      </div>
    </div>
  );
};
