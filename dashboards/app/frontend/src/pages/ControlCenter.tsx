import React, { useState, useCallback } from 'react';
import { AlertCircle, RefreshCw, ServerCrash } from 'lucide-react';
import { apiClient, API_BASE_URL } from '../api/client';
import type { AgentEvent, PreflightResponse, StartRunRequest } from '../api/types';
import { useSystemStatus } from '../hooks/useSystemStatus';
import { useEventStream } from '../hooks/useEventStream';

import { displayValue, displayNotification } from '../i18n/displayValue';
import { Header } from '../components/layout/Header';
import { RangeCard } from '../components/cards/RangeCard';
import { AgentCard } from '../components/cards/AgentCard';
import { SafetyCard } from '../components/cards/SafetyCard';
import { ExecutorCard } from '../components/cards/ExecutorCard';
import { EvidenceCard } from '../components/cards/EvidenceCard';
import { Pipeline } from '../components/pipeline/Pipeline';
import { CurrentActivity } from '../components/activity/CurrentActivity';
import { EventFeed } from '../components/events/EventFeed';
import { ResearchBoundary } from '../components/boundary/ResearchBoundary';
import { ControlBar } from '../components/controls/ControlBar';
import { PreflightModal } from '../components/controls/PreflightModal';
import { StartRunModal } from '../components/controls/StartRunModal';
import { EvidenceInspectorModal } from '../components/evidence/EvidenceInspectorModal';
import { ProposalReviewCard } from '../components/controls/ProposalReviewCard';
import { PresentationHero } from '../components/presentation/PresentationHero';
import { PresentationTimeline, PresentationResults } from '../components/presentation/PresentationSummary';
import { useLanguage } from '../i18n/LanguageContext';

export interface ControlCenterProps {
  activeTab?: 'overview' | 'runs' | 'run-detail' | 'compare' | 'research';
  onNavigateTab?: (tab: 'overview' | 'runs' | 'compare' | 'research') => void;
}

