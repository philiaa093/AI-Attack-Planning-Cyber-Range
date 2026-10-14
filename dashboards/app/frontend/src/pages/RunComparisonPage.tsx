import React, { useState, useEffect, useCallback } from 'react';
import {
  GitCompare,
  ArrowLeftRight,
  Shield,
  Layers,
  FileSpreadsheet,
  FileCode,
  Info,
} from 'lucide-react';
import { apiClient } from '../api/client';
import { recordedValue } from '../api/recordedValue';
import type {
  RunComparisonResponse,
  RunHistoryItem,
} from '../api/types';
import { useLanguage } from '../i18n/LanguageContext';
import { historyLabel } from '../i18n/historyLabels';

interface RunComparisonPageProps {
  initialRunA?: string;
  initialRunB?: string;
  onSelectRunDetail?: (runId: string) => void;
}

export const RunComparisonPage: React.FC<RunComparisonPageProps> = ({
  initialRunA,
  initialRunB,
  onSelectRunDetail,
}) => {
  const { lang, t } = useLanguage();
  const h = (value: string) => historyLabel(lang, value);
  const [runsList, setRunsList] = useState<RunHistoryItem[]>([]);
  const [runAId, setRunAId] = useState<string>(initialRunA || '');
  const [runBId, setRunBId] = useState<string>(initialRunB || '');
  const [comparison, setComparison] = useState<RunComparisonResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Load available runs for dropdowns
  useEffect(() => {
    async function loadRuns() {
      try {
        const res = await apiClient.getRunHistory();
        setRunsList(res.runs);
        if (res.runs.length >= 2) {
          if (!runAId) setRunAId(res.runs[0].run_id);
          if (!runBId) setRunBId(res.runs[1].run_id);
        } else if (res.runs.length === 1) {
          if (!runAId) setRunAId(res.runs[0].run_id);
          if (!runBId) setRunBId(res.runs[0].run_id);
        }
      } catch (err) {
        console.error('Failed to load runs list', err);
      }
    }
    loadRuns();
  }, []);

  // Fetch comparison when both runs are chosen
  const fetchComparison = useCallback(async () => {
    if (!runAId || !runBId) return;
    setIsLoading(true);
    setError(null);
    try {
      const res = await apiClient.compareRuns(runAId, runBId);
      setComparison(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setIsLoading(false);
    }
  }, [runAId, runBId]);

  useEffect(() => {
    if (runAId && runBId) {
      fetchComparison();
    }
  }, [fetchComparison]);

  const handleSwapRuns = () => {
    const temp = runAId;
    setRunAId(runBId);
    setRunBId(temp);
  };

  const handleExport = (format: 'json' | 'csv') => {
    if (!runAId || !runBId) return;
    const url = apiClient.getComparisonExportUrl(runAId, runBId, format);
    window.open(url, '_blank');
  };

  return (
    <div className="flex-1 min-w-0 overflow-y-auto p-4 sm:p-6 space-y-6 text-sm leading-relaxed bg-[#0a0e17] text-slate-100">
      {/* Top Header */}
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-800/80 pb-4">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <GitCompare className="w-5 h-5 text-blue-400" />
            <h2 className="text-lg font-bold tracking-wide text-slate-100">
              {(lang === 'vi' ? h('Planner & Run Experiment Comparison') : t('comparisonTitle'))}
            </h2>
          </div>
          <p className="text-sm text-slate-400 mt-1">
            {t('comparisonSubtitle')}
          </p>
        </div>

        {/* Export Buttons */}
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={() => handleExport('json')}
            disabled={!comparison || isLoading}
            className="flex flex-wrap items-center gap-1 px-3 py-1.5 rounded bg-slate-900 border border-slate-800 hover:bg-slate-800 text-sm text-slate-300 disabled:opacity-40 transition-all cursor-pointer"
          >
            <FileCode className="w-3.5 h-3.5 text-cyan-400" />
            <span>{t('exportJson')}</span>
          </button>
          <button
            type="button"
            onClick={() => handleExport('csv')}
            disabled={!comparison || isLoading}
            className="flex flex-wrap items-center gap-1 px-3 py-1.5 rounded bg-slate-900 border border-slate-800 hover:bg-slate-800 text-sm text-slate-300 disabled:opacity-40 transition-all cursor-pointer"
          >
            <FileSpreadsheet className="w-3.5 h-3.5 text-emerald-400" />
            <span>{t('exportCsv')}</span>
          </button>
        </div>
      </div>

      {/* Run Selectors Bar */}
      <div className="bg-[#111724] border border-slate-800 rounded-lg p-4 flex flex-wrap items-center justify-between gap-4">
        {/* Run A Selector */}
        <div className="flex-1 min-w-0 basis-60">
          <label htmlFor="history-run-a" className="block text-sm font-mono text-slate-400 font-semibold mb-1">
            {h('Run A (Baseline / Reference)')}
          </label>
          <select
            id="history-run-a"
            value={runAId}
            onChange={(e) => setRunAId(e.target.value)}
            className="w-full px-3 py-1.5 bg-slate-900 border border-slate-700 rounded text-sm font-mono text-slate-200 focus:outline-none focus:border-blue-500"
          >
            {runsList.map((r) => (
              <option key={`a-${r.run_id}`} value={r.run_id}>
                {r.run_id} ({h(r.planner_actual)}, {h(r.control_mode)})
              </option>
            ))}
          </select>
        </div>

        {/* Swap Button */}
        <div className="pt-5 shrink-0">
          <button
            type="button"
            onClick={handleSwapRuns}
            title={h('Swap Run A and Run B')}
            aria-label={h('Swap Run A and Run B')}
            className="p-2 rounded bg-slate-900 border border-slate-800 hover:bg-slate-800 text-slate-300 transition-all"
          >
            <ArrowLeftRight className="w-4 h-4" />
          </button>
        </div>

        {/* Run B Selector */}
        <div className="flex-1 min-w-0 basis-60">
          <label htmlFor="history-run-b" className="block text-sm font-mono text-slate-400 font-semibold mb-1">
            {h('Run B (Comparison Candidate)')}
          </label>
          <select
            id="history-run-b"
            value={runBId}
            onChange={(e) => setRunBId(e.target.value)}
            className="w-full px-3 py-1.5 bg-slate-900 border border-slate-700 rounded text-sm font-mono text-slate-200 focus:outline-none focus:border-blue-500"
          >
            {runsList.map((r) => (
              <option key={`b-${r.run_id}`} value={r.run_id}>
                {r.run_id} ({h(r.planner_actual)}, {h(r.control_mode)})
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Error state */}
      {error && (
        <div className="p-3 rounded bg-rose-950/70 border border-rose-800 text-rose-300 text-sm">
          {h('Comparison error:')} {h(error)}
        </div>
      )}

      {/* Loading state */}
      {isLoading && (
        <div className="p-8 text-center text-slate-400 font-mono text-sm">
          {h('Computing trajectory diff and comparative metrics...')}
        </div>
      )}

      {comparison && !isLoading && (
        <div className="space-y-6">
          {/* Neutral Academic Summary Banner */}
          <div className="bg-blue-950/40 border border-blue-800/80 rounded-lg p-3.5 flex items-start space-x-3 text-blue-200 text-sm">
            <Info className="w-5 h-5 text-blue-400 shrink-0 mt-0.5" />
            <div className="space-y-1">
              <div className="font-bold text-blue-300 font-mono text-sm">
                {lang === 'vi' ? 'Đối chiếu mô tả — chưa xác minh điều kiện thí nghiệm' : 'Descriptive comparison — experiment equivalence unverified'}
              </div>
              <p className="leading-relaxed text-blue-100/90 font-mono text-sm">
                {h(comparison.summary_verdict)}
              </p>
              {comparison.comparability_reasons?.map((reason) => <p key={reason}>{h(reason)}</p>)}
            </div>
          </div>

          {/* Section 1: Side-by-Side Metrics Table */}
          <div className="bg-[#111724] border border-slate-800 rounded-lg overflow-hidden shadow-lg">
            <div className="p-3 bg-slate-900/80 border-b border-slate-800 flex flex-wrap items-center justify-between gap-3">
              <h3 className="text-sm font-bold font-mono uppercase tracking-wider text-slate-300">
                {(lang === 'vi' ? h('Comparative Execution Metrics') : t('comparativeMetricsTitle'))}
              </h3>
              <span className="text-sm font-mono text-slate-400">{h('Side-by-side delta')}</span>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-left border-collapse text-sm">
                <thead>
                  <tr className="bg-slate-900/40 border-b border-slate-800 text-slate-400 font-mono text-sm uppercase">
                    <th scope="col" className="py-2.5 px-4">{t('metricLabel')}</th>
                    <th scope="col" className="py-2.5 px-4 font-bold text-slate-200">
                      <span
                        className={onSelectRunDetail ? 'cursor-pointer hover:text-blue-400' : ''}
                        onClick={() => onSelectRunDetail && onSelectRunDetail(comparison.run_a.run_id)}
                      >
                        {comparison.run_a.run_id}
                      </span>
                    </th>
                    <th scope="col" className="py-2.5 px-4 font-bold text-slate-200">
                      <span
                        className={onSelectRunDetail ? 'cursor-pointer hover:text-blue-400' : ''}
                        onClick={() => onSelectRunDetail && onSelectRunDetail(comparison.run_b.run_id)}
                      >
                        {comparison.run_b.run_id}
                      </span>
                    </th>
                    <th scope="col" className="py-2.5 px-4 text-right">{(lang === 'vi' ? h('Delta') : t('deltaLabel'))} (B - A)</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60 font-mono">
                  {comparison.metrics.map((m) => {
                    const hasDelta = m.delta !== null && m.delta !== undefined;
                    const deltaNum = typeof m.delta === 'number' ? m.delta : 0;
                    return (
                      <tr key={m.metric} className="hover:bg-slate-900/40">
                        <td className="py-2.5 px-4 font-sans text-slate-300">{h(m.label)}</td>
                        <td className="py-2.5 px-4 text-slate-200">{h(recordedValue(m.run_a_value))}{m.run_a_value != null && m.unit ? ` ${h(m.unit)}` : ''}</td>
                        <td className="py-2.5 px-4 text-slate-200">{h(recordedValue(m.run_b_value))}{m.run_b_value != null && m.unit ? ` ${h(m.unit)}` : ''}</td>
                        <td className="py-2.5 px-4 text-right">
                          {hasDelta ? (
                            <span
                              className={`px-2 py-0.5 rounded text-sm font-semibold ${
                                deltaNum > 0
                                  ? 'text-cyan-400 bg-cyan-950/60'
                                  : deltaNum < 0
                                  ? 'text-amber-400 bg-amber-950/60'
                                  : 'text-slate-400'
                              }`}
                            >
                              {deltaNum > 0 ? `+${deltaNum}` : deltaNum} {h(m.unit || '')}
                            </span>
                          ) : (
                            <span className="text-slate-400">—</span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>

          {/* Section 2: Action Sequence Trajectory Diff */}
          <div className="bg-[#111724] border border-slate-800 rounded-lg overflow-hidden shadow-lg">
            <div className="p-3 bg-slate-900/80 border-b border-slate-800 flex flex-wrap items-center justify-between gap-3">
              <h3 className="text-sm font-bold font-mono uppercase tracking-wider text-slate-300">
                {(lang === 'vi' ? h('Action Sequence Trajectory Diff') : t('actionTrajectoryTitle'))}
              </h3>
              <span className="text-sm font-mono text-slate-400">
                {lang === 'vi' ? 'Đối chiếu quyết định từng bước' : 'Step-by-step decision alignment'}
              </span>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-left border-collapse text-sm">
                <thead>
                  <tr className="bg-slate-900/40 border-b border-slate-800 text-slate-400 font-mono text-sm uppercase">
                    <th scope="col" className="py-2 px-3 w-12 text-center">{h('Iter')}</th>
                    <th scope="col" className="py-2 px-4 border-r border-slate-800">
                      {h('Run A Action & Verdict')} ({h(comparison.run_a.planner_actual)})
                    </th>
                    <th scope="col" className="py-2 px-4">
                      {h('Run B Action & Verdict')} ({h(comparison.run_b.planner_actual)})
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60 font-mono text-sm">
                  {Array.from({
                    length: Math.max(
                      comparison.action_sequence_a.length,
                      comparison.action_sequence_b.length
                    ),
                  }).map((_, idx) => {
                    const stepA = comparison.action_sequence_a[idx];
                    const stepB = comparison.action_sequence_b[idx];
                    return (
                      <tr key={`seq-${idx}`} className="hover:bg-slate-900/40">
                        <td className="py-2 px-3 text-center text-slate-400 font-bold">{idx + 1}</td>

                        {/* Step A */}
                        <td className="py-2 px-4 border-r border-slate-800">
                          {stepA ? (
                            <div className="flex flex-wrap items-center gap-2">
                              <span className="font-semibold text-slate-200">{stepA.action_id}</span>
                              <span
                                className={`px-1.5 py-0.2 rounded text-sm font-semibold ${
                                  stepA.safety_decision === 'APPROVED' || stepA.safety_decision === 'PERMITTED'
                                    ? 'bg-emerald-950 border border-emerald-800 text-emerald-300'
                                    : stepA.safety_decision === 'DENIED'
                                    ? 'bg-rose-950 border border-rose-800 text-rose-300'
                                    : 'bg-slate-900 border border-slate-700 text-slate-400'
                                }`}
                              >
                                {h(stepA.safety_decision)}
                              </span>
                              <span className="text-sm text-blue-400 font-mono">
                                {h(stepA.dispatched === true ? '(dispatched)' : stepA.dispatched === false ? '(not dispatched)' : '(dispatch unknown)')}
                              </span>
                            </div>
                          ) : (
                            <span className="text-slate-600">—</span>
                          )}
                        </td>

                        {/* Step B */}
                        <td className="py-2 px-4">
                          {stepB ? (
                            <div className="flex flex-wrap items-center gap-2">
                              <span className="font-semibold text-slate-200">{stepB.action_id}</span>
                              <span
                                className={`px-1.5 py-0.2 rounded text-sm font-semibold ${
                                  stepB.safety_decision === 'APPROVED' || stepB.safety_decision === 'PERMITTED'
                                    ? 'bg-emerald-950 border border-emerald-800 text-emerald-300'
                                    : stepB.safety_decision === 'DENIED'
                                    ? 'bg-rose-950 border border-rose-800 text-rose-300'
                                    : 'bg-slate-900 border border-slate-700 text-slate-400'
                                }`}
                              >
                                {h(stepB.safety_decision)}
                              </span>
                              <span className="text-sm text-blue-400 font-mono">
                                {h(stepB.dispatched === true ? '(dispatched)' : stepB.dispatched === false ? '(not dispatched)' : '(dispatch unknown)')}
                              </span>
                            </div>
                          ) : (
                            <span className="text-slate-600">—</span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>

          {/* Section 3: Safety Diff & Findings Overlap (2 Cols) */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {/* Safety Gate Policy Diff */}
            <div className="bg-[#111724] border border-slate-800 rounded-lg p-4 space-y-3">
              <div className="flex flex-wrap items-center gap-2 border-b border-slate-800 pb-2">
                <Shield className="w-4 h-4 text-emerald-400" />
                <h3 className="text-sm font-bold text-slate-200 font-mono">
                  {h('Safety Gate Policy Invariants')}
                </h3>
              </div>
              <p className="text-sm text-slate-300 leading-relaxed font-sans">
                {h(comparison.safety_diff.policy_adherence)}
              </p>
              <div className="text-sm font-mono space-y-1.5 pt-1">
                <div className="flex flex-wrap justify-between gap-x-4 gap-y-1">
                  <span className="text-slate-400">{h('Run A Permits / Denials:')}</span>
                  <span className="text-slate-200">
                    {recordedValue(comparison.safety_diff.run_a_permits)} / {recordedValue(comparison.safety_diff.run_a_denials)}
                  </span>
                </div>
                <div className="flex flex-wrap justify-between gap-x-4 gap-y-1">
                  <span className="text-slate-400">{h('Run B Permits / Denials:')}</span>
                  <span className="text-slate-200">
                    {recordedValue(comparison.safety_diff.run_b_permits)} / {recordedValue(comparison.safety_diff.run_b_denials)}
                  </span>
                </div>
              </div>
            </div>

            {/* Security Findings Overlap */}
            <div className="bg-[#111724] border border-slate-800 rounded-lg p-4 space-y-3">
              <div className="flex flex-wrap items-center gap-2 border-b border-slate-800 pb-2">
                <Layers className="w-4 h-4 text-cyan-400" />
                <h3 className="text-sm font-bold text-slate-200 font-mono">
                  {h('Discovered Findings Overlap')}
                </h3>
              </div>
              <div className="text-sm font-mono space-y-2">
                <div className="flex flex-wrap justify-between gap-x-4 gap-y-1">
                  <span className="text-slate-400">{h('Shared Findings:')}</span>
                  <span className="text-cyan-300 font-bold">
                    {comparison.findings_overlap.shared_count}
                  </span>
                </div>
                {comparison.findings_overlap.shared_findings.length > 0 && (
                  <div className="flex flex-wrap gap-1">
                    {comparison.findings_overlap.shared_findings.map((f) => (
                      <span
                        key={f}
                        className="px-2 py-0.5 rounded text-sm bg-slate-900 border border-slate-800 text-slate-300"
                      >
                        {h(f)}
                      </span>
                    ))}
                  </div>
                )}
                <div className="flex flex-wrap justify-between gap-x-4 gap-y-1 pt-1 border-t border-slate-800">
                  <span className="text-slate-400">{h('Unique to')} {comparison.run_a.run_id}:</span>
                  <span className="text-slate-300">{comparison.findings_overlap.unique_a_count}</span>
                </div>
                <div className="flex flex-wrap justify-between gap-x-4 gap-y-1">
                  <span className="text-slate-400">{h('Unique to')} {comparison.run_b.run_id}:</span>
                  <span className="text-slate-300">{comparison.findings_overlap.unique_b_count}</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
