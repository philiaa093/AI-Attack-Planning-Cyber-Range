import React, { useState } from 'react';
import { X, Play, ShieldAlert, Cpu, Sparkles, AlertCircle, UserCheck, PlayCircle, Eye } from 'lucide-react';
import type { StartRunRequest, ControlMode } from '../../api/types';
import { useLanguage } from '../../i18n/LanguageContext';
import { displayValue } from '../../i18n/displayValue';

interface StartRunModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (req: StartRunRequest) => Promise<void>;
  isSubmitting: boolean;
}

export const StartRunModal: React.FC<StartRunModalProps> = ({
  isOpen,
  onClose,
  onSubmit,
  isSubmitting,
}) => {
  const { lang, t } = useLanguage();
  const [mode, setMode] = useState<string>('deny-demo');
  const [planner, setPlanner] = useState<string>('rule');
  const [controlMode, setControlMode] = useState<ControlMode>('AUTONOMOUS');
  const [allowFallback, setAllowFallback] = useState<boolean>(true);
  const [target, setTarget] = useState<string>('lab-ecommerce');
  const [maxDecisions, setMaxDecisions] = useState<number>(10);
  const [previewOnePage, setPreviewOnePage] = useState<boolean>(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitError(null);
    try {
      await onSubmit({
        mode,
        planner,
        control_mode: controlMode,
        target,
        max_decisions: maxDecisions,
        scenario: 'SCN-001',
        approve_read_only: true,
        preview_one_page: previewOnePage,
        allow_fallback: allowFallback,
      });
      onClose();
    } catch (err) {
      setSubmitError(err instanceof Error ? err.message : String(err));
    }
  };

  const modeOptions = [
    {
      id: 'deny-demo',
      title: t.modeDenyDemoTitle,
      subtitle: lang === 'vi' ? "Minh họa việc áp dụng cổng an toàn trung tâm" : "Showcase Centralized Safety Gate Enforcement",
      desc: t.modeDenyDemoDesc,
      badge: lang === 'vi' ? "Chứng minh không gửi yêu cầu mạng" : "Zero Dispatch Proof",
      badgeColor: 'bg-emerald-950/80 text-emerald-300 border-emerald-800/60',
      icon: ShieldAlert,
    },
    {
      id: 'autonomous',
      title: t.modeAutonomousTitle,
      subtitle: lang === 'vi' ? "Chu trình khám phá khép kín hoàn chỉnh" : "Full Closed-Loop Discovery Cycle",
      desc: t.modeAutonomousDesc,
      badge: lang === 'vi' ? "Cần Docker" : "Docker Required",
      badgeColor: 'bg-blue-950/80 text-blue-300 border-blue-800/60',
      icon: Cpu,
    },
    {
      id: 'presentation',
      title: t.modePresentationTitle,
      subtitle: lang === 'vi' ? "Thực thi cấu hình sẵn trong giới hạn" : "Bounded Pre-configured Execution",
      desc: t.modePresentationDesc,
      badge: lang === 'vi' ? "Giới hạn an toàn" : "Safe Bounded",
      badgeColor: 'bg-indigo-950/80 text-indigo-300 border-indigo-800/60',
      icon: Sparkles,
    },
  ];

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-xs p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="start-run-title"
    >
      <div className="bg-[#111724] border border-slate-700/80 rounded-xl w-full max-w-xl shadow-2xl overflow-hidden animate-in fade-in duration-150">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-slate-800 bg-slate-900/60">
          <div className="flex items-center space-x-2">
            <Play className="w-5 h-5 text-blue-400" />
            <h2 id="start-run-title" className="text-sm font-semibold tracking-wide text-slate-200">
              {t.configureLaunchRun}
            </h2>
          </div>
          <button
            onClick={onClose}
            aria-label={lang === 'vi' ? "Đóng hộp thoại" : "Close modal"}
            className="p-1 rounded text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Form Body */}
        <form onSubmit={handleSubmit}>
          <div className="p-5 space-y-4 max-h-[70vh] overflow-y-auto">
            {submitError && (
              <div className="p-3 rounded bg-rose-950/40 border border-rose-900/60 text-rose-300 text-xs flex items-start space-x-2">
                <AlertCircle className="w-4 h-4 text-rose-400 shrink-0 mt-0.5" />
                <span>{displayValue(submitError, lang)}</span>
              </div>
            )}

            {/* Mode Selector */}
            <div className="space-y-2">
              <label className="text-xs font-semibold text-slate-300 uppercase tracking-wider block">
                {t.executionScenarioMode}
              </label>
              <div className="space-y-2">
                {modeOptions.map((opt) => {
                  const isSelected = mode === opt.id;
                  const Icon = opt.icon;
                  return (
                    <div
                      key={opt.id}
                      onClick={() => setMode(opt.id)}
                      className={`p-3 rounded-lg border cursor-pointer transition-all ${
                        isSelected
                          ? 'bg-blue-950/30 border-blue-500 ring-1 ring-blue-500/40'
                          : 'bg-slate-900/60 border-slate-800 hover:border-slate-700'
                      }`}
                    >
                      <div className="flex items-center justify-between">
                        <div className="flex items-center space-x-2">
                          <Icon className={`w-4 h-4 ${isSelected ? 'text-blue-400' : 'text-slate-400'}`} />
                          <span className="font-semibold text-slate-200 text-xs">{opt.title}</span>
                        </div>
                        <span className={`text-[10px] font-mono px-2 py-0.5 rounded border ${opt.badgeColor}`}>
                          {opt.badge}
                        </span>
                      </div>
                      <p className="mt-1 text-[11px] text-slate-400 leading-relaxed pl-6">{opt.desc}</p>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Control Mode Selector */}
            <div className="space-y-2">
              <label className="text-xs font-semibold text-slate-300 uppercase tracking-wider block">
                {t.executionControlMode}
              </label>
              <div className="grid grid-cols-3 gap-2">
                {[
                  {
                    id: 'AUTONOMOUS' as ControlMode,
                    title: t.controlAutonomousTitle,
                    desc: t.controlAutonomousDesc,
                    icon: PlayCircle,
                  },
                  {
                    id: 'ASSISTED' as ControlMode,
                    title: t.controlAssistedTitle,
                    desc: t.controlAssistedDesc,
                    icon: Eye,
                  },
                  {
                    id: 'MANUAL' as ControlMode,
                    title: t.controlManualTitle,
                    desc: t.controlManualDesc,
                    icon: UserCheck,
                  },
                ].map((item) => {
                  const isSelected = controlMode === item.id;
                  const Icon = item.icon;
                  return (
                    <div
                      key={item.id}
                      onClick={() => setControlMode(item.id)}
                      className={`p-2.5 rounded-lg border cursor-pointer transition-all ${
                        isSelected
                          ? 'bg-blue-950/40 border-blue-500 ring-1 ring-blue-500/40 text-blue-200'
                          : 'bg-slate-900/60 border-slate-800 text-slate-400 hover:border-slate-700 hover:text-slate-300'
                      }`}
                    >
                      <div className="flex items-center space-x-1.5 mb-1">
                        <Icon className={`w-3.5 h-3.5 ${isSelected ? 'text-blue-400' : 'text-slate-500'}`} />
                        <span className="font-semibold text-xs text-slate-200">{item.title}</span>
                      </div>
                      <p className="text-[10px] text-slate-400 leading-snug">{item.desc}</p>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Advanced Configuration */}
            <div className="grid grid-cols-2 gap-3 pt-2 text-xs">
              <div>
                <label className="text-[11px] font-medium text-slate-400 block mb-1">{t.plannerStrategy}</label>
                <select
                  value={planner}
                  onChange={(e) => setPlanner(e.target.value)}
                  className="w-full bg-slate-900 border border-slate-800 rounded px-2.5 py-1.5 text-slate-200 font-mono text-xs focus:outline-hidden focus:border-blue-500"
                >
                  <option value="rule">{lang === 'vi' ? "Theo luật (bộ máy quy tắc tất định)" : "rule (Deterministic Rule Engine)"}</option>
                  <option value="llm">{lang === 'vi' ? "Mô hình ngôn ngữ lớn (lập kế hoạch bằng LLM thực)" : "llm (Real LLM Guided Planner)"}</option>
                  <option value="llm-unavailable">{lang === 'vi' ? "LLM không khả dụng (kiểm tra dự phòng)" : "llm-unavailable (Fallback Test)"}</option>
                  <option value="hybrid">{lang === 'vi' ? "Kết hợp (chỉ có đặc tả)" : "hybrid (Hybrid SPEC-ONLY)"}</option>
                </select>
              </div>

              <div>
                <label className="text-[11px] font-medium text-slate-400 block mb-1">{t.labTarget}</label>
                <input
                  type="text"
                  value={target}
                  onChange={(e) => setTarget(e.target.value)}
                  className="w-full bg-slate-900 border border-slate-800 rounded px-2.5 py-1.5 text-slate-200 font-mono text-xs focus:outline-hidden focus:border-blue-500"
                />
              </div>

              <div>
                <label className="text-[11px] font-medium text-slate-400 block mb-1">{t.maxDecisionsLimit}</label>
                <input
                  type="number"
                  min={1}
                  max={50}
                  value={maxDecisions}
                  onChange={(e) => setMaxDecisions(Number(e.target.value))}
                  className="w-full bg-slate-900 border border-slate-800 rounded px-2.5 py-1.5 text-slate-200 font-mono text-xs focus:outline-hidden focus:border-blue-500"
                />
              </div>

              <div className="space-y-2 pt-1">
                <div className="flex items-center space-x-2">
                  <input
                    type="checkbox"
                    id="allow-fallback"
                    checked={allowFallback}
                    onChange={(e) => setAllowFallback(e.target.checked)}
                    className="rounded border-slate-700 bg-slate-900 text-blue-600 focus:ring-0"
                  />
                  <label htmlFor="allow-fallback" className="text-[11px] text-slate-400 cursor-pointer">
                    {t.allowFallbackToRule}
                  </label>
                </div>
                <div className="flex items-center space-x-2">
                  <input
                    type="checkbox"
                    id="preview-mode"
                    checked={previewOnePage}
                    onChange={(e) => setPreviewOnePage(e.target.checked)}
                    className="rounded border-slate-700 bg-slate-900 text-blue-600 focus:ring-0"
                  />
                  <label htmlFor="preview-mode" className="text-[11px] text-slate-400 cursor-pointer">
                    {t.singleStepPreview}
                  </label>
                </div>
              </div>
            </div>
          </div>

          {/* Footer */}
          <div className="p-4 border-t border-slate-800 bg-slate-900/60 flex items-center justify-end space-x-2">
            <button
              type="button"
              onClick={onClose}
              disabled={isSubmitting}
              className="px-4 py-1.5 rounded text-xs font-medium bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700"
            >
              {t.cancel}
            </button>
            <button
              type="submit"
              disabled={isSubmitting}
              aria-label={lang === 'vi' ? "Bắt đầu thực thi" : "Launch Execution"}
              className="px-4 py-1.5 rounded text-xs font-semibold bg-blue-600 hover:bg-blue-500 text-white disabled:opacity-50 flex items-center space-x-1.5 shadow-sm"
            >
              <Play className="w-3.5 h-3.5" />
              <span>{isSubmitting ? t.startingRun : t.launchExecution}</span>
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
