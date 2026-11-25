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

  it('selects approved active scanners and matching Webapp A without launching automatically', async () => {
    const submit = vi.fn().mockResolvedValue(undefined);
    render(<StartRunModal isOpen onClose={() => {}} onSubmit={submit} isSubmitting={false} />);
    fireEvent.change(screen.getByLabelText('Lab Target'), { target: { value: 'lab-webapp-a' } });
    expect(screen.getByLabelText('Target Origin URL')).toHaveValue('http://127.0.0.1:18085');
    fireEvent.click(screen.getByRole('button', { name: 'Approve and select Active + ZAP + Nuclei' }));
    expect(submit).not.toHaveBeenCalled();
    expect(screen.getByRole('checkbox', { name: /Approve bounded active lab checks/ })).toBeChecked();
    expect(screen.getByRole('combobox', { name: 'OWASP ZAP' })).toHaveValue('zap-active');
    fireEvent.click(screen.getByRole('button', { name: 'Launch Execution' }));
    await waitFor(() => expect(submit).toHaveBeenCalledWith(expect.objectContaining({
      target: 'lab-webapp-a', target_origin: 'http://127.0.0.1:18085', execution_scope: 'scan',
      approve_active_verification: true, external_scanners: ['zap-active', 'nuclei'], max_requests: 500,
    })));
  });

  it('returns to ShopLab when changing from Webapp B to business workflow', () => {
    render(<StartRunModal isOpen onClose={() => {}} onSubmit={vi.fn()} isSubmitting={false} />);
    fireEvent.change(screen.getByLabelText('Lab Target'), { target: { value: 'lab-webapp-b' } });
    expect(screen.getByLabelText('Target Origin URL')).toHaveValue('http://127.0.0.1:18086');
    fireEvent.click(screen.getByRole('radio', { name: 'Fixed business workflow' }));
    expect(screen.getByLabelText('Lab Target')).toHaveValue('lab-ecommerce');
    expect(screen.queryByRole('option', { name: 'Webapp B (lab-webapp-b)' })).not.toBeInTheDocument();
  });
});
