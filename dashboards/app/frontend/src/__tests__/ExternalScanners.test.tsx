import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { StartRunModal } from '../components/controls/StartRunModal';
import { CurrentActivity } from '../components/activity/CurrentActivity';
import type { SystemStatus } from '../api/types';

describe('External scanner controls', () => {
  it('requires approval before selecting and submitting scanners', async () => {
    const submit = vi.fn().mockResolvedValue(undefined);
    render(<StartRunModal isOpen onClose={() => {}} onSubmit={submit} isSubmitting={false} />);
    const zap = screen.getByRole('combobox', { name: 'OWASP ZAP' });
    expect(zap).toBeDisabled();
    fireEvent.click(screen.getByRole('checkbox', { name: /Approve bounded active lab checks/ }));
    expect(zap).toBeEnabled();
    fireEvent.change(zap, { target: { value: 'zap-active' } });
    fireEvent.click(screen.getByRole('checkbox', { name: /Nuclei:/ }));
    fireEvent.click(screen.getByRole('button', { name: 'Launch Execution' }));
    await waitFor(() => expect(submit).toHaveBeenCalledWith(expect.objectContaining({
      approve_active_verification: true, external_scanners: ['zap-active', 'nuclei'],
    })));
  });

  it('shows a scanner failure separately from zero findings', () => {
    const system = { agent: { state: 'RUNNING', facts_count: 1,
      scanner_status: { nuclei: { status: 'ERROR', coverage: 'INCOMPLETE', reason: 'SCANNER_TIMEOUT' } } },
      run: { state: 'RUNNING' }, safety: { denials_count: 0, permits_count: 1 },
    } as unknown as SystemStatus;
    render(<CurrentActivity system={system} latestEvent={null} />);
    expect(screen.getByText('SCANNER_TIMEOUT')).toBeInTheDocument();
    expect(screen.getByText('Coverage: INCOMPLETE')).toBeInTheDocument();
    expect(screen.queryByText('0 unconfirmed candidates')).not.toBeInTheDocument();
  });
});
