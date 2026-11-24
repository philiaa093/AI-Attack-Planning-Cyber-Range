import { afterEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { apiClient } from '../api/client';
import type { RunCoverage } from '../api/types';
import { CoveragePanel } from '../components/coverage/CoveragePanel';
import { LanguageProvider } from '../i18n/LanguageContext';

const coverage: RunCoverage = {
  run_id: 'RUN-FIXTURE', integrity: 'VERIFIED', record_count: 3,
  scope: { execution_scope: 'scan', workflow_approved: false,
    active_verification_approved: true, selected_scanners: ['nuclei'] },
  workflow: { status: 'NOT_SELECTED', restore: 'UNKNOWN', recorded_checks: 0, reason: 'WORKFLOW_NOT_APPROVED' },
  scanners: [
    { tool: 'nuclei', status: 'COMPLETED', coverage: 'PARTIAL', reason: null, evidence_id: 'EV-SCAN',
      seed_coverage: { observed_seed_count: 21, requested_seed_count: 16, not_requested_seed_count: 5 } },
    { tool: 'zap-active', status: 'NOT_SELECTED', coverage: 'NOT_RECORDED', reason: 'NOT_SELECTED', seed_coverage: {}, evidence_id: null },
  ],
  verifications: [{ action: 'ACTION-WEB-001', resource: '/products', parameter: 'category',
    attempts: 3, classification: 'INCONCLUSIVE', reason: 'Invalid baseline', evidence_id: 'EV-WEB' }],
  matrix: [{ check: 'legacy', route: '/admin', method: 'GET', role: 'USER', auth_state: 'AUTHENTICATED',
    case: 'ADMIN_ACCESS', negative: true, expected: 'HTTP 403', status: 'UNKNOWN',
    reason: 'CHECK_CONTEXT_NOT_RECORDED_OR_MISMATCHED', evidence_id: 'EV-CHECK', http_status: null }],
  legacy_workflow_checks: [{ check: 'legacy', status: 'PASS', evidence_id: 'EV-CHECK' }],
};

afterEach(() => vi.restoreAllMocks());

describe('Coverage panel', () => {
  it('shows partial scanner coverage, skipped workflow and unknown legacy matrix context', async () => {
    vi.spyOn(apiClient, 'getRunCoverage').mockResolvedValue(coverage);
    render(<LanguageProvider initialLang="vi"><CoveragePanel runId="RUN-FIXTURE" /></LanguageProvider>);
    expect(await screen.findByText(/URL đã gửi \/ đã quan sát: 16 \/ 21/)).toBeInTheDocument();
    expect(screen.getByText(/5 URL chưa gửi; lý do cụ thể chưa được ghi/)).toBeInTheDocument();
    expect(screen.getByText('Workflow chưa được phê duyệt')).toBeInTheDocument();
    expect(screen.getByText('Evidence cũ thiếu hoặc không khớp ngữ cảnh route/role')).toBeInTheDocument();
    expect(screen.getByText(/3 lượt/)).toBeInTheDocument();
    expect(screen.getByText(/Invalid baseline/)).toBeInTheDocument();
    fireEvent.click(screen.getByText(/Check cũ chưa đủ ngữ cảnh/));
    expect(screen.getByText(/legacy: Đạt/)).toBeInTheDocument();
  });

  it('does not present unverified evidence as coverage', async () => {
    vi.spyOn(apiClient, 'getRunCoverage').mockResolvedValue({ ...coverage, integrity: 'FAILED' });
    render(<LanguageProvider initialLang="vi"><CoveragePanel runId="RUN-FIXTURE" /></LanguageProvider>);
    expect(await screen.findByText(/Chưa thể hiển thị kết quả coverage/)).toBeInTheDocument();
    expect(screen.queryByText(/16 \/ 21/)).not.toBeInTheDocument();
  });

  it('does not fetch before a run is selected', async () => {
    const get = vi.spyOn(apiClient, 'getRunCoverage');
    render(<LanguageProvider initialLang="vi"><CoveragePanel runId={null} /></LanguageProvider>);
    expect(screen.getByText('Chưa chọn phiên.')).toBeInTheDocument();
    await waitFor(() => expect(get).not.toHaveBeenCalled());
  });
});
