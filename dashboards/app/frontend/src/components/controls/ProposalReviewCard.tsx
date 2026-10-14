import React, { useState } from 'react';
import {
  AlertCircle,
  CheckCircle2,
  XCircle,
  Shield,
  Cpu,
  Clock,
  RefreshCw,
} from 'lucide-react';
import type { PendingProposal } from '../../api/types';
import { useLanguage } from '../../i18n/LanguageContext';
import { displayValue } from '../../i18n/displayValue';

interface ProposalReviewCardProps {
  proposal: PendingProposal;
  runId: string;
  onApprove: (runId: string, proposalId: string) => Promise<void>;
  onReject: (runId: string, proposalId: string, reason?: string) => Promise<void>;
}

export const ProposalReviewCard: React.FC<ProposalReviewCardProps> = ({
  proposal,
  runId,
  onApprove,
  onReject,
}) => {
  const { lang, t } = useLanguage();
  const [isApproving, setIsApproving] = useState(false);
  const [isRejecting, setIsRejecting] = useState(false);
  const [rejectReason, setRejectReason] = useState('Operator rejected proposal');
  const [showRejectInput, setShowRejectInput] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const handleApprove = async () => {
    setIsApproving(true);
    setActionError(null);
    try {
      await onApprove(runId, proposal.plan_id);
    } catch (err) {
      setActionError(err instanceof Error ? err.message : String(err));
      setIsApproving(false);
    }
  };

  const handleReject = async () => {
    setIsRejecting(true);
    setActionError(null);
    try {
      await onReject(runId, proposal.plan_id, rejectReason);
    } catch (err) {
      setActionError(err instanceof Error ? err.message : String(err));
      setIsRejecting(false);
    }
  };

  const isSafetyPermitted = proposal.safety_decision === 'PERMIT';

  return (
    <div className="bg-[#121927] border-2 border-amber-500/80 rounded-xl p-5 shadow-xl shadow-amber-950/20 space-y-4 animate-in fade-in duration-200">
      {/* Banner */}
      <div className="flex items-center justify-between pb-3 border-b border-slate-800">
        <div className="flex items-center space-x-2.5">
          <Clock className="w-5 h-5 text-amber-400 animate-pulse" />
          <div>
            <h3 className="text-sm font-bold text-amber-200 uppercase tracking-wide">
              {t.operatorApprovalRequired}
            </h3>
            <p className="text-[11px] text-slate-400">
              {t.executionPausedSafeBoundary}
            </p>
          </div>
        </div>
        <span className="font-mono text-xs px-2.5 py-1 rounded bg-amber-950/70 text-amber-300 border border-amber-800/60 font-semibold">
          {lang === 'vi' ? 'Chế độ: ' : ''}{displayValue(proposal.control_mode || 'MANUAL', lang)}{lang === 'en' ? ' MODE' : ''}
        </span>
      </div>

      {actionError && (
        <div className="p-3 rounded bg-rose-950/40 border border-rose-900/60 text-rose-300 text-xs flex items-start space-x-2">
          <AlertCircle className="w-4 h-4 text-rose-400 shrink-0 mt-0.5" />
          <span>{displayValue(actionError, lang)}</span>
        </div>
      )}

      {/* Proposal Summary Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
        {/* Left Column: Action Details */}
        <div className="bg-slate-900/80 border border-slate-800 rounded-lg p-3.5 space-y-2.5">
          <div className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider flex items-center space-x-1.5">
            <Cpu className="w-3.5 h-3.5 text-blue-400" />
            <span>{t.proposedAction}</span>
          </div>

          <div className="space-y-1.5">
            <div className="flex justify-between items-center">
              <span className="text-slate-400">{lang === 'vi' ? "Mã hành động:" : "Action ID:"}</span>
              <span className="font-mono text-blue-300 font-semibold">{proposal.action_id}</span>
            </div>
            {proposal.action_name && (
              <div className="flex justify-between items-center">
                <span className="text-slate-400">{lang === 'vi' ? "Tên hành động:" : "Action Name:"}</span>
                <span className="font-mono text-slate-200">{displayValue(proposal.action_name, lang)}</span>
              </div>
            )}
            <div className="flex justify-between items-center">
              <span className="text-slate-400">{lang === 'vi' ? "Mã mục tiêu:" : "Target ID:"}</span>
              <span className="font-mono text-slate-200">{proposal.target_id}</span>
            </div>
            {proposal.resource_ref && (
              <div className="flex justify-between items-center">
                <span className="text-slate-400">{lang === 'vi' ? "Tham chiếu tài nguyên:" : "Resource Ref:"}</span>
                <span className="font-mono text-slate-300">{proposal.resource_ref}</span>
              </div>
            )}
            {proposal.confidence !== undefined && (
              <div className="flex justify-between items-center">
                <span className="text-slate-400">{lang === 'vi' ? "Độ tin cậy:" : "Confidence:"}</span>
                <span className="font-mono text-slate-200 font-semibold">
                  {(proposal.confidence * 100).toFixed(0)}%
                </span>
              </div>
            )}
          </div>
        </div>

        {/* Right Column: Safety Evaluation & Provenance */}
        <div className="bg-slate-900/80 border border-slate-800 rounded-lg p-3.5 space-y-2.5">
          <div className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider flex items-center space-x-1.5">
            <Shield className="w-3.5 h-3.5 text-emerald-400" />
            <span>{t.safetyEvaluationProvenance}</span>
          </div>

          <div className="space-y-1.5">
            <div className="flex justify-between items-center">
              <span className="text-slate-400">{lang === 'vi' ? "Quyết định an toàn:" : "Safety Decision:"}</span>
              <span
                className={`font-mono text-xs font-semibold px-2 py-0.5 rounded border ${
                  isSafetyPermitted
                    ? 'bg-emerald-950/70 text-emerald-300 border-emerald-800/60'
                    : 'bg-rose-950/70 text-rose-300 border-rose-800/60'
                }`}
              >
                {displayValue(proposal.safety_decision || 'EVALUATING', lang)}
              </span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-slate-400">{lang === 'vi' ? "Nguồn quyết định:" : "Decision Origin:"}</span>
              <span className="font-mono text-slate-200">{displayValue(proposal.decision_origin || 'RULE', lang)}</span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-slate-400">{lang === 'vi' ? "Bộ lập kế hoạch (yêu cầu / thực tế):" : "Planner (Req / Act):"}</span>
              <span className="font-mono text-slate-300">
                {displayValue(proposal.requested_mode || 'RULE', lang)} / {displayValue(proposal.actual_mode || 'RULE', lang)}
              </span>
            </div>
            {proposal.provider && (
              <div className="flex justify-between items-center">
                <span className="text-slate-400">{lang === 'vi' ? "Nhà cung cấp / Mô hình:" : "Provider / Model:"}</span>
                <span className="font-mono text-slate-300 text-[11px]">
                  {proposal.provider}:{proposal.model || (lang === 'vi' ? 'mặc định' : 'default')}
                </span>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Rationale / Observed Basis */}
      {proposal.reason_code && (
        <div className="bg-slate-900/60 border border-slate-800/80 rounded-lg p-3 text-xs">
          <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider block mb-1">
            {t.decisionRationale}
          </span>
          <p className="font-mono text-slate-300 leading-relaxed text-[11px]">
            {displayValue(proposal.reason_code, lang)}
          </p>
        </div>
      )}

      {/* Reject Reason input if toggled */}
      {showRejectInput && (
        <div className="space-y-1.5">
          <label className="text-[11px] font-semibold text-rose-300">{t.rejectionReason}</label>
          <input
            type="text"
            value={rejectReason}
            onChange={(e) => setRejectReason(e.target.value)}
            className="w-full bg-slate-900 border border-rose-900/60 rounded px-3 py-1.5 text-slate-200 font-mono text-xs focus:outline-hidden focus:border-rose-500"
          />
        </div>
      )}

      {/* Action Buttons */}
      <div className="flex items-center justify-between pt-2 border-t border-slate-800/80">
        <span className="text-[11px] text-slate-400 font-mono">
          {lang === 'vi' ? "Mã đề xuất:" : "Proposal ID:"} <span className="text-slate-300">{proposal.plan_id}</span>
        </span>

        <div className="flex items-center space-x-2.5">
          {!showRejectInput ? (
            <button
              onClick={() => setShowRejectInput(true)}
              disabled={isApproving || isRejecting}
              aria-label={lang === 'vi' ? "Từ chối đề xuất" : "Reject Proposal"}
              className="px-3.5 py-1.5 rounded text-xs font-medium bg-rose-950/60 hover:bg-rose-900 text-rose-200 border border-rose-800/60 transition-colors disabled:opacity-40 flex items-center space-x-1.5"
            >
              <XCircle className="w-3.5 h-3.5 text-rose-400" />
              <span>{t.rejectProposal}</span>
            </button>
          ) : (
            <div className="flex items-center space-x-1.5">
              <button
                onClick={() => setShowRejectInput(false)}
                className="px-2.5 py-1.5 rounded text-xs bg-slate-800 text-slate-300"
              >
                {t.cancel}
              </button>
              <button
                onClick={handleReject}
                disabled={isRejecting}
                aria-label={lang === 'vi' ? "Xác nhận từ chối" : "Confirm Reject"}
                className="px-3.5 py-1.5 rounded text-xs font-semibold bg-rose-700 hover:bg-rose-600 text-white disabled:opacity-40 flex items-center space-x-1.5"
              >
                {isRejecting ? (
                  <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                ) : (
                  <XCircle className="w-3.5 h-3.5 text-white" />
                )}
                <span>{t.confirmReject}</span>
              </button>
            </div>
          )}

          <button
            onClick={handleApprove}
            disabled={isApproving || isRejecting}
            aria-label={lang === 'vi' ? "Phê duyệt và thực thi" : "Approve & Execute"}
            className="px-4 py-1.5 rounded text-xs font-semibold bg-emerald-600 hover:bg-emerald-500 text-white disabled:opacity-40 shadow-sm flex items-center space-x-1.5"
          >
            {isApproving ? (
              <RefreshCw className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <CheckCircle2 className="w-3.5 h-3.5 text-white" />
            )}
            <span>{t.approveAndExecute}</span>
          </button>
        </div>
      </div>
    </div>
  );
};