export const ControlCenter: React.FC<ControlCenterProps> = ({
  activeTab = 'overview',
  onNavigateTab,
}) => {
  const { t, lang } = useLanguage();
  const { status, isLoading, error, refetch, updateFromEvent } = useSystemStatus();

  // Modal and Action states
  const [isEvidenceModalOpen, setIsEvidenceModalOpen] = useState(false);

  // Handle incoming events from SSE stream
  const handleIncomingEvent = useCallback(
    (ev: AgentEvent) => {
      updateFromEvent(ev);
    },
    [updateFromEvent]
  );

  const {
    events,
    latestEvent,
    connectionStatus,
    clearEvents,
    reconnect,
  } = useEventStream({
    runId: status?.run.run_id ?? undefined,
    onEvent: handleIncomingEvent,
  });

  // Modal and Action states
  const [isPreflightOpen, setIsPreflightOpen] = useState(false);
  const [preflightResult, setPreflightResult] = useState<PreflightResponse | null>(null);
  const [isPreflightLoading, setIsPreflightLoading] = useState(false);

  const [isStartRunOpen, setIsStartRunOpen] = useState(false);
  const [isStartingRun, setIsStartingRun] = useState(false);

  const [isLabStarting, setIsLabStarting] = useState(false);
  const [isLabStopping, setIsLabStopping] = useState(false);
  const [isRunPausing, setIsRunPausing] = useState(false);
  const [isRunResuming, setIsRunResuming] = useState(false);
  const [isRunStopping, setIsRunStopping] = useState(false);
  const [isEmergencyStopping, setIsEmergencyStopping] = useState(false);

  const [notification, setNotification] = useState<{
    type: 'success' | 'error' | 'info';
    message: string;
  } | null>(null);

  const notify = (type: 'success' | 'error' | 'info', message: string) => {
    setNotification({ type, message });
    setTimeout(() => {
      setNotification((curr) => (curr?.message === message ? null : curr));
    }, 5000);
  };

  // Action handlers
  const handleRunPreflight = async () => {
    setIsPreflightOpen(true);
    setIsPreflightLoading(true);
    try {
      const res = await apiClient.runPreflight();
      setPreflightResult(res);
      await refetch();
    } catch (err) {
      notify('error', `Preflight execution failed: ${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setIsPreflightLoading(false);
    }
  };

  const handleStartLab = async () => {
    setIsLabStarting(true);
    try {
      const res = await apiClient.startRange();
      notify('info', `Range Start initiated: ${res.status}`);
      await refetch();
    } catch (err) {
      notify('error', `Failed to start lab: ${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setIsLabStarting(false);
    }
  };

  const handleStopLab = async () => {
    setIsLabStopping(true);
    try {
      const res = await apiClient.stopRange();
      notify('info', `Range Stop response: ${res.message || res.status}`);
      await refetch();
    } catch (err) {
      notify('error', `Failed to stop lab: ${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setIsLabStopping(false);
    }
  };

  const handleLaunchRun = async (req: StartRunRequest) => {
    setIsStartingRun(true);
    try {
      const res = await apiClient.startRun(req);
      if (res.success) {
        notify('success', `Autonomous run started: ${res.run_id}`);
        await refetch();
      } else {
        notify('error', res.message || 'Run startup rejected');
      }
    } catch (err) {
      notify('error', `Failed to start run: ${err instanceof Error ? err.message : String(err)}`);
      throw err;
    } finally {
      setIsStartingRun(false);
    }
  };

  const [presentationMode, setPresentationMode] = useState<boolean>(true);

  const handleLaunchPreset = async (preset: 'safe-recon' | 'deny-demo' | 'assisted') => {
    let req: StartRunRequest;
    if (preset === 'safe-recon') {
      req = {
        mode: 'autonomous',
        planner: 'rule',
        control_mode: 'AUTONOMOUS',
        allow_fallback: true,
        target: 'lab-ecommerce',
        scenario: 'SCN-001',
        max_decisions: 10,
      };
    } else if (preset === 'deny-demo') {
      req = {
        mode: 'deny-demo',
        planner: 'rule',
        control_mode: 'AUTONOMOUS',
        allow_fallback: true,
        target: 'lab-ecommerce',
        scenario: 'SCN-002',
        max_decisions: 5,
      };
    } else {
      req = {
        mode: 'presentation',
        planner: 'rule',
        control_mode: 'ASSISTED',
        allow_fallback: true,
        target: 'lab-ecommerce',
        scenario: 'SCN-001',
        max_decisions: 10,
      };
    }
    try {
      await handleLaunchRun(req);
    } catch {
      // notification handled in handleLaunchRun
    }
  };

  const handlePauseRun = async () => {
    if (!status?.run.run_id) return;
    setIsRunPausing(true);
    try {
      const res = await apiClient.pauseRun(status.run.run_id);
      notify('info', res.message || 'Pause requested');
      await refetch();
    } catch (err) {
      notify('error', `Failed to pause run: ${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setIsRunPausing(false);
    }
  };

  const handleResumeRun = async () => {
    if (!status?.run.run_id) return;
    setIsRunResuming(true);
    try {
      const res = await apiClient.resumeRun(status.run.run_id);
      notify('info', res.message || 'Resume requested');
      await refetch();
    } catch (err) {
      notify('error', `Failed to resume run: ${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setIsRunResuming(false);
    }
  };

  const handleApproveProposal = async (runId: string, proposalId: string) => {
    try {
      const res = await apiClient.approveProposal(runId, proposalId);
      notify('success', res.message || 'Proposal approved by operator');
      await refetch();
    } catch (err) {
      notify('error', `Approval failed: ${err instanceof Error ? err.message : String(err)}`);
      throw err;
    }
  };

  const handleRejectProposal = async (runId: string, proposalId: string, reason?: string) => {
    try {
      const res = await apiClient.rejectProposal(runId, proposalId, reason);
      notify('info', res.message || 'Proposal rejected by operator');
      await refetch();
    } catch (err) {
      notify('error', `Rejection failed: ${err instanceof Error ? err.message : String(err)}`);
      throw err;
    }
  };

  const handleStopRun = async () => {
    if (!status?.run.run_id) return;
    setIsRunStopping(true);
    try {
      const res = await apiClient.stopRun(status.run.run_id);
      notify('info', res.message || 'Stop requested');
      await refetch();
    } catch (err) {
      notify('error', `Failed to stop run: ${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setIsRunStopping(false);
    }
  };

  const handleEmergencyStop = async () => {
    setIsEmergencyStopping(true);
    try {
      const res = await apiClient.emergencyStop();
      notify('error', `EMERGENCY KILL SWITCH ACTIVATED: ${res.message}`);
      await refetch();
    } catch (err) {
      notify('error', `Emergency stop error: ${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setIsEmergencyStopping(false);
    }
  };

  // Backend Offline UI Handling (Never crash on backend disconnect)
  if (!status && !isLoading && error) {
    return (
      <div className="min-h-screen bg-[#0b0f17] text-slate-200 flex flex-col items-center justify-center p-6">
        <div className="bg-[#111724] border border-rose-800/80 rounded-xl p-8 max-w-md w-full shadow-2xl text-center space-y-4">
          <div className="p-3 bg-rose-950/60 rounded-full w-14 h-14 mx-auto flex items-center justify-center text-rose-400 border border-rose-800/60">
            <ServerCrash className="w-8 h-8" />
          </div>
          <h2 className="text-lg font-bold text-slate-100 uppercase tracking-wide">
            {t.controlApiOffline}
          </h2>
          <p className="text-xs text-slate-400 font-mono leading-relaxed">
            {t.controlApiOfflineDesc}
            <br />
            <span className="text-rose-400 font-semibold">{API_BASE_URL}</span>
          </p>
          <p className="text-[11px] text-slate-500">
            {lang === 'vi' ? 'Máy chủ chưa phản hồi. Kiểm tra dịch vụ rồi thử kết nối lại.' : 'The server is not responding. Check the service, then retry.'}

          </p>
          <button
            onClick={() => refetch()}
            aria-label={lang === 'vi' ? 'Thử kết nối lại' : 'Retry Connection'}
            className="w-full mt-2 px-4 py-2 rounded text-xs font-semibold bg-blue-600 hover:bg-blue-500 text-white transition-colors flex items-center justify-center space-x-2 cursor-pointer"
          >
            <RefreshCw className="w-4 h-4" />
            <span>{t.retry}</span>
          </button>
        </div>
      </div>
    );
  }

  // Loading skeleton while initial fetch completes
  if (!status && isLoading) {
    return (
      <div className="min-h-screen bg-[#0b0f17] text-slate-200 flex items-center justify-center">
        <div className="flex flex-col items-center space-y-3 font-mono text-xs text-slate-400">
          <RefreshCw className="w-6 h-6 animate-spin text-blue-500" />
          <span>{lang === 'vi' ? 'Đang tải dữ liệu…' : 'Loading research workspace…'}</span>
        </div>
      </div>
    );
  }

  if (!status) return null;

  return (
    <div className={presentationMode ? 'cc-presentation min-h-screen flex flex-col font-sans' : 'min-h-screen bg-[#0b0f17] text-slate-100 flex flex-col font-sans'}>
      {/* Top Header */}
      <Header
        system={status}
        sseStatus={connectionStatus}
        activeTab={activeTab}
        onNavigate={onNavigateTab}
        presentationMode={presentationMode}
        onTogglePresentationMode={() => setPresentationMode((prev) => !prev)}
      />

      {/* Main Dashboard Body */}
      <main className={presentationMode ? 'cc-main flex-1' : 'flex-1 p-4 lg:p-5 max-w-[1720px] w-full mx-auto space-y-4'}>
        {/* Floating Notification Banner if active */}
        {notification && (
          <div
            className={`p-3 rounded-lg border text-xs flex items-center justify-between font-mono animate-in fade-in duration-150 ${
              notification.type === 'error'
                ? 'bg-rose-950/80 border-rose-800 text-rose-300'
                : notification.type === 'success'
                ? 'bg-emerald-950/80 border-emerald-800 text-emerald-300'
                : 'bg-blue-950/80 border-blue-800 text-blue-300'
            }`}
          >
            <div className="flex items-center space-x-2">
              <AlertCircle className="w-4 h-4 shrink-0" />
              <span title={notification.message}>{displayNotification(notification.message, lang)}</span>
            </div>
            <button
              onClick={() => setNotification(null)}
              className="text-slate-400 hover:text-slate-200 text-xs px-2"
            >
              {lang === 'vi' ? 'Đóng thông báo' : 'Dismiss'}
            </button>
          </div>
        )}

        {error && <p role="alert" className="cc-stale">{lang === 'vi' ? 'Không cập nhật được trạng thái. Đang hiển thị dữ liệu đã nhận trước đó.' : 'Status refresh failed. Showing previously received data.'}</p>}

        {/* Presentation view only summarizes received data. */}
        {presentationMode && (
          <>
            <div className="cc-session-strip">
              <span>{lang === 'vi' ? 'Phiên hiện tại' : 'Current session'} · <span className="cc-code">{status.run.run_id || (lang === 'vi' ? 'Chưa bắt đầu' : 'Not started')}</span></span>
              <span>{lang === 'vi' ? 'Môi trường' : 'Lab'}: {displayValue(status.range.status, lang)}</span>
            </div>
            {status.range.status !== 'HEALTHY' && <details className="cc-environment-note"><summary>{displayValue(status.range.status, lang)}</summary><p>{status.range.message}</p></details>}
            <PresentationHero
              system={status}
              latestEvent={latestEvent}
              onViewHistory={onNavigateTab ? () => onNavigateTab('runs') : undefined}
            />
            <div className="cc-overview-columns">
              <PresentationTimeline events={events} runId={status.run.run_id} connectionStatus={connectionStatus} onReconnect={reconnect} />
              <PresentationResults system={status} onInspect={() => setIsEvidenceModalOpen(true)} />
            </div>
          </>
        )}

        {status.agent.pending_proposal && status.run.run_id && (
          <section aria-label={lang === 'vi' ? 'Xem xét đề xuất' : 'Proposal Approval Review'}>
            <ProposalReviewCard proposal={status.agent.pending_proposal} runId={status.run.run_id}
              onApprove={handleApproveProposal} onReject={handleRejectProposal} />
          </section>
        )}

        <details className={presentationMode ? 'cc-technical' : 'space-y-4'} open={presentationMode ? undefined : true}>
          <summary className={presentationMode ? 'cc-technical-toggle' : 'hidden'}>{lang === 'vi' ? 'Chi tiết kỹ thuật' : 'Technical details'}</summary>
          <div className={presentationMode ? 'cc-technical-content space-y-4' : 'space-y-4'}>
          {presentationMode && <div className="flex flex-wrap items-center gap-2 text-slate-200 text-sm">
            <span>{t.quickScenarios}</span>
            {(['safe-recon', 'deny-demo', 'assisted'] as const).map((preset, index) => <button key={preset} type="button"
              className="px-3 py-2 rounded border border-slate-600 hover:bg-slate-800 disabled:opacity-40"
              disabled={['RUNNING', 'STARTING', 'WAITING_FOR_APPROVAL'].includes(status.run.state)}
              onClick={() => handleLaunchPreset(preset)}>{[t.scenarioSafeRecon, t.scenarioSafetyDeny, t.scenarioAssisted][index]}</button>)}
          </div>}
        {/* Row 1: The 5 Core Operational Cards */}
        <section aria-label={lang === 'vi' ? 'Các thành phần hệ thống' : 'System Components Overview'} className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-5 gap-3.5">
          <RangeCard range={status.range} />
          <AgentCard agent={status.agent} run={status.run} />
          <SafetyCard safety={status.safety} system={status} />
          <ExecutorCard system={status} />
          <EvidenceCard
            evidence={status.evidence}
            onInspect={() => setIsEvidenceModalOpen(true)}
          />
        </section>

        {/* Row 2: Closed-Loop Lifecycle Pipeline */}
        <section aria-label={lang === 'vi' ? 'Tiến trình xử lý' : 'Autonomous Pipeline Progress'}>
          <Pipeline pipeline={status.pipeline} />
        </section>

        {/* Row 3: Current Activity (Left) + Live Event Stream (Right) */}
        <section aria-label={lang === 'vi' ? 'Hoạt động và sự kiện' : 'Live Activity and Telemetry'} className="grid grid-cols-1 lg:grid-cols-12 gap-3.5">
          <div className="lg:col-span-5">
            <CurrentActivity system={status} latestEvent={latestEvent} />
          </div>
          <div className="lg:col-span-7">
            <EventFeed
              events={events}
              connectionStatus={connectionStatus}
              onClear={clearEvents}
              onReconnect={reconnect}
            />
          </div>
        </section>

        {/* Row 4: Research & Safety Boundary Invariants */}
        <section aria-label={lang === 'vi' ? 'Phạm vi nghiên cứu và an toàn' : 'Research and Safety Boundary'}>
          <ResearchBoundary />
        </section>
          </div>
        </details>

        {/* Row 5: Persistent Control Action Bar */}
        <section aria-label={lang === 'vi' ? 'Điều khiển phiên' : 'Operational Controls'}>
          <ControlBar
            system={status}
            onRunPreflight={handleRunPreflight}
            onStartLab={handleStartLab}
            onStopLab={handleStopLab}
            onOpenStartRun={() => setIsStartRunOpen(true)}
            onPauseRun={handlePauseRun}
            onResumeRun={handleResumeRun}
            onStopRun={handleStopRun}
            onEmergencyStop={handleEmergencyStop}
            isLabStarting={isLabStarting}
            isLabStopping={isLabStopping}
            isRunPausing={isRunPausing}
            isRunResuming={isRunResuming}
            isRunStopping={isRunStopping}
            isEmergencyStopping={isEmergencyStopping}
          />
        </section>
      </main>

      {/* Preflight Modal */}
      <PreflightModal
        isOpen={isPreflightOpen}
        onClose={() => setIsPreflightOpen(false)}
        result={preflightResult}
        isLoading={isPreflightLoading}
        onRerun={handleRunPreflight}
      />

      {/* Start Run Modal */}
      <StartRunModal
        isOpen={isStartRunOpen}
        onClose={() => setIsStartRunOpen(false)}
        onSubmit={handleLaunchRun}
        isSubmitting={isStartingRun}
      />

      {/* Evidence & Findings Inspector Modal */}
      <EvidenceInspectorModal
        isOpen={isEvidenceModalOpen}
        onClose={() => setIsEvidenceModalOpen(false)}
        runId={status.run.run_id}
      />
    </div>
  );
};
