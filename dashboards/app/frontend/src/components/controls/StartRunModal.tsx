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
  const [mode, setMode] = useState<string>('autonomous');
  const [planner, setPlanner] = useState<string>('llm');
  const [controlMode, setControlMode] = useState<ControlMode>('AUTONOMOUS');
  const [allowFallback, setAllowFallback] = useState<boolean>(false);
  const [target, setTarget] = useState<string>('lab-ecommerce');
  const [targetOrigin, setTargetOrigin] = useState<string>('http://10.0.0.2:8080');
  const [maxDecisions, setMaxDecisions] = useState<number>(30);
  const [maxRequests, setMaxRequests] = useState(120);
  const [maxPages, setMaxPages] = useState(30);
  const [approveActiveVerification, setApproveActiveVerification] = useState(false);
  const [zapMode, setZapMode] = useState<'' | 'zap-passive' | 'zap-active'>('');
  const [useNuclei, setUseNuclei] = useState(false);
  const [approveWorkflow, setApproveWorkflow] = useState(false);
  const [executionScope, setExecutionScope] = useState<'scan' | 'workflow'>('scan');
  const [previewOnePage, setPreviewOnePage] = useState<boolean>(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const scanOrigins: Record<string, string> = {
    'lab-webapp-a': 'http://127.0.0.1:18085',
    'lab-webapp-b': 'http://127.0.0.1:18086',
  };
  const disposableTarget = target in scanOrigins;
  const selectTarget = (next: string) => {
    setTarget(next);
    setTargetOrigin(scanOrigins[next] ?? 'http://127.0.0.1:18088');
  };

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitError(null);
    const normalizedOrigin = targetOrigin.trim().replace(/\/+$/, '');
    const knownTarget = target === 'lab-ecommerce'
      ? ['http://127.0.0.1:18088', 'http://10.0.0.2:8080'].includes(normalizedOrigin)
      : executionScope === 'scan' && scanOrigins[target] === normalizedOrigin;
    if ((executionScope === 'workflow' || mode !== 'deny-demo') && !knownTarget) {
      setSubmitError('ISOLATED_LAB_TARGET_UNSUPPORTED');
      return;
    }
    try {
      await onSubmit({
        mode: executionScope === 'workflow' ? 'autonomous' : mode,
        planner,
        control_mode: executionScope === 'workflow' ? 'AUTONOMOUS' : controlMode,
        target,
        target_origin: targetOrigin,
        max_decisions: maxDecisions,
        max_requests: maxRequests,
        max_pages: maxPages,
        scenario: 'SCN-001',
        approve_read_only: true,
        execution_scope: executionScope,
        approve_active_verification: executionScope === 'scan' && approveActiveVerification && !previewOnePage,
        approve_authenticated_workflow: executionScope === 'workflow' && approveWorkflow,
        external_scanners: executionScope === 'scan' && approveActiveVerification && !previewOnePage && mode !== 'deny-demo'
          ? [...(zapMode ? [zapMode] : []), ...(useNuclei ? ['nuclei' as const] : [])] : [],
        preview_one_page: executionScope === 'scan' && previewOnePage,
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
                <span>{submitError.includes('SCAN_REDACTION_UNSAFE')
                  ? (lang === 'vi' ? 'Không thể chạy scan: bộ ghi evidence chưa che được giá trị CSRF trong HTML. Cần sửa redaction trước.' : 'Scan blocked: evidence redaction does not yet protect CSRF values in HTML.')
                  : submitError.includes('ISOLATED_LAB_TARGET_UNSUPPORTED')
                  ? (lang === 'vi' ? 'Chọn đúng target và địa chỉ lab tương ứng. Workflow chỉ hỗ trợ ShopLab.' : 'Choose a supported target and its matching lab address. Workflows support ShopLab only.')
                  : displayValue(submitError, lang)}</span>
              </div>
            )}

            <fieldset className="space-y-2 rounded border border-slate-700 p-3">
              <legend className="px-1 text-xs font-semibold text-slate-200">{lang === 'vi' ? 'Nội dung phiên' : 'Run scope'}</legend>
              <label className="flex items-center gap-2 text-xs text-slate-200">
                <input type="radio" name="execution-scope" checked={executionScope === 'scan'} onChange={() => setExecutionScope('scan')} />
                {lang === 'vi' ? 'Scan và kiểm tra chủ động' : 'Scan and active verification'}
              </label>
              <label className="flex items-center gap-2 text-xs text-slate-200">
                <input type="radio" name="execution-scope" checked={executionScope === 'workflow'} onChange={() => {
                  setExecutionScope('workflow');
                  if (disposableTarget) selectTarget('lab-ecommerce');
                }} />
                {lang === 'vi' ? 'Workflow nghiệp vụ cố định' : 'Fixed business workflow'}
              </label>
              <p className="text-xs text-slate-400">{lang === 'vi' ? 'Workflow cố định không dùng planner hoặc scanner. Webapp A/B chạy trên container riêng từng phiên. ShopLab dùng bản sao volume Docker hoặc snapshot/restore GNS3; ShopLab có thể tạm gián đoạn.' : 'The fixed workflow uses no planner or scanner. Webapp A/B use disposable containers per run. ShopLab uses a Docker volume copy or GNS3 snapshot/restore and may be briefly unavailable.'}</p>
            </fieldset>

            {/* Mode Selector */}
            {executionScope === 'scan' && <div className="space-y-2">
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
            </div>}

            {/* Control Mode Selector */}
            {executionScope === 'scan' && <div className="space-y-2">
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
            </div>}

            {/* Advanced Configuration */}
            <div className="grid grid-cols-2 gap-3 pt-2 text-xs">
              {executionScope === 'scan' ? <div>
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
              </div> : <div className="text-slate-400">{lang === 'vi' ? 'Workflow cố định, không dùng planner.' : 'Fixed workflow, no planner is used.'}</div>}

              <div>
                <label htmlFor="lab-target" className="text-[11px] font-medium text-slate-400 block mb-1">{t.labTarget}</label>
                <select
                  id="lab-target"
                  value={target}
                  onChange={(e) => selectTarget(e.target.value)}
                  className="w-full bg-slate-900 border border-slate-800 rounded px-2.5 py-1.5 text-slate-200 font-mono text-xs focus:outline-hidden focus:border-blue-500"
                >
                  <option value="lab-ecommerce">ShopLab (lab-ecommerce)</option>
                  {executionScope === 'scan' && <>
                    <option value="lab-webapp-a">Webapp A (lab-webapp-a)</option>
                    <option value="lab-webapp-b">Webapp B (lab-webapp-b)</option>
                  </>}
                </select>
                {disposableTarget && <p className="mt-1 text-[10px] text-slate-400">{lang === 'vi'
                  ? 'Lab có lỗi cố ý để kiểm tra khả năng phát hiện. Chỉ scan GET/HEAD; stored XSS cần POST chưa được kiểm tra.'
                  : 'Intentionally vulnerable detection lab. GET/HEAD scans only; stored XSS requiring POST is untested.'}</p>}
              </div>

              <div className="col-span-2 space-y-1.5 rounded border border-slate-800 bg-slate-900/60 p-2.5">
                <div className="flex items-center justify-between">
                  <label htmlFor="target-origin" className="text-[11px] font-medium text-slate-300 block">{t.targetOrigin}</label>
                  {!disposableTarget && <div className="flex items-center space-x-1.5">
                    <button
                      type="button"
                      onClick={() => { setTarget('lab-ecommerce'); setTargetOrigin('http://10.0.0.2:8080'); }}
                      className={`text-[10px] px-2 py-0.5 rounded border transition-colors cursor-pointer ${
                        targetOrigin === 'http://10.0.0.2:8080'
                          ? 'border-emerald-600 bg-emerald-950/60 text-emerald-300 font-medium'
                          : 'border-slate-700 bg-slate-800 text-slate-400 hover:text-slate-200'
                      }`}
                    >
                      GNS3 (10.0.0.2:8080)
                    </button>
                    <button
                      type="button"
                      onClick={() => { setTarget('lab-ecommerce'); setTargetOrigin('http://127.0.0.1:18088'); }}
                      className={`text-[10px] px-2 py-0.5 rounded border transition-colors cursor-pointer ${
                        targetOrigin === 'http://127.0.0.1:18088'
                          ? 'border-blue-600 bg-blue-950/60 text-blue-300 font-medium'
                          : 'border-slate-700 bg-slate-800 text-slate-400 hover:text-slate-200'
                      }`}
                    >
                      Docker Gateway (127.0.0.1:18088)
                    </button>
                  </div>}
                </div>
                <input
                  id="target-origin"
                  type="text"
                  value={targetOrigin}
                  onChange={(e) => setTargetOrigin(e.target.value)}
                  placeholder="http://10.0.0.2:8080"
                  className="w-full bg-slate-950 border border-slate-800 rounded px-2.5 py-1.5 text-slate-200 font-mono text-xs focus:outline-hidden focus:border-blue-500"
                />
                <p className="text-[10px] text-slate-400">{t.targetOriginDesc}</p>
                <p className="text-[10px] text-slate-400">{lang === 'vi'
                  ? 'A/B dùng cổng loopback 18085/18086 với container riêng; nếu cổng đang bị chiếm, phiên sẽ báo lỗi. ShopLab hỗ trợ hai địa chỉ Docker/GNS3 ở trên.'
                  : 'A/B use loopback ports 18085/18086 with disposable containers; an occupied port stops the run with an error. ShopLab supports the Docker/GNS3 addresses above.'}</p>
              </div>

              <div>
                <label htmlFor="max-decisions" className="text-[11px] font-medium text-slate-400 block mb-1">{t.maxDecisionsLimit}</label>
                <input
                  type="number"
                  id="max-decisions"
                  disabled={executionScope === 'workflow'}
                  min={1}
                  max={100}
                  required
                  value={maxDecisions}
                  onChange={(e) => setMaxDecisions(Number(e.target.value))}
                  className="w-full bg-slate-900 border border-slate-800 rounded px-2.5 py-1.5 text-slate-200 font-mono text-xs focus:outline-hidden focus:border-blue-500"
                />
              </div>

              <label className="text-[11px] text-slate-400">{lang === 'vi' ? 'Giới hạn yêu cầu HTTP' : 'HTTP request budget'}
                <input type="number" min={executionScope === 'workflow' ? 200 : 1} max={500} required value={maxRequests} onChange={e => setMaxRequests(Number(e.target.value))} className="w-full rounded border border-slate-800 bg-slate-900 px-2.5 py-1.5 text-slate-200" />
              </label>
              <label className="text-[11px] text-slate-400">{lang === 'vi' ? 'Giới hạn trang khám phá' : 'Discovery page budget'}
                <input type="number" min={1} max={100} required disabled={executionScope === 'workflow'} value={maxPages} onChange={e => setMaxPages(Number(e.target.value))} className="w-full rounded border border-slate-800 bg-slate-900 px-2.5 py-1.5 text-slate-200" />
              </label>
              {executionScope === 'scan' && mode !== 'deny-demo' && !previewOnePage && <div className="col-span-2 space-y-2">
                <button type="button" onClick={() => {
                  setApproveActiveVerification(true);
                  setZapMode('zap-active');
                  setUseNuclei(true);
                  setMaxRequests(Math.max(500, maxRequests));
                }} className="rounded border border-blue-700 bg-blue-950/40 px-3 py-2 text-xs text-blue-200 hover:bg-blue-900/40">
                  {lang === 'vi' ? 'Phê duyệt và chọn Active + ZAP + Nuclei' : 'Approve and select Active + ZAP + Nuclei'}
                </button>
                <p className="text-[11px] text-slate-400">{lang === 'vi'
                  ? 'Chọn gói pentest lab với ngân sách 500 HTTP; xem lại bên dưới rồi bắt đầu phiên. Không có kết quả phát hiện vẫn có thể là chưa kiểm tra hoặc thiếu bằng chứng.'
                  : 'Select the lab pentest preset with a 500-request budget; review the settings below before launching. Zero findings can still mean untested inputs or insufficient evidence.'}</p>
              </div>}
              {executionScope === 'scan' && <label className="col-span-2 flex items-start gap-2 rounded border border-amber-900 bg-amber-950/20 p-2 text-xs text-amber-200">
                <input type="checkbox" checked={approveActiveVerification && !previewOnePage} disabled={previewOnePage} onChange={e => setApproveActiveVerification(e.target.checked)} />
                {lang === 'vi' ? 'Phê duyệt kiểm tra chủ động có giới hạn trong lab: SQLi, XSS, path traversal. Yêu cầu kiểm tra tới ứng dụng chỉ dùng GET/HEAD; phép thử form cần POST sẽ bị từ chối và báo chưa kiểm tra.' : 'Approve bounded active lab checks: SQLi, XSS and path traversal. Application checks use GET/HEAD only; POST-based form checks are refused and reported as untested.'}
              </label>}

              {executionScope === 'scan' && <fieldset disabled={!approveActiveVerification || previewOnePage || mode === 'deny-demo'} className="col-span-2 space-y-2 rounded border border-slate-700 p-3 disabled:opacity-50">
                <legend className="px-1 text-xs text-slate-200">{lang === 'vi' ? 'Scanner trong lab' : 'Lab scanners'}</legend>
                <label className="block text-xs text-slate-300">OWASP ZAP
                  <select aria-label="OWASP ZAP" value={zapMode} onChange={e => setZapMode(e.target.value as typeof zapMode)} className="ml-2 rounded bg-slate-900 p-1">
                    <option value="">{lang === 'vi' ? 'Không chạy' : 'Not selected'}</option>
                    <option value="zap-passive">Passive</option>
                    <option value="zap-active">Active: SQLi / XSS</option>
                  </select>
                </label>
                <label className="flex items-center gap-2 text-xs text-slate-300">
                  <input type="checkbox" checked={useNuclei} onChange={e => setUseNuclei(e.target.checked)} />
                  Nuclei: SQL error / lab sentinel
                </label>
                <p className="text-[11px] text-slate-400">{lang === 'vi'
                  ? 'Chỉ GET/HEAD đã khám phá, dùng chung ngân sách HTTP. Không kiểm tra đăng nhập, POST hoặc logic nghiệp vụ. Kết quả cần xác minh thêm.'
                  : 'Observed GET/HEAD only, sharing the HTTP budget. No login, POST or business-logic testing. Findings require verification.'}</p>
              </fieldset>}
              {executionScope === 'workflow' && <label className="col-span-2 flex items-start gap-2 rounded border border-amber-700 p-3 text-xs text-amber-200">
                <input type="checkbox" required checked={approveWorkflow}
                  onChange={e => { setApproveWorkflow(e.target.checked); if (e.target.checked) setMaxRequests(Math.max(200, maxRequests)); }} />
                {lang === 'vi' ? 'Cho phép workflow đăng nhập và POST trong lab cô lập: tạo tài khoản, giỏ hàng, đơn mô phỏng; kiểm tra quyền và CSRF. Docker giữ lại bản sao volume; GNS3 dùng snapshot và restore. Lab có thể tạm gián đoạn. Workflow cố định, không do LLM lập kế hoạch.' : 'Approve login and POST in the isolated lab: disposable accounts, cart, simulated checkout, role and CSRF checks. Docker retains a volume copy; GNS3 uses snapshot and restore. The lab may be briefly unavailable. The workflow is fixed, not LLM-planned.'}
              </label>}
              {executionScope === 'scan' && <div className="space-y-2 pt-1">
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
              </div>}
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
