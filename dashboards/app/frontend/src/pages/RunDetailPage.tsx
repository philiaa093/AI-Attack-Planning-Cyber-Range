import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  Play,
  Pause,
  RotateCcw,
  SkipBack,
  SkipForward,
  ArrowLeft,
  Lock,
} from 'lucide-react';
import { apiClient } from '../api/client';
import { recordedValue } from '../api/recordedValue';
import type {
  RunHistoryItem,
  TimelineEventItem,
} from '../api/types';
import { useLanguage } from '../i18n/LanguageContext';
import { historyLabel } from '../i18n/historyLabels';
import { displayTool, displayValue } from '../i18n/displayValue';

interface RunDetailPageProps {
  runId: string;
  onBack: () => void;
  onCompareWith?: (runId: string) => void;
}

const PIPELINE_STEPS = [
  'PREFLIGHT',
  'RANGE',
  'OBSERVE',
  'STATE',
  'PLAN',
  'SAFETY',
  'EXECUTE',
  'EVIDENCE',
  'VERIFY',
  'COMPLETE',
];

const displayedVerification = (event: TimelineEventItem) => {
  const classification = String(event.payload.classification ?? 'INCONCLUSIVE');
  const input = String(event.payload.parameter_name ?? '').toLowerCase();
  const fileLike = ['file', 'path', 'template', 'document', 'download', 'folder', 'dir', 'include']
    .some(name => input.includes(name));
  return classification === 'VERIFIED_IN_LAB' && event.payload.family === 'PATH_TRAVERSAL' && !fileLike
    ? 'INCONCLUSIVE'
    : classification;
};

