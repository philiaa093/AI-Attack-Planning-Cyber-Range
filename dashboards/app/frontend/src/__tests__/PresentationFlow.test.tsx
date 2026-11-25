import { describe, expect, it } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import type { AgentEvent, SystemStatus } from '../api/types';
import { PresentationFlow } from '../components/presentation/PresentationFlow';
import { PresentationHero } from '../components/presentation/PresentationHero';
import { LanguageProvider } from '../i18n/LanguageContext';

const event = (type: string, runId = 'run-1'): AgentEvent => ({
  event_id: `${runId}-${type}`,
  run_id: runId,
  type,
  timestamp_utc: '2026-11-25T00:00:00Z',
  payload: {},
});

describe('PresentationHero objective status', () => {
  const system = (stop_reason: string): SystemStatus => ({
    run: { run_id: 'run-1', state: 'COMPLETED', stop_reason, target: 'lab-ecommerce' },
    agent: { actual_mode: 'LLM', requested_mode: 'LLM', current_phase: 'RECON' },
  } as unknown as SystemStatus);

  it('distinguishes a limited stop from evidence of objective completion', () => {
    render(<LanguageProvider initialLang="vi"><PresentationHero
      system={system('no_approved_action_can_make_progress')} latestEvent={null} />
    </LanguageProvider>);
    expect(screen.getByRole('heading', { name: 'Phiên chạy đã kết thúc' })).toBeInTheDocument();
    expect(screen.getByText('Phiên đã dừng; chưa có bằng chứng xác nhận mục tiêu đã hoàn thành.')).toBeInTheDocument();
  });

  it('does not invent an unconfirmed stop for other terminal reasons', () => {
    render(<LanguageProvider initialLang="en"><PresentationHero
      system={system('objective_completed')} latestEvent={null} />
    </LanguageProvider>);
    expect(screen.queryByText('The run has stopped; objective completion has not been established.')).not.toBeInTheDocument();
  });
});

const step = (name: string) => {
  const item = screen.getByRole('heading', { name }).closest('li');
  if (!item) throw new Error(`Step ${name} is missing`);
  return within(item);
};

describe('PresentationFlow', () => {
  it('shows a refusal without inventing an execution and ignores other runs', () => {
    render(<LanguageProvider initialLang="en"><PresentationFlow runId="run-1" events={[
      event('PLANNER_PROPOSED'), event('SAFETY_DENIED'), event('ACTION_COMPLETED', 'run-2'),
    ]} /></LanguageProvider>);

    expect(step('Propose').getByText('Proposal received')).toBeInTheDocument();
    expect(step('Safety').getByText('Refusal recorded')).toBeInTheDocument();
    expect(step('Execute').getByText('No event received')).toBeInTheDocument();
    expect(step('Evidence').getByText('No event received')).toBeInTheDocument();
  });

  it('reports the latest received event per step, including failure and verification', () => {
    render(<LanguageProvider initialLang="vi"><PresentationFlow runId="run-1" events={[
      event('SAFETY_PERMITTED'), event('ACTION_DISPATCH_STARTED'), event('ACTION_FAILED'),
      event('EVIDENCE_RECORDED'), event('EVIDENCE_VERIFIED'),
    ]} /></LanguageProvider>);

    expect(step('An toàn').getByText('Đã ghi nhận cho phép')).toBeInTheDocument();
    expect(step('Thực thi').getByText('Hành động gặp lỗi')).toBeInTheDocument();
    expect(step('Bằng chứng').getByText('Đã xác minh bằng chứng')).toBeInTheDocument();
    expect(screen.getByText(/không nhất thiết thuộc cùng một hành động/)).toBeInTheDocument();
  });

  it('does not display an event without a selected run', () => {
    render(<LanguageProvider initialLang="en"><PresentationFlow runId={null} events={[event('OBSERVATION_RECEIVED')]} /></LanguageProvider>);

    expect(step('Observe').getByText('No event received')).toBeInTheDocument();
  });
});
