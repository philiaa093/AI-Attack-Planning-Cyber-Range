import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { ModelSettingsButton } from '../components/controls/ModelSettings';
import { apiClient } from '../api/client';
import type { ModelProfile } from '../api/modelProfiles';

vi.mock('../api/client', () => ({ apiClient: {
  getModelProfiles: vi.fn(), saveModelProfile: vi.fn(), removeModelProfile: vi.fn(),
} }));

const saved: ModelProfile = { id: 'profile-1', name: 'Research', protocol: 'openai-compatible',
  model: 'custom-model', endpoint: 'https://provider.example/v1', has_api_key: true, connection_status: 'NOT_TESTED' };

beforeEach(() => { vi.resetAllMocks(); vi.mocked(apiClient.getModelProfiles).mockResolvedValue({ profiles: [] }); });

describe('Model configuration', () => {
  it('adds custom model/endpoint with masked key and clears it after saving', async () => {
    vi.mocked(apiClient.saveModelProfile).mockResolvedValue(saved);
    render(<ModelSettingsButton />);
    expect(apiClient.getModelProfiles).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'Model & API' }));
    await screen.findByText('No models yet. Use the form to add one.');
    fireEvent.change(screen.getByLabelText('Display name'), { target: { value: 'Research' } });
    fireEvent.change(screen.getByLabelText('Model ID'), { target: { value: 'custom-model' } });
    fireEvent.change(screen.getByLabelText('Endpoint'), { target: { value: 'https://provider.example/v1' } });
    const key = screen.getByLabelText('API key');
    expect(key).toHaveAttribute('type', 'password');
    fireEvent.change(key, { target: { value: 'test-only-key' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save settings' }));
    await screen.findByText('Settings saved for the current backend session.');
    expect(apiClient.saveModelProfile).toHaveBeenCalledWith(expect.objectContaining({ model: 'custom-model', endpoint: 'https://provider.example/v1', api_key: 'test-only-key' }), undefined);
    expect(key).toHaveValue('');
    expect(screen.getByText('API key saved')).toBeInTheDocument();
  });

  it('edits without retrieving existing secret and supports removing the profile', async () => {
    vi.mocked(apiClient.getModelProfiles).mockResolvedValue({ profiles: [saved] });
    vi.mocked(apiClient.saveModelProfile).mockResolvedValue({ ...saved, has_api_key: false });
    vi.mocked(apiClient.removeModelProfile).mockResolvedValue({ removed: true });
    render(<ModelSettingsButton />);
    fireEvent.click(screen.getByRole('button', { name: 'Model & API' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Edit Research' }));
    expect(screen.getByLabelText('API key')).toHaveValue('');
    fireEvent.click(screen.getByLabelText('Remove existing API key'));
    expect(screen.getByLabelText('API key')).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: 'Save settings' }));
    await screen.findByText('No API key');
    expect(apiClient.saveModelProfile).toHaveBeenCalledWith(expect.objectContaining({ clear_key: true, api_key: '' }), 'profile-1');
    fireEvent.click(screen.getByRole('button', { name: 'Remove Research' }));
    await screen.findByText('No models yet. Use the form to add one.');
  });

  it('close discards entered key and errors do not render backend secret text', async () => {
    vi.mocked(apiClient.saveModelProfile).mockRejectedValue(new Error('sensitive-key-do-not-show'));
    render(<ModelSettingsButton />);
    fireEvent.click(screen.getByRole('button', { name: 'Model & API' }));
    await screen.findByText('No models yet. Use the form to add one.');
    fireEvent.change(screen.getByLabelText('API key'), { target: { value: 'test-only-key' } });
    fireEvent.submit(screen.getByRole('button', { name: 'Save settings' }).closest('form')!);
    await screen.findByRole('alert');
    expect(screen.queryByText('sensitive-key-do-not-show')).not.toBeInTheDocument();
    expect(screen.getByLabelText('API key')).toHaveValue('');
    fireEvent.change(screen.getByLabelText('API key'), { target: { value: 'discard-on-close' } });
    fireEvent.click(screen.getByRole('button', { name: 'Close model settings' }));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Model & API' }));
    await waitFor(() => expect(screen.getByLabelText('API key')).toHaveValue(''));
  });
});
