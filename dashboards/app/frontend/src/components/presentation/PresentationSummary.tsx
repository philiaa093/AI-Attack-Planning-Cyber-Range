import React, { useEffect, useState } from 'react';
import { displayValue } from '../../i18n/displayValue';
import { ArrowRight, FileText, Radio } from 'lucide-react';
import type { AgentEvent, SseConnectionStatus, SystemStatus } from '../../api/types';
import { useLanguage } from '../../i18n/LanguageContext';
import type { Language } from '../../i18n/translations';

const eventTitles: Record<string, [string, string]> = {
  RUN_STARTED: ['Phiên chạy bắt đầu', 'Run started'],
  RUN_COMPLETED: ['Phiên chạy kết thúc', 'Run completed'],
  RUN_FAILED: ['Phiên chạy gặp lỗi', 'Run failed'],
  RUN_STOPPED: ['Phiên chạy đã dừng', 'Run stopped'],
  RUN_STOP_REQUESTED: ['Đã yêu cầu dừng', 'Stop requested'],
  PLANNER_PROPOSED: ['Đã nhận đề xuất kế hoạch', 'Planner proposed an action'],
  PLANNER_FALLBACK: ['Chuyển sang phương án dự phòng', 'Planner used fallback'],
  PROPOSAL_WAITING_APPROVAL: ['Đề xuất đang chờ duyệt', 'Proposal awaiting approval'],
  PLANNER_FAILED: ['Lập kế hoạch gặp lỗi', 'Planning failed'],
  ACTION_DISPATCHED: ['Đã phát lệnh hành động', 'Action dispatched'],
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

export const presentationEventTitle = (type: string, lang: Language): string =>
  eventTitles[type]?.[lang === 'vi' ? 0 : 1] || displayValue(type, lang);

interface TimelineProps {
  events: AgentEvent[];
  runId: string | null;
  connectionStatus: SseConnectionStatus;
  onReconnect: () => void;
}

// Explain the event itself, without inferring later steps from a proposal or permission.
const eventExplanation: Record<string, [string, string]> = {
  PLANNER_PROPOSED: ['Đây là đề xuất để xem xét, chưa phải hành động đã thực thi.', 'This is a proposal for review, not an executed action.'],
  PROPOSAL_WAITING_APPROVAL: ['Phiên đang chờ quyết định của người vận hành.', 'The run is waiting for an operator decision.'],
  PLANNER_FALLBACK: ['Kiểm tra chế độ thực tế và lý do dự phòng trong chi tiết.', 'Check the actual mode and fallback reason in the details.'],
  SAFETY_PERMITTED: ['Cổng an toàn đã ghi nhận cho phép đối với hành động này.', 'The safety gate recorded permission for this action.'],
  SAFETY_DENIED: ['Cổng an toàn đã ghi nhận từ chối đối với hành động này.', 'The safety gate recorded a refusal for this action.'],
  ACTION_DISPATCHED: ['Đã ghi nhận sự kiện phát lệnh; xem sự kiện kết quả để biết kết cục.', 'A dispatch was recorded; see the result event for its outcome.'],
  ACTION_COMPLETED: ['Kết quả hành động đã được ghi nhận.', 'The action result was recorded.'],
  ACTION_FAILED: ['Hành động kết thúc với trạng thái lỗi.', 'The action ended with a failure status.'],
  OBSERVATION_RECEIVED: ['Quan sát mới được tiếp nhận vào phiên.', 'A new observation was received for the run.'],
  STATE_UPDATED: ['Trạng thái được cập nhật từ dữ liệu đã ghi nhận.', 'The state was updated from recorded data.'],
  EVIDENCE_RECORDED: ['Bản ghi bằng chứng đã được tạo; xem chi tiết để tra cứu.', 'An evidence record was created; inspect the details to look it up.'],
  EVIDENCE_VERIFIED: ['Đã nhận sự kiện xác minh bằng chứng.', 'An evidence verification event was received.'],
  RUN_FAILED: ['Xem lý do được ghi nhận trong thông tin phiên hoặc chi tiết sự kiện.', 'See the recorded reason in the run information or event details.'],
};

const TimelineEvent: React.FC<{ event: AgentEvent; lang: Language }> = ({ event, lang }) => {
  const [showRaw, setShowRaw] = useState(false);
  const vi = lang === 'vi';
  const date = new Date(event.timestamp_utc);
  const validDate = !Number.isNaN(date.getTime());
  const time = validDate ? date.toISOString().slice(11, 19) : '—';
  const hasWarning = /DENIED|FAILED|FALLBACK|KILL_SWITCH|EMERGENCY/.test(event.type);
  const textFields: Array<[string, string, string]> = [
    ['action_id', 'Hành động', 'Action'],
    ['target_id', 'Mục tiêu', 'Target'],
    ['reason', 'Lý do', 'Reason'],
    ['reason_code', 'Mã lý do', 'Reason code'],
    ['outcome', 'Kết quả ghi nhận', 'Recorded outcome'],
    ['actual_mode', 'Chế độ thực tế', 'Actual mode'],
    ['evidence_id', 'Mã bằng chứng', 'Evidence ID'],
    ['observation_id', 'Mã quan sát', 'Observation ID'],
  ];
  const recordedFields = textFields.filter(([key]) => typeof event.payload?.[key] === 'string' && (event.payload[key] as string).length > 0);
  return <li className={hasWarning ? 'cc-timeline-warning' : ''}>
    <span className="cc-timeline-dot" aria-hidden="true" />
    <div>
      <details>
        <summary><span>{presentationEventTitle(event.type, lang)}</span><time dateTime={validDate ? event.timestamp_utc : undefined}>{time} UTC</time></summary>
        <div className="cc-event-detail">
          {recordedFields.length > 0 && <dl className="ps-event-fields">
            {recordedFields.map(([key, labelVi, labelEn]) => <div key={key}>
              <dt>{vi ? labelVi : labelEn}</dt><dd>{displayValue(event.payload[key] as string, lang)}</dd>
            </div>)}
          </dl>}
          {typeof event.iteration === 'number' && <p className="cc-caption">{vi ? 'Vòng xử lý' : 'Iteration'}: {event.iteration}</p>}
          <p className="cc-caption">{vi ? 'Sự kiện' : 'Event'}: <span className="cc-code">{event.event_id}</span></p>
          <details className="ps-raw-event" onToggle={e => setShowRaw(e.currentTarget.open)}>
            <summary>{vi ? 'Xem dữ liệu sự kiện' : 'View event data'}</summary>
            {showRaw && <><span className="cc-code">{event.type}</span><pre>{JSON.stringify(event.payload, null, 2)}</pre></>}
          </details>
        </div>
      </details>
      {eventExplanation[event.type] && <p className="ps-event-explanation">{eventExplanation[event.type][vi ? 0 : 1]}</p>}
    </div>
  </li>;
};

export const PresentationTimeline: React.FC<TimelineProps> = ({ events, runId, connectionStatus, onReconnect }) => {
  const { lang } = useLanguage();
  const vi = lang === 'vi';
  const [showAll, setShowAll] = useState(false);
  useEffect(() => setShowAll(false), [runId]);
  // These are events received in this browser session, not necessarily the complete run history.
  const milestones = runId ? events.filter(e => e.run_id === runId && (
    Object.prototype.hasOwnProperty.call(eventTitles, e.type) || presentationEventTitle(e.type, lang) !== e.type
  )) : [];
  const displayed = showAll ? milestones : milestones.slice(-6);
  return (
    <section className="cc-timeline-section" aria-label={vi ? 'Diễn biến của phiên' : 'Run timeline'}>
      <div className="cc-section-heading">
        <h3>{vi ? 'Diễn biến của phiên' : 'Run timeline'}</h3>
        <span className="cc-caption"><Radio size={14} aria-hidden="true" /> {connectionStatus === 'CONNECTED' ? (vi ? 'Đang nhận sự kiện' : 'Receiving events') : displayValue(connectionStatus, lang)}</span>
      </div>
      <p className="ps-timeline-intro">{vi ? 'Các mốc trình duyệt đã nhận cho phiên này; lịch sử phiên có thể chứa thêm thông tin.' : 'Milestones received in this browser for this run; saved history may contain more.'}</p>
      {connectionStatus !== 'CONNECTED' && <button type="button" className="cc-button" onClick={onReconnect}>{vi ? 'Kết nối lại sự kiện' : 'Reconnect events'}</button>}
      {displayed.length === 0 ? (
        <div className="cc-empty-timeline"><FileText size={24} aria-hidden="true" /><p>{vi ? 'Chưa nhận được sự kiện của phiên này.' : 'No events received for this run yet.'}</p><p className="cc-caption">{vi ? 'Lịch sử phiên lưu diễn biến của những lần chạy trước.' : 'Saved run history contains previous timelines.'}</p></div>
      ) : (
        <ol className="cc-timeline">
          {displayed.map(event => <TimelineEvent key={event.event_id} event={event} lang={lang} />)}
        </ol>
      )}
      {milestones.length > 6 && <button type="button" className="cc-button ps-show-events" aria-expanded={showAll} onClick={() => setShowAll(value => !value)}>
        {showAll ? (vi ? 'Thu gọn diễn biến' : 'Show fewer milestones') : (vi ? `Xem ${milestones.length} mốc đã nhận` : `Show ${milestones.length} received milestones`)}
      </button>}
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
