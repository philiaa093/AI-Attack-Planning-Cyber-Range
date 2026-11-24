import React from 'react';
import { Activity, ClipboardList, FileCheck2, Radar, ShieldCheck } from 'lucide-react';
import type { AgentEvent } from '../../api/types';
import { useLanguage } from '../../i18n/LanguageContext';

interface PresentationFlowProps {
  events: AgentEvent[];
  runId: string | null;
}

type EventDescription = { vi: string; en: string; warning?: boolean };

// Each message describes only the event received, not the outcome of a later step.
const steps: Array<{
  name: string[];
  description: string[];
  icon: React.ElementType;
  events: Record<string, EventDescription>;
}> = [
  {
    name: ['Quan sát', 'Observe'],
    description: ['Nhận thông tin từ môi trường', 'Receive information from the environment'],
    icon: Radar,
    events: { OBSERVATION_RECEIVED: { vi: 'Đã nhận quan sát', en: 'Observation received' } },
  },
  {
    name: ['Đề xuất', 'Propose'],
    description: ['Planner đề xuất hành động', 'Planner proposes an action'],
    icon: ClipboardList,
    events: {
      PLANNER_STARTED: { vi: 'Bắt đầu lập kế hoạch', en: 'Planning started' },
      PLANNER_PROPOSED: { vi: 'Đã nhận đề xuất', en: 'Proposal received' },
      PLANNER_FALLBACK: { vi: 'Đã dùng phương án dự phòng', en: 'Fallback used', warning: true },
    },
  },
  {
    name: ['An toàn', 'Safety'],
    description: ['Kiểm tra đề xuất theo chính sách', 'Check the proposal against policy'],
    icon: ShieldCheck,
    events: {
      SAFETY_EVALUATION_STARTED: { vi: 'Bắt đầu kiểm tra', en: 'Safety check started' },
      SAFETY_PERMITTED: { vi: 'Đã ghi nhận cho phép', en: 'Permission recorded' },
      SAFETY_DENIED: { vi: 'Đã ghi nhận từ chối', en: 'Refusal recorded', warning: true },
    },
  },
  {
    name: ['Thực thi', 'Execute'],
    description: ['Thực hiện hành động được duyệt', 'Execute an approved action'],
    icon: Activity,
    events: {
      ACTION_DISPATCH_STARTED: { vi: 'Bắt đầu phát lệnh', en: 'Dispatch started' },
      ACTION_DISPATCHED: { vi: 'Đã phát lệnh', en: 'Action dispatched' },
      ACTION_COMPLETED: { vi: 'Hành động đã kết thúc', en: 'Action completed' },
      ACTION_FAILED: { vi: 'Hành động gặp lỗi', en: 'Action failed', warning: true },
    },
  },
  {
    name: ['Bằng chứng', 'Evidence'],
    description: ['Ghi nhận kết quả để kiểm tra', 'Record results for review'],
    icon: FileCheck2,
    events: {
      EVIDENCE_RECORDED: { vi: 'Đã ghi bằng chứng', en: 'Evidence recorded' },
      EVIDENCE_VERIFIED: { vi: 'Đã xác minh bằng chứng', en: 'Evidence verified' },
    },
  },
];

export const PresentationFlow: React.FC<PresentationFlowProps> = ({ events, runId }) => {
  const { lang } = useLanguage();
  const vi = lang === 'vi';
  const runEvents = runId ? events.filter((event) => event.run_id === runId) : [];

  return (
    <section className="pf-flow" aria-label={vi ? 'Quy trình và sự kiện đã nhận' : 'Workflow and received events'}>
      <div className="pf-heading">
        <div>
          <h3>{vi ? 'Hệ thống hoạt động như thế nào?' : 'How does the system work?'}</h3>
          <p>{vi ? 'Từ thông tin quan sát được đến bằng chứng có thể xem lại.' : 'From observations to evidence available for review.'}</p>
        </div>
      </div>
      <ol className="pf-steps">
        {steps.map((step, index) => {
          const descriptions: Record<string, EventDescription> = step.events;
          const event = [...runEvents].reverse().find((item) => Object.prototype.hasOwnProperty.call(descriptions, item.type));
          const description = event ? descriptions[event.type] : undefined;
          const Icon = step.icon;
          return (
            <li className={`pf-step${description ? ' pf-recorded' : ''}${description?.warning ? ' pf-warning' : ''}`} key={step.name[0]}>
              <div className="pf-step-icon"><Icon size={21} aria-hidden="true" /><span>{index + 1}</span></div>
              <div className="pf-step-copy">
                <h4>{step.name[vi ? 0 : 1]}</h4>
                <p>{step.description[vi ? 0 : 1]}</p>
                <div className="pf-step-state">{description ? description[vi ? 'vi' : 'en'] : (vi ? 'Chưa nhận sự kiện' : 'No event received')}</div>
              </div>
            </li>
          );
        })}
      </ol>
      <p className="pf-flow-note">{vi
        ? 'Mỗi ô là sự kiện gần nhất đã nhận cho bước đó trong phiên này; các ô không nhất thiết thuộc cùng một hành động. Chưa nhận sự kiện không có nghĩa là bước đó chưa từng xảy ra.'
        : 'Each step shows its latest received event for this run; events may refer to different actions. No event received does not mean the step never occurred.'}</p>
    </section>
  );
};
