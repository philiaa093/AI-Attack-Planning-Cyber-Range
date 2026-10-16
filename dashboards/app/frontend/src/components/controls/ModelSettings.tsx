import React, { useEffect, useState } from 'react';
import { Settings, X, Plus, Pencil, Trash2, KeyRound } from 'lucide-react';
import { apiClient } from '../../api/client';
import type { ModelProfile, ModelProfileInput } from '../../api/modelProfiles';
import { useLanguage } from '../../i18n/LanguageContext';

const emptyForm = (): ModelProfileInput => ({
  name: '', protocol: 'openai-compatible', model: '', endpoint: '', api_key: '', clear_key: false, persist: false,
});
const inputClass = 'w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 focus:border-blue-500 focus:outline-none';

export const ModelSettingsModal: React.FC<{ onClose: () => void }> = ({ onClose }) => {
  const { lang } = useLanguage();
  const vi = lang === 'vi';
  const [profiles, setProfiles] = useState<ModelProfile[]>([]);
  const [form, setForm] = useState<ModelProfileInput>(emptyForm);
  const [editing, setEditing] = useState<string>();
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  useEffect(() => {
    let cancelled = false;
    apiClient.getModelProfiles().then(result => {
      if (!cancelled) setProfiles(result.profiles);
    }).catch(() => {
      if (!cancelled) setError(vi ? 'Không tải được cấu hình. Hãy kiểm tra máy chủ.' : 'Could not load settings. Check the backend.');
    }).finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [vi]);

  const reset = () => { setForm(emptyForm()); setEditing(undefined); setError(''); setNotice(''); };
  const close = () => { setForm(emptyForm()); onClose(); };
  const change = <K extends keyof ModelProfileInput>(key: K, value: ModelProfileInput[K]) => {
    setForm(current => ({ ...current, [key]: value }));
    setNotice('');
  };
  const save = async (event: React.FormEvent) => {
    event.preventDefault();
    setBusy(true); setError(''); setNotice('');
    try {
      const saved = await apiClient.saveModelProfile({ ...form, name: form.name.trim(), model: form.model.trim(), endpoint: form.endpoint.trim() }, editing);
      setProfiles(current => [...current.filter(p => p.id !== saved.id).map(p => ({ ...p, is_active: false, persisted: saved.persisted ? false : p.persisted })), saved]);
      setForm(emptyForm()); setEditing(undefined);
      setNotice(vi ? 'Đã lưu. Lần chạy LLM tiếp theo sẽ dùng cấu hình này.' : 'Saved. The next LLM run will use this profile.');
    } catch {
      setForm(current => ({ ...current, api_key: '' }));
      setError(vi ? 'Không lưu được cấu hình. Hãy kiểm tra địa chỉ API dùng HTTPS (HTTP chỉ dành cho localhost), mô hình và khóa API.' : 'Could not save. Check the HTTPS endpoint (HTTP only for localhost), model and API key.');
    } finally { setBusy(false); }
  };
  const remove = async (id: string) => {
    setBusy(true); setError(''); setNotice('');
    try {
      await apiClient.removeModelProfile(id);
      setProfiles(current => current.filter(p => p.id !== id));
      if (editing === id) reset();
    } catch { setError(vi ? 'Không xóa được cấu hình.' : 'Could not remove settings.'); }
    finally { setBusy(false); }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm">
      <section role="dialog" aria-modal="true" aria-labelledby="model-settings-title" className="flex max-h-[90vh] w-full max-w-3xl flex-col overflow-hidden rounded-xl border border-slate-700 bg-[#111724] text-slate-100 shadow-2xl">
        <div className="flex items-center justify-between border-b border-slate-800 px-5 py-4">
          <h2 id="model-settings-title" className="flex items-center gap-2 font-semibold"><Settings size={18} className="text-blue-400" />{vi ? 'Cấu hình mô hình và API' : 'Model & API settings'}</h2>
          <button type="button" onClick={close} disabled={busy} aria-label={vi ? 'Đóng cấu hình' : 'Close model settings'} className="rounded p-1 text-slate-400 hover:text-white"><X size={20} /></button>
        </div>
        <div className="overflow-y-auto p-5 space-y-5">
          <p className="rounded-lg border border-blue-900 bg-blue-950/30 p-3 text-xs leading-relaxed text-blue-200">
            {vi ? 'Lần chạy LLM tiếp theo dùng cấu hình lưu gần nhất. Sửa và lưu để chọn lại một mô hình. Chọn lưu vào .env để giữ một cấu hình sau khi khởi động lại; cấu hình lưu sau sẽ thay cấu hình đã lưu trước. Khóa được lưu dạng văn bản trên máy chủ. Lưu không kiểm tra kết nối hoặc thay đổi run đang chạy.' : 'The next LLM run uses the most recently saved profile. Edit and save to select a model again. Save to .env to keep one profile after restart; saving another replaces it. The key is stored as plain text on the server. Saving does not test connectivity or change an active run.'}
          </p>
          {error && <p role="alert" className="text-sm text-rose-300">{error}</p>}
          {notice && <p role="status" className="text-sm text-emerald-300">{notice}</p>}
          <div className="grid gap-5 md:grid-cols-2">
            <div className="space-y-3">
              <div className="flex items-center justify-between"><h3 className="text-sm font-semibold">{vi ? 'Mô hình đã thêm' : 'Saved models'}</h3><button type="button" onClick={reset} disabled={busy} className="flex items-center gap-1 text-xs text-blue-300"><Plus size={14} />{vi ? 'Thêm mới' : 'Add new'}</button></div>
              {loading ? <p className="text-xs text-slate-400">{vi ? 'Đang tải…' : 'Loading…'}</p> : profiles.length === 0 && <p className="text-xs text-slate-400">{vi ? 'Chưa có mô hình. Điền biểu mẫu để thêm mô hình.' : 'No models yet. Use the form to add one.'}</p>}
              {profiles.map(profile => (
                <article key={profile.id} className={`rounded-lg border p-3 ${editing === profile.id ? 'border-blue-500 bg-blue-950/20' : 'border-slate-800 bg-slate-900/50'}`}>
                  <div className="flex items-start justify-between gap-2"><strong className="break-all text-sm">{profile.name}</strong><div className="flex gap-2">
                    <button type="button" disabled={busy} aria-label={`${vi ? 'Sửa' : 'Edit'} ${profile.name}`} onClick={() => { setEditing(profile.id); setForm({ name: profile.name, protocol: profile.protocol, model: profile.model, endpoint: profile.endpoint, api_key: '', clear_key: false, persist: profile.persisted ?? false }); setError(''); setNotice(''); }} className="text-slate-400 hover:text-blue-300"><Pencil size={14} /></button>
                    <button type="button" disabled={busy} aria-label={`${vi ? 'Xóa' : 'Remove'} ${profile.name}`} onClick={() => void remove(profile.id)} className="text-slate-400 hover:text-rose-300"><Trash2 size={14} /></button>
                  </div></div>
                  <p className="mt-1 break-all font-mono text-xs text-slate-300">{profile.model}</p>
                  {profile.is_active && <p className="mt-1 text-xs text-emerald-300">{vi ? 'Dùng cho lần chạy LLM tiếp theo' : 'Selected for the next LLM run'}</p>}
                  <p className="mt-1 break-all text-xs text-slate-500">{profile.endpoint}</p>
                  {profile.persisted && <p className="mt-1 text-xs text-slate-400">{vi ? 'Đã lưu trong .env' : 'Saved in .env'}</p>}
                  <p className="mt-2 flex items-center gap-1 text-xs text-slate-400"><KeyRound size={12} />{profile.has_api_key ? (vi ? 'Đã lưu khóa API' : 'API key saved') : (vi ? 'Chưa có khóa API' : 'No API key')}</p>
                </article>
              ))}
            </div>
            <form onSubmit={save} className="space-y-3">
              <h3 className="text-sm font-semibold">{editing ? (vi ? 'Sửa cấu hình' : 'Edit settings') : (vi ? 'Thêm mô hình' : 'Add model')}</h3>
              <label className="block text-xs text-slate-400">{vi ? 'Tên hiển thị' : 'Display name'}<input required maxLength={80} value={form.name} onChange={e => change('name', e.target.value)} className={`${inputClass} mt-1`} placeholder={vi ? 'Mô hình cục bộ / API nghiên cứu' : 'Local model / Research API'} /></label>
              <label className="block text-xs text-slate-400">{vi ? 'Loại API' : 'API type'}<select value={form.protocol} onChange={e => change('protocol', e.target.value as ModelProfile['protocol'])} className={`${inputClass} mt-1`}><option value="openai-compatible">{vi ? 'Tương thích OpenAI' : 'OpenAI-compatible'}</option><option value="anthropic">Anthropic</option></select></label>
              <label className="block text-xs text-slate-400">{vi ? 'Mã mô hình' : 'Model ID'}<input required maxLength={160} value={form.model} onChange={e => change('model', e.target.value)} className={`${inputClass} mt-1`} placeholder={vi ? 'ma-mo-hinh-cua-ban' : 'your-model-id'} /></label>
              <label className="block text-xs text-slate-400">{vi ? 'Địa chỉ API' : 'Endpoint'}<input required type="url" maxLength={512} value={form.endpoint} onChange={e => change('endpoint', e.target.value)} className={`${inputClass} mt-1`} placeholder="https://provider.example/v1" /></label>
              <label className="block text-xs text-slate-400">{vi ? 'Khóa API' : 'API key'}<input type="password" autoComplete="new-password" spellCheck={false} maxLength={4096} disabled={form.clear_key} value={form.api_key} onChange={e => change('api_key', e.target.value)} className={`${inputClass} mt-1`} placeholder={editing ? (vi ? 'Để trống để giữ khóa hiện tại' : 'Leave blank to keep existing key') : (vi ? 'Không bắt buộc với mô hình cục bộ' : 'Optional for local models')} /></label>
              {editing && <label className="flex items-center gap-2 text-xs text-slate-400"><input type="checkbox" checked={form.clear_key} onChange={e => setForm(current => ({ ...current, clear_key: e.target.checked, api_key: '' }))} />{vi ? 'Xóa khóa API hiện tại' : 'Remove existing API key'}</label>}
              <label className="flex items-center gap-2 text-xs text-slate-400"><input type="checkbox" checked={form.persist ?? false} onChange={e => change('persist', e.target.checked)} />{vi ? 'Lưu API và mô hình vào .env (giữ sau khi khởi động lại)' : 'Save API and model to .env (keep after restart)'}</label>
              <button type="submit" disabled={busy || loading} className="w-full rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-500 disabled:opacity-50">{busy ? (vi ? 'Đang lưu…' : 'Saving…') : (vi ? 'Lưu cấu hình' : 'Save settings')}</button>
            </form>
          </div>
        </div>
      </section>
    </div>
  );
};

export const ModelSettingsButton: React.FC = () => {
  const { lang } = useLanguage();
  const [open, setOpen] = useState(false);
  return <>
    <button type="button" onClick={() => setOpen(true)} className="flex items-center gap-1.5 rounded border border-slate-700 bg-slate-900 px-2.5 py-1 text-xs font-semibold text-slate-200 hover:border-blue-500"><Settings size={14} className="text-blue-400" />{lang === 'vi' ? "Mô hình và API" : "Model & API"}</button>
    {open && <ModelSettingsModal onClose={() => setOpen(false)} />}
  </>;
};
