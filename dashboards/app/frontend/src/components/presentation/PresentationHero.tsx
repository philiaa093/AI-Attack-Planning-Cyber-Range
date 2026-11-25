import React from 'react';
import { ArrowRight, ShieldCheck, ShieldAlert, Lock } from 'lucide-react';
import type { AgentEvent, SystemStatus } from '../../api/types';
import { useLanguage } from '../../i18n/LanguageContext';
import { displayValue } from '../../i18n/displayValue';
import { presentationEventTitle } from './PresentationSummary';

interface PresentationHeroProps {
  system: SystemStatus | null;
  latestEvent: AgentEvent | null;
  onViewHistory?: () => void;
}

export const PresentationHero: React.FC<PresentationHeroProps> = ({ system, latestEvent, onViewHistory }) => {
  const { lang } = useLanguage();
  const vi = lang === 'vi';
  const run = system?.run;
  const hasRun = !!run?.run_id && run.state !== 'IDLE';
  const eventMatchesRun = !!run?.run_id && latestEvent?.run_id === run.run_id;
  const eventPayload = eventMatchesRun ? latestEvent?.payload || {} : {};
  const text = (value: unknown): string | null => typeof value === 'string' && value.length > 0 ? value : null;
  const actionId = text(eventPayload.action_id) || text(eventPayload.action);
  // A cumulative counter or another run's event cannot establish this decision.
  const isDenied = eventMatchesRun && !!actionId && latestEvent?.type === 'SAFETY_DENIED';
  const isPermitted = eventMatchesRun && !!actionId && latestEvent?.type === 'SAFETY_PERMITTED';
  const decision = isDenied ? 'DENIED' : isPermitted ? 'PERMITTED' : 'UNKNOWN';
  const lifecycle: Record<string, [string, string]> = {
    IDLE: ['Chưa có phiên chạy đang diễn ra', 'No run in progress'],
    STARTING: ['Phiên chạy đang khởi động', 'The run is starting'],
    PREFLIGHT: ['Đang kiểm tra điều kiện bắt đầu', 'Checking run prerequisites'],
    WAITING_FOR_APPROVAL: ['Đề xuất đang chờ bạn duyệt', 'A proposal awaits your review'],
    PAUSING: ['Đang tạm dừng phiên chạy', 'Pausing the run'],
    PAUSED: ['Phiên chạy đã tạm dừng', 'The run is paused'],
    RESUMING: ['Đang tiếp tục phiên chạy', 'Resuming the run'],
    STOPPING: ['Đang dừng phiên chạy', 'Stopping the run'],
    COMPLETED: ['Phiên chạy đã kết thúc', 'The run has completed'],
    FAILED: ['Phiên chạy gặp lỗi', 'The run encountered an error'],
    BLOCKED: ['Phiên chạy đang bị chặn', 'The run is blocked'],
  };
  const title = !hasRun ? lifecycle.IDLE[vi ? 0 : 1]
    : lifecycle[run!.state]?.[vi ? 0 : 1]
      || (eventMatchesRun && latestEvent ? presentationEventTitle(latestEvent.type, lang)
        : vi ? 'Đang theo dõi phiên chạy' : 'Following the current run');
  const description = !hasRun
    ? vi ? 'Mở một phiên đã lưu để xem lại diễn biến, quyết định và bằng chứng.' : 'Open a saved run to review its timeline, decisions and evidence.'
    : (run?.error || run?.stop_reason ? displayValue(run.error || run.stop_reason, lang) : null) || (vi
      ? 'Theo dõi diễn biến, quyết định an toàn và bằng chứng đã ghi nhận của phiên này.'
      : 'Follow the recorded timeline, safety decisions and evidence for this run.');
  // A terminal lifecycle event alone does not establish that the objective was met.
  const inconclusiveStopReasons = new Set([
    'no_approved_action_can_make_progress', 'unresolved_candidate_surface',
    'unresolved_inconclusive_surface', 'inconclusive_terminal_stop',
    'MAX_DECISIONS_REACHED', 'BUDGET_EXHAUSTED', 'NO_PROGRESS_LOOP',
  ]);
  const objectiveUnconfirmed = hasRun && run?.state === 'COMPLETED'
    && typeof run.stop_reason === 'string' && inconclusiveStopReasons.has(run.stop_reason);
  const DecisionIcon = isDenied ? ShieldAlert : isPermitted ? ShieldCheck : Lock;

  return (
    <section className="cc-hero" aria-label={vi ? 'Hoạt động hiện tại' : 'Current activity'}>
      <div className="cc-hero-main">
        <div className="cc-eyebrow">{vi ? 'Hoạt động hiện tại' : 'Current activity'}</div>
        <h2 aria-live="polite">{title}</h2>
        <p className="cc-description">{description}</p>
        {objectiveUnconfirmed && <p className="cc-description">{vi
          ? 'Phiên đã dừng; chưa có bằng chứng xác nhận mục tiêu đã hoàn thành.'
          : 'The run has stopped; objective completion has not been established.'}</p>}
        <div className="cc-meta">
          <span className="cc-chip">{displayValue(run?.state || 'IDLE', lang)}</span>
          <span>{vi ? 'Mục tiêu' : 'Target'}: {run?.target || '—'}</span>
        </div>
        {!hasRun && onViewHistory && (
          <button type="button" className="cc-button cc-button-primary" onClick={onViewHistory}>
            {vi ? 'Xem lịch sử phiên' : 'View run history'} <ArrowRight size={16} aria-hidden="true" />
          </button>
        )}
      </div>
      <dl className="cc-run-context">
        <div><dt>{vi ? 'Bộ lập kế hoạch thực tế' : 'Actual planner'}</dt><dd>{displayValue(system?.agent.actual_mode, lang)}</dd></div>
        <div><dt>{vi ? 'Bộ lập kế hoạch yêu cầu' : 'Requested planner'}</dt><dd>{displayValue(system?.agent.requested_mode, lang)}</dd></div>
        <div><dt>{vi ? 'Giai đoạn ghi nhận' : 'Recorded phase'}</dt><dd>{hasRun ? displayValue(system?.agent.current_phase, lang) : '—'}</dd></div>
        {system?.agent.fallback_reason && <div className="cc-fallback"><dt>{vi ? 'Lý do dùng dự phòng' : 'Fallback'}</dt><dd>{displayValue(system.agent.fallback_reason, lang)}</dd></div>}
      </dl>
      <div className={`cc-decision ${isDenied ? 'cc-decision-denied' : ''}`}>
        <DecisionIcon size={18} aria-hidden="true" />
        <div>
          <span className="cc-decision-label">{vi ? 'Quyết định trong sự kiện mới nhất' : 'Decision in latest event'}: <strong>{displayValue(decision, lang)}</strong></span>
          <p>{isDenied ? (vi ? 'Quyết định từ chối đã ghi nhận' : 'Recorded refusal for this action')
            : isPermitted ? (vi ? 'Quyết định cho phép đã ghi nhận' : 'Recorded permission for this action')
              : vi ? 'Sự kiện mới nhất không cho biết quyết định an toàn.' : 'The latest event does not establish a safety decision.'}</p>
          {actionId && <p className="cc-code">{actionId}</p>}
          {isDenied && <p>{displayValue(text(eventPayload.reason) || text(eventPayload.rule) || 'UNKNOWN', lang)}</p>}
          {isPermitted && <p><span>{vi ? 'Số lần phát lệnh ghi nhận của lượt chạy:' : 'Recorded run dispatches:'}</span>{' '}<span>{run?.network_dispatches ?? '—'}</span></p>}
        </div>
      </div>
    </section>
  );
};