export const RunDetailPage: React.FC<RunDetailPageProps> = ({
  runId,
  onBack,
  onCompareWith,
}) => {
  const { lang, t } = useLanguage();
  const h = (value: string) => historyLabel(lang, value);
  const [run, setRun] = useState<RunHistoryItem | null>(null);
  const [timeline, setTimeline] = useState<TimelineEventItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Replay State
  const [currentStepIndex, setCurrentStepIndex] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const [speed, setSpeed] = useState<1 | 2 | 4>(1);
  const playTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const fetchRunData = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const [runData, timelineData] = await Promise.all([
        apiClient.getRunDetail(runId),
        apiClient.getRunTimeline(runId),
      ]);
      setRun(runData);
      setTimeline(timelineData.events);
      setCurrentStepIndex(0);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setIsLoading(false);
    }
  }, [runId]);

  useEffect(() => {
    fetchRunData();
  }, [fetchRunData]);

  // Player ticker loop
  useEffect(() => {
    if (isPlaying && timeline.length > 0) {
      const intervalMs = Math.floor(1000 / speed);
      playTimerRef.current = setTimeout(() => {
        setCurrentStepIndex((prev) => {
          if (prev >= timeline.length - 1) {
            setIsPlaying(false);
            return prev;
          }
          return prev + 1;
        });
      }, intervalMs);
    }
    return () => {
      if (playTimerRef.current) {
        clearTimeout(playTimerRef.current);
      }
    };
  }, [isPlaying, currentStepIndex, timeline.length, speed]);

  const handlePlayPause = () => {
    if (currentStepIndex >= timeline.length - 1) {
      setCurrentStepIndex(0);
      setIsPlaying(true);
    } else {
      setIsPlaying((prev) => !prev);
    }
  };

  const handleStepPrev = () => {
    setIsPlaying(false);
    setCurrentStepIndex((prev) => Math.max(0, prev - 1));
  };

  const handleStepNext = () => {
    setIsPlaying(false);
    setCurrentStepIndex((prev) => Math.min(timeline.length - 1, prev + 1));
  };

  const handleReset = () => {
    setIsPlaying(false);
    setCurrentStepIndex(0);
  };

  const currentEvent: TimelineEventItem | undefined = timeline[currentStepIndex];

  // Derive active pipeline stage based on current event type
  const getActivePipelineStage = (ev?: TimelineEventItem): string => {
    if (!ev) return 'PREFLIGHT';
    const t = ev.type.toUpperCase();
    if (t.includes('PREFLIGHT') || t.includes('INIT')) return 'PREFLIGHT';
    if (t.includes('PROPOSE') || t.includes('PLAN')) return 'PLAN';
    if (t.includes('SAFETY') || t.includes('APPROVAL') || t.includes('DENIED') || t.includes('PERMIT')) return 'SAFETY';
    if (t.includes('DISPATCH') || t.includes('EXECUTE')) return 'EXECUTE';
    if (t.includes('OBSERV') || t.includes('RECEIVE')) return 'OBSERVE';
    if (t.includes('STATE')) return 'STATE';
    if (t.includes('RECORD') || t.includes('EVIDENCE_RECORD')) return 'EVIDENCE';
    if (t.includes('VERIF')) return 'VERIFY';
    if (t.includes('COMPLET') || t.includes('STOP') || t.includes('FAIL')) return 'COMPLETE';
    return 'OBSERVE';
  };

  const activeStage = getActivePipelineStage(currentEvent);

  if (isLoading) {
    return (
      <div className="flex-1 flex items-center justify-center bg-[#0a0e17] text-slate-400 font-mono text-sm">
        {h('Reconstructing execution timeline from evidence...')}
      </div>
    );
  }

  if (error || !run) {
    return (
      <div className="flex-1 p-8 bg-[#0a0e17] text-slate-100">
        <button
          type="button"
          onClick={onBack}
          className="flex flex-wrap items-center gap-1.5 text-sm text-blue-400 hover:text-blue-300 font-mono mb-4"
        >
          <ArrowLeft className="w-4 h-4" />
          <span>{h('Back to Runs')}</span>
        </button>
        <div className="p-4 rounded bg-rose-950/80 border border-rose-800 text-rose-300 text-sm">
          {h('Failed to load run replay:')} {error ? h(error) : h('Run not found')}
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 min-w-0 overflow-y-auto p-4 sm:p-6 space-y-6 text-sm leading-relaxed bg-[#0a0e17] text-slate-100">
      {/* Top Breadcrumb & Metadata strip */}
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-800/80 pb-4">
        <div className="flex flex-wrap items-center gap-3">
          <button
            type="button"
            onClick={onBack}
            className="flex flex-wrap items-center gap-1 px-2.5 py-1.5 rounded bg-slate-900 border border-slate-800 hover:bg-slate-800 text-sm text-slate-300 transition-all"
          >
            <ArrowLeft className="w-3.5 h-3.5" />
            <span>{h('Runs List')}</span>
          </button>
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-lg font-bold font-mono break-all text-slate-100">{run.run_id}</h2>
              <span className="px-2 py-0.5 rounded text-sm font-mono font-semibold bg-blue-950/80 border border-blue-800/80 text-blue-300">
                {h('PLANNER')}: {h(run.planner_actual)}
              </span>
              <span className="px-2 py-0.5 rounded text-sm font-mono font-semibold bg-slate-900 border border-slate-800 text-slate-300">
                {h(run.control_mode)}
              </span>
            </div>
            <p className="text-sm font-mono text-slate-400 mt-0.5">
              {h('Target:')} {run.target_id === 'UNKNOWN' ? h('UNKNOWN') : run.target_id} • {h('Scenario:')} {run.scenario === 'UNKNOWN' ? h('UNKNOWN') : run.scenario} • {h('Decisions:')} {recordedValue(run.iterations)} • {h('Dispatches:')} {recordedValue(run.network_dispatches)}
            </p>
          </div>
        </div>

        {onCompareWith && (
          <button
            type="button"
            onClick={() => onCompareWith(run.run_id)}
            className="flex flex-wrap items-center gap-1.5 px-3 py-1.5 rounded bg-blue-600 hover:bg-blue-500 text-sm font-semibold text-white shadow transition-all"
          >
            <span>{h('Compare This Run')}</span>
          </button>
        )}
      </div>

      {/* Mandatory Historical Replay Banner */}
      <div className="bg-amber-950/40 border border-amber-600/60 rounded-lg p-3 flex flex-wrap items-center gap-3 text-amber-200">
        <div className="p-2 rounded bg-amber-900/50 border border-amber-700/60 shrink-0 text-amber-400">
          <Lock className="w-5 h-5" />
        </div>
        <div className="text-sm">
          <div className="font-bold text-amber-300 font-mono flex flex-wrap items-center gap-2">
            <span>{(lang === 'vi' ? h('HISTORICAL REPLAY — NO LIVE EXECUTION') : t('replayBannerTitle'))}</span>
            <span className="text-sm bg-amber-950/80 border border-amber-700 px-1.5 py-0.2 rounded font-semibold">
              {(lang === 'vi' ? h('READ-ONLY') : t('replayBannerReadOnly'))}
            </span>
          </div>
          <p className="text-amber-200/80 text-sm mt-0.5">
            {lang === 'vi'
              ? 'Trình phát này duyệt trực quan các trạng thái thực thi lịch sử dựa trên dữ liệu chứng cứ bất biến. Không có gói tin HTTP hoặc lệnh shell trực tiếp nào được phát ra.'
              : 'This player visually scrubs through historical execution states strictly derived from canonical evidence. Zero live HTTP packets or shell calls are emitted during replay.'}
          </p>
        </div>
      </div>

      {/* Interactive Replay Player Bar */}
      {timeline.some(event => event.type === 'SCANNER_COMPLETED') && (
        <section className="rounded-lg border border-slate-700 bg-[#111724] p-4 space-y-2" aria-label="Scanner results">
          <h3 className="text-sm font-semibold text-slate-200">{lang === 'vi' ? 'Kết quả scanner' : 'Scanner results'}</h3>
          {timeline.filter(event => event.type === 'SCANNER_COMPLETED').map((event, index) => (
            <p key={index} className="break-all text-xs text-slate-300">
              {String(event.payload.tool)}: {displayValue(String(event.payload.status), lang)}
              {' · '}{String(event.payload.coverage ?? '')}
              {event.payload.candidate_count !== undefined ? ` · ${String(event.payload.candidate_count)} candidates` : ''}
              {event.payload.reason ? ` · ${String(event.payload.reason)}` : ''}
            </p>
          ))}
          <p className="text-xs text-amber-200">{lang === 'vi' ? 'Candidate chưa phải lỗ hổng đã xác minh. Không có kết quả không chứng minh website an toàn.' : 'Candidates are unconfirmed. No findings do not establish that the website is safe.'}</p>
        </section>
      )}
      <div className="bg-[#111724] border border-slate-800 rounded-lg p-4 space-y-4 shadow-xl">
        <div className="flex flex-wrap items-center justify-between gap-4">
          {/* Controls: Play/Pause, Step Prev/Next, Reset */}
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={handleReset}
              title={h('Reset to step 1')}
              aria-label={h('Reset to step 1')}
              className="p-2 rounded bg-slate-900 border border-slate-800 hover:bg-slate-800 text-slate-300 transition-all"
            >
              <RotateCcw className="w-4 h-4" />
            </button>
            <button
              type="button"
              onClick={handleStepPrev}
              disabled={currentStepIndex === 0}
              title={h('Previous Step')}
              aria-label={h('Previous Step')}
              className="p-2 rounded bg-slate-900 border border-slate-800 hover:bg-slate-800 text-slate-300 disabled:opacity-40 transition-all"
            >
              <SkipBack className="w-4 h-4" />
            </button>
            <button
              type="button"
              onClick={handlePlayPause}
              aria-label={h(isPlaying ? 'Pause' : 'Play')}
              className="flex flex-wrap items-center gap-1.5 px-4 py-2 rounded bg-blue-600 hover:bg-blue-500 text-white font-semibold text-sm shadow-md transition-all"
            >
              {isPlaying ? (
                <>
                  <Pause className="w-4 h-4" />
                  <span>{(lang === 'vi' ? h('Pause') : t('replayPause'))}</span>
                </>
              ) : (
                <>
                  <Play className="w-4 h-4" />
                  <span>{currentStepIndex >= timeline.length - 1 ? (lang === 'vi' ? h('Replay') : t('actionReplay')) : (lang === 'vi' ? h('Play') : t('replayPlay'))}</span>
                </>
              )}
            </button>
            <button
              type="button"
              onClick={handleStepNext}
              disabled={currentStepIndex >= timeline.length - 1}
              title={h('Next Step')}
              aria-label={h('Next Step')}
              className="p-2 rounded bg-slate-900 border border-slate-800 hover:bg-slate-800 text-slate-300 disabled:opacity-40 transition-all"
            >
              <SkipForward className="w-4 h-4" />
            </button>
          </div>

          {/* Speed multiplier selector */}
          <div className="flex flex-wrap items-center gap-1.5 text-sm font-mono">
            <span className="text-slate-400 text-sm font-sans">{t('replaySpeed')}:</span>
            {([1, 2, 4] as const).map((s) => (
              <button
                key={s}
                type="button"
                onClick={() => setSpeed(s)}
                className={`px-2 py-1 rounded text-sm font-mono font-medium transition-all ${
                  speed === s
                    ? 'bg-blue-600 text-white'
                    : 'bg-slate-900 border border-slate-800 text-slate-400 hover:text-slate-200'
                }`}
              >
                {s}x
              </button>
            ))}
          </div>

          {/* Step Counter Indicator */}
          <div className="font-mono text-sm text-slate-300">
            {t('replayStep')}{' '}
            <strong className="text-blue-400">{timeline.length ? currentStepIndex + 1 : 0}</strong>{' '}
            {lang === 'vi' ? '/' : 'of'} <strong>{timeline.length}</strong>
          </div>
        </div>

        {/* Scrubber slider */}
        <div className="space-y-1">
          <input
            type="range"
            aria-label={t('replayStep')}
            min={0}
            max={Math.max(0, timeline.length - 1)}
            value={currentStepIndex}
            onChange={(e) => {
              setIsPlaying(false);
              setCurrentStepIndex(Number(e.target.value));
            }}
            className="w-full h-2 bg-slate-800 rounded-lg appearance-none cursor-pointer accent-blue-500"
          />
          <div className="flex flex-wrap justify-between gap-x-4 gap-y-1 text-sm font-mono text-slate-400">
            <span>{h('Start (Event 1)')}</span>
            <span>{currentEvent?.timestamp_utc ? currentEvent.timestamp_utc.slice(11, 19) : ''}</span>
            <span>{h('Final State')} ({h('Event')} {timeline.length})</span>
          </div>
        </div>
      </div>

      {/* Dynamic Pipeline Visualization */}
      <section className="rounded-lg border border-slate-800 bg-[#111724] p-4 space-y-3">
        <h3 className="font-semibold text-slate-200">{lang === 'vi' ? 'Công cụ và kết quả kiểm tra lỗ hổng' : 'Tools and vulnerability verification results'}</h3>
        {timeline.filter(ev => ev.type === 'VERIFICATION_COMPLETED').length === 0 && <p className="text-slate-400">{lang === 'vi' ? 'Chưa ghi nhận kết quả kiểm tra chủ động. Discovery không xác nhận lỗ hổng.' : 'No active verification result recorded. Discovery does not confirm a vulnerability.'}</p>}
        {timeline.filter(ev => ev.type === 'VERIFICATION_COMPLETED').map(ev => (
          <div key={ev.event_id} className="rounded border border-slate-800 p-3 space-y-1">
            <p className="break-all text-slate-200">{displayTool(String(ev.payload.tool ?? ''), lang)} · {displayValue(String(ev.payload.family ?? 'UNKNOWN'), lang)}</p>
            <p className="break-all text-slate-400">{String(ev.payload.resource_ref ?? '')} · {String(ev.payload.parameter_name ?? '')}</p>
            <p className="text-amber-200">{displayValue(displayedVerification(ev), lang)}</p>
            {displayedVerification(ev) !== ev.payload.classification && <p className="text-xs text-amber-400">{lang === 'vi' ? 'Đã hạ mức: tham số không phải đầu vào kiểu tệp hoặc đường dẫn nên chưa chứng minh lỗ hổng vượt đường dẫn.' : 'Downgraded: the parameter is not a file/path input, so path traversal is not established.'}</p>}
            <p className="break-all font-mono text-xs text-slate-500">{String(ev.payload.result_evidence_id ?? '')}</p>
          </div>
        ))}
      </section>

      <div className="bg-[#111724] border border-slate-800 rounded-lg p-4 space-y-2">
        <h3 className="text-sm font-bold text-slate-400 font-mono">
          {h('Pipeline State at Scrubber Position')}
        </h3>
        <div className="grid grid-cols-2 sm:grid-cols-5 xl:grid-cols-10 gap-1.5">
          {PIPELINE_STEPS.map((step) => {
            const isCurrent = activeStage === step;
            return (
              <div
                key={step}
                className={`p-2 rounded text-center transition-all border ${
                  isCurrent
                    ? 'bg-blue-600/30 border-blue-500 text-blue-200 shadow-sm font-bold scale-105'
                    : 'bg-slate-900/60 border-slate-800/80 text-slate-400'
                }`}
              >
                <div className="text-sm font-mono">{h(step)}</div>
                <div className="text-sm mt-0.5">{h(isCurrent ? 'ACTIVE' : 'IDLE')}</div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Step Detail Card */}
      {currentEvent ? (
        <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
          {/* Left 2 Cols: Event Payload & Action Inspection */}
          <div className="xl:col-span-2 bg-[#111724] border border-slate-800 rounded-lg p-5 space-y-4 min-w-0 break-words">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800 pb-3">
              <div className="flex flex-wrap items-center gap-2">
                <span className="w-2.5 h-2.5 rounded-full bg-blue-400" />
                <h3 className="text-sm font-bold text-slate-100 uppercase tracking-wide">
                  {h(currentEvent.title)}
                </h3>
                <span className="px-2 py-0.5 rounded text-sm font-mono bg-slate-900 border border-slate-800 text-slate-300">
                  {h(currentEvent.type)}
                </span>
              </div>
              <span className="text-sm font-mono text-slate-400">
                {currentEvent.timestamp_utc}
              </span>
            </div>

            <p className="text-sm text-slate-300 font-sans leading-relaxed">
              {h(currentEvent.description)}
            </p>

            {/* Structured Event Payload Dump */}
            {Boolean(currentEvent.payload.tool) && <p className="break-all text-slate-200">{lang === 'vi' ? 'Công cụ ghi nhận' : 'Recorded tool'}: {displayTool(String(currentEvent.payload.tool), lang)} · {displayValue(String(currentEvent.payload.family ?? 'UNKNOWN'), lang)}</p>}
            <div className="space-y-1">
              <span className="text-sm font-mono text-slate-400 uppercase font-semibold">
                {h('Recorded Step Data:')}
              </span>
              <pre className="p-3 rounded bg-slate-950 border border-slate-800/80 text-sm font-mono text-slate-200 overflow-x-auto max-h-[280px]">
                {JSON.stringify(currentEvent.payload, null, 2)}
              </pre>
            </div>
          </div>

          {/* Right 1 Col: Run Provenance & Cumulative Metrics */}
          <div className="bg-[#111724] border border-slate-800 rounded-lg p-5 space-y-4 min-w-0 break-words">
            <h3 className="text-sm font-bold text-slate-400 font-mono border-b border-slate-800 pb-2">
              {h('Audited Provenance')}
            </h3>
            <div className="space-y-2 text-sm font-mono">
              <div className="flex flex-wrap justify-between gap-x-4 gap-y-1">
                <span className="text-slate-400">{h('Planner Mode:')}</span>
                <span className="text-cyan-300">{h(run.planner_actual)}</span>
              </div>
              <div className="flex flex-wrap justify-between gap-x-4 gap-y-1">
                <span className="text-slate-400">{h('Requested Mode:')}</span>
                <span className="text-slate-200">{h(run.planner_requested)}</span>
              </div>
              <div className="flex flex-wrap justify-between gap-x-4 gap-y-1">
                <span className="text-slate-400">{h('Verification:')}</span>
                <span className="text-amber-300">{h(run.planner_verification)}</span>
              </div>
              <div className="flex flex-wrap justify-between gap-x-4 gap-y-1">
                <span className="text-slate-400">{h('Control Mode:')}</span>
                <span className="text-indigo-300">{h(run.control_mode)}</span>
              </div>
              <div className="flex flex-wrap justify-between gap-x-4 gap-y-1">
                <span className="text-slate-400">{h('Total Iterations:')}</span>
                <span className="text-slate-200">{recordedValue(run.iterations)}</span>
              </div>
              <div className="flex flex-wrap justify-between gap-x-4 gap-y-1">
                <span className="text-slate-400">{h('Net Dispatches:')}</span>
                <span className="text-blue-300 font-bold">{recordedValue(run.network_dispatches)}</span>
              </div>
              <div className="flex flex-wrap justify-between gap-x-4 gap-y-1">
                <span className="text-slate-400">{h('Permits / Denials:')}</span>
                <span className="text-slate-200">{recordedValue(run.permits)} / {recordedValue(run.denials)}</span>
              </div>
              <div className="flex flex-wrap justify-between gap-x-4 gap-y-1">
                <span className="text-slate-400">{h('Evidence Count:')}</span>
                <span className="text-emerald-400">{run.evidence_count}</span>
              </div>
              <div className="flex flex-wrap justify-between gap-x-4 gap-y-1">
                <span className="text-slate-400">{h('Termination:')}</span>
                <span className="text-slate-300">{h(run.stop_reason || run.state)}</span>
              </div>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
};
