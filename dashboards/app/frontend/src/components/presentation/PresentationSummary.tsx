import React from 'react';
import { displayValue } from '../../i18n/displayValue';
import { ArrowRight, FileText, Radio } from 'lucide-react';
import type { AgentEvent, SseConnectionStatus, SystemStatus } from '../../api/types';
import { useLanguage } from '../../i18n/LanguageContext';

const eventTitles: Record<string, [string, string]> = {
  RUN_STARTED: ['Phiên chạy bắt đầu', 'Run started'],
  RUN_COMPLETED: ['Phiên chạy kết thúc', 'Run completed'],
  RUN_FAILED: ['Phiên chạy gặp lỗi', 'Run failed'],
  RUN_STOPPED: ['Phiên chạy đã dừng', 'Run stopped'],
  RUN_STOP_REQUESTED: ['Đã yêu cầu dừng', 'Stop requested'],
  PLANNER_PROPOSED: ['Đã nhận đề xuất kế hoạch', 'Planner proposed an action'],
  PLANNER_FALLBACK: ['Chuyển sang phương án dự phòng', 'Planner used fallback'],
  SAFETY_PERMITTED: ['Đã ghi nhận quyết định cho phép', 'Permission recorded'],
  SAFETY_DENIED: ['Đã ghi nhận quyết định từ chối', 'Refusal recorded'],
  ACTION_COMPLETED: ['Hành động đã kết thúc', 'Action completed'],
  ACTION_FAILED: ['Hành động gặp lỗi', 'Action failed'],
  OBSERVATION_RECEIVED: ['Đã nhận quan sát mới', 'Observation received'],
  STATE_UPDATED: ['Đã cập nhật trạng thái', 'State updated'],
  EVIDENCE_RECORDED: ['Đã ghi bằng chứng', 'Evidence recorded'],
  EVIDENCE_VERIFIED: ['Đã xác minh bằng chứng', 'Evidence verified'],
  KILL_SWITCH_ACTIVATED: ['Đã bật dừng khẩn cấp', 'Kill switch activated'],
  EMERGENCY_STOP_ACTIVATED: ['Đã bật dừng khẩn cấp', 'Emergency stop activated'],
  STOP_CONDITION_REACHED: ['Đã đạt điều kiện dừng', 'Stop condition reached'],
};

export const presentationEventTitle = (type: string, lang: string): string =>
  eventTitles[type]?.[lang === 'vi' ? 0 : 1] || type;

interface TimelineProps {
  events: AgentEvent[];
  runId: string | null;
  connectionStatus: SseConnectionStatus;
  onReconnect: () => void;
}

export const PresentationTimeline: React.FC<TimelineProps> = ({ events, runId, connectionStatus, onReconnect }) => {
  const { lang } = useLanguage();
  const vi = lang === 'vi';
  const milestones = runId ? events.filter(e => e.run_id === runId && Object.prototype.hasOwnProperty.call(eventTitles, e.type)) : [];
  const recent = milestones.slice(-6);
  return (
    <section className="cc-timeline-section" aria-label={vi ? 'Diễn biến của phiên' : 'Run timeline'}>
      <div className="cc-section-heading">
        <h3>{vi ? 'Diễn biến của phiên' : 'Run timeline'}</h3>
        <span className="cc-caption"><Radio size={14} aria-hidden="true" /> {connectionStatus === 'CONNECTED' ? (vi ? 'Đang nhận sự kiện' : 'Receiving events') : displayValue(connectionStatus, lang)}</span>
      </div>
      {connectionStatus !== 'CONNECTED' && <button type="button" className="cc-button" onClick={onReconnect}>{vi ? 'Kết nối lại sự kiện' : 'Reconnect events'}</button>}
      {recent.length === 0 ? (
        <div className="cc-empty-timeline"><FileText size={24} aria-hidden="true" /><p>{vi ? 'Chưa nhận được sự kiện của phiên này.' : 'No events received for this run yet.'}</p><p className="cc-caption">{vi ? 'Lịch sử phiên lưu diễn biến của những lần chạy trước.' : 'Saved run history contains previous timelines.'}</p></div>
      ) : (
        <ol className="cc-timeline">
          {recent.map((event) => {
            const date = new Date(event.timestamp_utc);
            const time = Number.isNaN(date.getTime()) ? '—' : date.toISOString().slice(11, 19);
            const hasWarning = /DENIED|FAILED|FALLBACK|KILL_SWITCH|EMERGENCY/.test(event.type);
            return <li key={event.event_id} className={hasWarning ? 'cc-timeline-warning' : ''}>
              <span className="cc-timeline-dot" aria-hidden="true" />
              <details>
                <summary><span>{presentationEventTitle(event.type, lang)}</span><time dateTime={Number.isNaN(date.getTime()) ? undefined : event.timestamp_utc}>{time} UTC</time></summary>
                <div className="cc-event-detail"><span className="cc-code">{event.type}</span><p className="cc-caption">{event.event_id}</p><pre>{JSON.stringify(event.payload, null, 2)}</pre></div>
              </details>
            </li>;
          })}
        </ol>
      )}
      {milestones.length > 6 && <p className="cc-caption">{vi ? 'Hiển thị 6 mốc mới nhất. Mở chi tiết kỹ thuật để xem toàn bộ sự kiện đã nhận.' : 'Showing the latest 6 milestones. Open technical details for all received events.'}</p>}
    </section>
  );
};

export const PresentationResults: React.FC<{ system: SystemStatus; onInspect: () => void }> = ({ system, onInspect }) => {
  const { lang } = useLanguage();
  const vi = lang === 'vi';
  const hasRun = !!system.run.run_id && system.run.state !== 'IDLE';
  const count = (value: unknown) => hasRun && typeof value === 'number' && Number.isSafeInteger(value) && value >= 0 ? String(value) : '—';
  return (
    <section className="cc-results" aria-label={vi ? 'Số liệu đã ghi nhận' : 'Recorded results'}>
      <h3>{vi ? 'Số liệu đã ghi nhận' : 'Recorded results'}</h3>
      <dl>
        <div><dd>{count(system.agent.facts_count)}</dd><dt>{vi ? 'Dữ kiện trong trạng thái' : 'Facts in state'}</dt></div>
        <div><dd>{count(system.evidence.count)}</dd><dt>{vi ? 'Bản ghi bằng chứng' : 'Evidence records'}</dt><p className="cc-caption">{vi ? 'Đã xác minh' : 'Verified'}: {count(system.evidence.verified_count)}</p></div>
        <div><dd>{count(system.run.decisions_count)}</dd><dt>{vi ? 'Quyết định của phiên' : 'Run decisions'}</dt></div>
      </dl>
      <p className="cc-caption">{vi ? 'Các số đếm này không phải số lỗ hổng đã xác nhận.' : 'These counts do not represent confirmed vulnerabilities.'}</p>
      <button type="button" className="cc-button" onClick={onInspect} disabled={!hasRun}>{vi ? 'Xem bằng chứng' : 'View evidence'} <ArrowRight size={16} aria-hidden="true" /></button>
    </section>
  );
};
