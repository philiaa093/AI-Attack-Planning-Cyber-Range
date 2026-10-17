import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { StartRunModal } from '../components/controls/StartRunModal';
import { CurrentActivity } from '../components/activity/CurrentActivity';
import type { SystemStatus } from '../api/types';
import { LanguageProvider } from '../i18n/LanguageContext';
import { displayTool, displayValue } from '../i18n/displayValue';
import { presentationEventTitle } from '../components/presentation/PresentationSummary';

describe('Run budget and verification display', () => {
  it('submits separate budgets and requires opting into active lab checks', async () => {
    const submit = vi.fn().mockResolvedValue(undefined);
    render(<StartRunModal isOpen onClose={() => {}} onSubmit={submit} isSubmitting={false} />);
    expect(screen.getByLabelText('HTTP request budget')).toHaveValue(120);
    expect(screen.getByLabelText('Discovery page budget')).toHaveValue(30);
    const approval = screen.getByRole('checkbox', { name: /Approve bounded active lab checks/ });
    expect(approval).not.toBeChecked();
    fireEvent.change(screen.getByLabelText('HTTP request budget'), { target: { value: '200' } });
    fireEvent.click(approval);
    fireEvent.click(screen.getByRole('button', { name: 'Launch Execution' }));
    await waitFor(() => expect(submit).toHaveBeenCalledWith(expect.objectContaining({
      mode: 'autonomous', planner: 'llm', max_decisions: 30, max_requests: 200, max_pages: 30,
      allow_fallback: false, approve_active_verification: true,
    })));
  });

  it('shows the actual internal tool and a signal without claiming exploitation', () => {
    const system = {
      agent: { state: 'RUNNING', current_action: 'ACTION-WEB-001', planner: 'llm', actual_mode: 'LLM',
        facts_count: 5, current_execution: { tool: 'SafeInputVerificationExecutor', family: 'SQL_INJECTION',
          status: 'RUNNING', resource_ref: '/products', parameter_name: 'q' },
        last_verification: { classification: 'SIGNAL' } },
      run: { state: 'RUNNING', target: 'lab-ecommerce' }, safety: { denials_count: 0, permits_count: 1 },
    } as unknown as SystemStatus;
    render(<LanguageProvider initialLang="vi"><CurrentActivity system={system} latestEvent={null} /></LanguageProvider>);
    expect(screen.getByText('Bộ kiểm tra đầu vào SQL an toàn')).toBeInTheDocument();
    expect(screen.getByText('Có dấu hiệu, chưa xác nhận')).toBeInTheDocument();
    expect(screen.getByText(/Khám phá hoặc có tín hiệu chưa chứng minh/)).toBeInTheDocument();
    expect(screen.queryByText('VERIFIED_IN_LAB')).not.toBeInTheDocument();
  });

  it('translates recorded runtime values while preserving technical identifiers separately', () => {
    expect(displayValue('objective_satisfied', 'vi')).toBe('Đã đạt mục tiêu kiểm tra');
    expect(displayValue('provider_unavailable_halt:FALLBACK_NOT_ALLOWED:PROVIDER_ERROR_JSONDecodeError', 'vi'))
      .toBe('Dừng vì dịch vụ mô hình không khả dụng: Không cho phép dùng phương án dự phòng: Phản hồi của dịch vụ mô hình không phải JSON hợp lệ');
    expect(displayTool('SafePathFixtureVerificationExecutor', 'vi')).toBe('Bộ kiểm tra vượt đường dẫn an toàn');
    expect(presentationEventTitle('PLANNER_STARTED', 'vi')).toBe('Bắt đầu lập kế hoạch');
    expect(presentationEventTitle('PLANNER_RESPONSE_RECEIVED', 'vi')).toBe('Đã nhận phản hồi từ mô hình lập kế hoạch');
  });
});
