import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  History,
  Search,
  RefreshCw,
  PlayCircle,
  GitCompare,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  Clock,
  ArrowRight,
} from 'lucide-react';
import { apiClient } from '../api/client';
import { recordedValue } from '../api/recordedValue';
import type { RunHistoryItem } from '../api/types';
import { useLanguage } from '../i18n/LanguageContext';
import { historyLabel } from '../i18n/historyLabels';

interface RunHistoryPageProps {
  onSelectRun: (runId: string) => void;
  onCompareRuns: (runA: string, runB: string) => void;
}

const HISTORY_PAGE_SIZE = 25;

export const RunHistoryPage: React.FC<RunHistoryPageProps> = ({
  onSelectRun,
  onCompareRuns,
}) => {
  const { lang, t } = useLanguage();
  const h = (value: string) => historyLabel(lang, value);
  const [runs, setRuns] = useState<RunHistoryItem[]>([]);
  const [totalCount, setTotalCount] = useState(0);
  const requestId = useRef(0);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Filters
  const [search, setSearch] = useState('');
  const [plannerFilter, setPlannerFilter] = useState('ALL');
  const [modeFilter, setModeFilter] = useState('ALL');
  const [stateFilter, setStateFilter] = useState('ALL');
  const [includeTestRuns, setIncludeTestRuns] = useState(false);
  const [page, setPage] = useState(1);

  // Comparison selection (up to 2 runs)
  const [selectedForCompare, setSelectedForCompare] = useState<string[]>([]);

  const fetchHistory = useCallback(async () => {
    const id = ++requestId.current;
    setIsLoading(true);
    setError(null);
    try {
      const res = await apiClient.getRunHistory({
        limit: HISTORY_PAGE_SIZE,
        offset: (page - 1) * HISTORY_PAGE_SIZE,
        include_test_runs: includeTestRuns,
        planner: plannerFilter === 'ALL' ? undefined : plannerFilter,
        control_mode: modeFilter === 'ALL' ? undefined : modeFilter,
        state: stateFilter === 'ALL' ? undefined : stateFilter,
        search: search.trim() ? search.trim() : undefined,
      });
      if (id !== requestId.current) return;
      setTotalCount(res.total_count);
      if (page > Math.max(1, Math.ceil(res.total_count / HISTORY_PAGE_SIZE))) {
        setPage(Math.max(1, Math.ceil(res.total_count / HISTORY_PAGE_SIZE)));
      }
      setRuns(res.runs.filter((run) => includeTestRuns || !/^(TEST-|RUN-TEST-|RUN-SL\d+-TEST-)/i.test(run.run_id)));
    } catch (err) {
      if (id !== requestId.current) return;
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      if (id === requestId.current) setIsLoading(false);
    }
  }, [plannerFilter, modeFilter, stateFilter, search, includeTestRuns, page]);

  useEffect(() => {
    const timer = setTimeout(() => { void fetchHistory(); }, 200);
    return () => { clearTimeout(timer); ++requestId.current; };
  }, [fetchHistory]);

  useEffect(() => {
    setPage(1);
  }, [search, plannerFilter, modeFilter, stateFilter, includeTestRuns]);

  const pageCount = Math.max(1, Math.ceil(totalCount / HISTORY_PAGE_SIZE));
  const currentPage = Math.min(page, pageCount);
  const pageStart = (currentPage - 1) * HISTORY_PAGE_SIZE;
  const pageRuns = runs;

  const toggleCompareSelection = (runId: string) => {
    setSelectedForCompare((prev) => {
      if (prev.includes(runId)) {
        return prev.filter((id) => id !== runId);
      }
      if (prev.length >= 2) {
        return [prev[1], runId];
      }
      return [...prev, runId];
    });
  };

  const handleLaunchCompare = () => {
    if (selectedForCompare.length === 2) {
      onCompareRuns(selectedForCompare[0], selectedForCompare[1]);
    }
  };

  const formatDuration = (ms?: number | null) => {
    if (!ms && ms !== 0) return '—';
    if (ms < 1000) return lang === 'vi' ? `${ms} mili giây` : `${ms}ms`;
    const secs = Math.floor(ms / 1000);
    const mins = Math.floor(secs / 60);
    const remSecs = secs % 60;
    return lang === 'vi'
      ? (mins > 0 ? `${mins} phút ${remSecs} giây` : `${secs} giây`)
      : (mins > 0 ? `${mins}m ${remSecs}s` : `${secs}s`);
  };

  const renderProvenanceBadge = (item: RunHistoryItem) => {
    const status = item.planner_verification;
    if (status === 'LLM_FALLBACK_TO_RULE') {
      return (
        <span className="px-2 py-0.5 rounded text-sm font-mono font-semibold bg-amber-950/70 border border-amber-800 text-amber-300">
          {h('LLM → RULE FALLBACK')}
        </span>
      );
    }
    if (status === 'LLM_PROVIDER_NOT_AVAILABLE') {
      return (
        <span className="px-2 py-0.5 rounded text-sm font-mono font-semibold bg-orange-950/70 border border-orange-800 text-orange-300">
          {h('LLM UNAVAILABLE')}
        </span>
      );
    }
    if (status === 'LLM_PROVIDER_EXECUTED' || status === 'LLM_PROVIDER_RECORDED') {
      return (
        <span className="px-2 py-0.5 rounded text-sm font-mono font-semibold bg-purple-950/70 border border-purple-800 text-purple-300">
          {h('LLM MODE RECORDED')}
        </span>
      );
    }
    if (status === 'HYBRID_NOT_IMPLEMENTED') {
      return (
        <span className="px-2 py-0.5 rounded text-sm font-mono font-semibold bg-slate-900 border border-slate-700 text-slate-400">
          {h('HYBRID (N/A)')}
        </span>
      );
    }
    return (
      <span className="px-2 py-0.5 rounded text-sm font-mono font-semibold bg-cyan-950/70 border border-cyan-800 text-cyan-300">
        {h(status === 'RULE_EXECUTED' ? 'RULE MODE RECORDED' : 'UNKNOWN')}
      </span>
    );
  };

  const renderStateBadge = (state: string) => {
    const s = state.toUpperCase();
    if (s === 'COMPLETED') {
      return (
        <span className="flex flex-wrap items-center gap-1 text-emerald-400 font-mono text-sm">
          <CheckCircle2 className="w-3.5 h-3.5" />
          <span>{h('COMPLETED')}</span>
        </span>
      );
    }
    if (s === 'BLOCKED') {
      return (
        <span className="flex flex-wrap items-center gap-1 text-rose-400 font-mono text-sm">
          <XCircle className="w-3.5 h-3.5" />
          <span>{h('BLOCKED')}</span>
        </span>
      );
    }
    if (s === 'STOPPED') {
      return (
        <span className="flex flex-wrap items-center gap-1 text-amber-400 font-mono text-sm">
          <AlertTriangle className="w-3.5 h-3.5" />
          <span>{h('STOPPED')}</span>
        </span>
      );
    }
    return (
      <span className="flex flex-wrap items-center gap-1 text-slate-400 font-mono text-sm">
        <Clock className="w-3.5 h-3.5" />
        <span>{h(state)}</span>
      </span>
    );
  };

  return (
    <div className="flex-1 min-w-0 overflow-y-auto p-4 sm:p-6 space-y-6 text-sm leading-relaxed bg-[#0a0e17] text-slate-100">
      {/* Top Header */}
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-800/80 pb-4">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <History className="w-5 h-5 text-blue-400" />
            <h2 className="text-lg font-bold tracking-wide text-slate-100">
              {(lang === 'vi' ? h('Execution Run History') : t('runHistoryTitle'))}
            </h2>
            <span aria-live="polite" className="text-sm font-mono px-2 py-0.5 rounded bg-blue-950/80 border border-blue-800/60 text-blue-400">
              {isLoading
                ? `— ${h('Loading...')}`
                : error !== null
                ? `— ${h('History data unavailable.')}`
                : `${totalCount} ${lang === 'vi' ? 'phiên đã ghi nhận' : 'Runs Indexed'}`}
            </span>
          </div>
          <p className="text-sm text-slate-400 mt-1">
            {(lang === 'vi' ? h('Filesystem-backed research experiment index — Auditable, replayable, and comparable') : t('runHistorySubtitle'))}
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <button
            type="button"
            onClick={fetchHistory}
            disabled={isLoading}
            className="flex flex-wrap items-center gap-1.5 px-3 py-1.5 rounded bg-slate-900 border border-slate-700 hover:bg-slate-800 text-sm font-medium text-slate-300 transition-all disabled:opacity-50"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? 'animate-spin' : ''}`} />
            <span>{lang === 'vi' ? 'Làm mới' : 'Refresh'}</span>
          </button>
        </div>
      </div>

      {/* Filter and Search Bar */}
      <div className="bg-[#111724] border border-slate-800 rounded-lg p-4 space-y-3">
        <div className="flex flex-wrap items-center gap-3">
          {/* Search box */}
          <div className="relative flex-1 min-w-0 basis-60">
            <Search className="w-4 h-4 absolute left-3 top-2.5 text-slate-400" />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              aria-label={h('Search by Run ID, Target, or Stop Reason...')}
              placeholder={h('Search by Run ID, Target, or Stop Reason...')}
              className="w-full pl-9 pr-3 py-1.5 bg-slate-900/90 border border-slate-700/80 rounded text-sm font-mono text-slate-200 placeholder-slate-500 focus:outline-none focus:border-blue-500"
            />
          </div>

          {/* Planner Filter */}
          <div className="flex flex-wrap items-center gap-1.5 text-sm">
            <span className="text-slate-400 text-sm font-sans">{h('Planner:')}</span>
            {['ALL', 'RULE', 'LLM', 'HYBRID'].map((p) => (
              <button
                key={p}
                type="button"
                aria-pressed={plannerFilter === p}
                onClick={() => setPlannerFilter(p)}
                className={`px-2.5 py-1 rounded text-sm font-mono font-medium transition-all ${
                  plannerFilter === p
                    ? 'bg-blue-600 text-white'
                    : 'bg-slate-900 border border-slate-800 text-slate-400 hover:text-slate-200'
                }`}
              >
                {h(p)}
              </button>
            ))}
          </div>

          {/* Control Mode Filter */}
          <div className="flex flex-wrap items-center gap-1.5 text-sm">
            <span className="text-slate-400 text-sm font-sans">{h('Mode:')}</span>
            {['ALL', 'AUTONOMOUS', 'ASSISTED', 'MANUAL'].map((m) => (
              <button
                key={m}
                type="button"
                aria-pressed={modeFilter === m}
                onClick={() => setModeFilter(m)}
                className={`px-2.5 py-1 rounded text-sm font-mono font-medium transition-all ${
                  modeFilter === m
                    ? 'bg-indigo-600 text-white'
                    : 'bg-slate-900 border border-slate-800 text-slate-400 hover:text-slate-200'
                }`}
              >
                {h(m)}
              </button>
            ))}
          </div>

          {/* State Filter */}
          <div className="flex flex-wrap items-center gap-1.5 text-sm">
            <span className="text-slate-400 text-sm font-sans">{h('State:')}</span>
            {['ALL', 'COMPLETED', 'STOPPED', 'BLOCKED'].map((s) => (
              <button
                key={s}
                type="button"
                aria-pressed={stateFilter === s}
                onClick={() => setStateFilter(s)}
                className={`px-2.5 py-1 rounded text-sm font-mono font-medium transition-all ${
                  stateFilter === s
                    ? 'bg-emerald-600 text-white'
                    : 'bg-slate-900 border border-slate-800 text-slate-400 hover:text-slate-200'
                }`}
              >
                {h(s)}
              </button>
            ))}
          </div>
          <label className="flex items-center gap-2 text-sm text-slate-300">
            <input type="checkbox" checked={includeTestRuns} onChange={(e) => setIncludeTestRuns(e.target.checked)} />
            {lang === 'vi' ? 'Hiện lượt chạy kiểm thử' : 'Include test runs'}
          </label>
        </div>
      </div>

      {/* Floating Compare Action Bar if runs are selected */}
      {selectedForCompare.length > 0 && (
        <div className="p-3 bg-blue-950/80 border border-blue-800/80 rounded-lg flex flex-wrap items-center justify-between gap-3 shadow-lg">
          <div className="flex flex-wrap items-center gap-2 text-sm font-mono text-blue-200">
            <GitCompare className="w-4 h-4 text-blue-400" />
            <span>
              {h('Selected for Comparison')} ({selectedForCompare.length}/2):{' '}
              <strong className="text-white">{selectedForCompare.join(lang === 'vi' ? ' và ' : ' vs ')}</strong>
            </span>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={() => setSelectedForCompare([])}
              className="px-2.5 py-1 text-sm text-slate-400 hover:text-slate-200"
            >
              {h('Clear')}
            </button>
            <button
              type="button"
              disabled={selectedForCompare.length !== 2}
              onClick={handleLaunchCompare}
              className="flex flex-wrap items-center gap-1.5 px-3 py-1.5 bg-blue-600 hover:bg-blue-500 text-white rounded text-sm font-semibold shadow disabled:opacity-40 transition-all"
            >
              <span>{h('Compare Selected')}</span>
              <ArrowRight className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      )}

      {/* Error state */}
      {error && (
        <div className="p-3 rounded bg-rose-950/70 border border-rose-800 text-rose-300 text-sm">
          {h('Error loading run history:')} {h(error)}
        </div>
      )}

      {/* Runs Table */}
      <div className="bg-[#111724] border border-slate-800/80 rounded-lg overflow-hidden shadow-xl">
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse text-sm">
            <thead>
              <tr className="bg-slate-900/90 border-b border-slate-800 text-slate-400 font-mono text-sm uppercase tracking-wider">
                <th scope="col" className="py-3 px-4 w-10 text-center">{h('Cmp')}</th>
                <th scope="col" className="py-3 px-4">{h('Run ID & Target')}</th>
                <th scope="col" className="py-3 px-4">{h('Planner Provenance')}</th>
                <th scope="col" className="py-3 px-4">{h('Control Mode')}</th>
                <th scope="col" className="py-3 px-4">{h('Outcome')}</th>
                <th scope="col" className="py-3 px-4">{h('Duration')}</th>
                <th scope="col" className="py-3 px-4 text-center">{h('Dispatches')}</th>
                <th scope="col" className="py-3 px-4 text-center">{h('Permits / Denials')}</th>
                <th scope="col" className="py-3 px-4 text-center">{h('Evidence')}</th>
                <th scope="col" className="py-3 px-4 text-right">{h('Actions')}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60 font-sans">
              {runs.length === 0 ? (
                <tr>
                  <td colSpan={10} className="py-8 text-center text-slate-400 font-mono">
                    {h(isLoading ? 'Scanning run directories...' : error !== null ? 'History data unavailable.' : 'No execution runs match current filter criteria.')}
                  </td>
                </tr>
              ) : (
                pageRuns.map((r) => {
                  const isSelected = selectedForCompare.includes(r.run_id);
                  return (
                    <tr
                      key={r.run_id}
                      className={`hover:bg-slate-900/50 transition-colors ${
                        isSelected ? 'bg-blue-950/20' : ''
                      }`}
                    >
                      {/* Checkbox for compare */}
                      <td className="py-3 px-4 text-center">
                        <input
                          type="checkbox"
                          aria-label={`${h('Compare')} ${r.run_id}`}
                          checked={isSelected}
                          onChange={() => toggleCompareSelection(r.run_id)}
                          className="rounded border-slate-700 bg-slate-800 text-blue-600 focus:ring-0 cursor-pointer"
                        />
                      </td>

                      {/* Run ID & Target */}
                      <td className="py-3 px-4">
                        <div className="font-mono font-medium text-slate-200 hover:text-blue-400 cursor-pointer" onClick={() => onSelectRun(r.run_id)}>
                          {r.run_id}
                        </div>
                        <div className="text-sm font-mono text-slate-400 flex flex-wrap items-center gap-1.5 mt-0.5">
                          <span>{r.target_id === 'UNKNOWN' ? h('UNKNOWN') : r.target_id}</span>
                          <span>•</span>
                          <span>{r.scenario === 'UNKNOWN' ? h('UNKNOWN') : r.scenario}</span>
                          {r.started_at_utc && (
                            <>
                              <span>•</span>
                              <span>{r.started_at_utc.replace('T', ' ').slice(0, 19)} UTC</span>
                            </>
                          )}
                        </div>
                      </td>

                      {/* Planner Provenance */}
                      <td className="py-3 px-4">
                        {renderProvenanceBadge(r)}
                        {r.fallback_reason && (
                          <div className="text-sm text-amber-400 font-mono truncate max-w-[150px] mt-0.5" title={h(r.fallback_reason)}>
                            {h('Fallback:')} {h(r.fallback_reason)}
                          </div>
                        )}
                      </td>

                      {/* Control Mode */}
                      <td className="py-3 px-4">
                        <span className="px-2 py-0.5 rounded text-sm font-mono font-semibold bg-slate-900 border border-slate-800 text-slate-300">
                          {h(r.control_mode || 'AUTONOMOUS')}
                        </span>
                      </td>

                      {/* State */}
                      <td className="py-3 px-4">{renderStateBadge(r.state)}</td>

                      {/* Duration */}
                      <td className="py-3 px-4 font-mono text-slate-400">
                        {formatDuration(r.duration_ms)}
                      </td>

                      {/* Dispatches */}
                      <td className="py-3 px-4 text-center font-mono">
                        <span className={`px-2 py-0.5 rounded text-sm font-semibold ${
                          r.network_dispatches != null && r.network_dispatches > 0
                            ? 'bg-blue-950/60 border border-blue-800/60 text-blue-300'
                            : 'bg-slate-900 border border-slate-800 text-slate-400'
                        }`}>
                          {recordedValue(r.network_dispatches)}
                        </span>
                      </td>

                      {/* Permits / Denials */}
                      <td className="py-3 px-4 text-center font-mono text-sm">
                        <span className="text-slate-300 font-medium">{recordedValue(r.permits)}</span>
                        <span className="text-slate-600 mx-1">/</span>
                        <span className={r.denials != null && r.denials > 0 ? 'text-rose-400 font-medium' : 'text-slate-400'}>
                          {recordedValue(r.denials)}
                        </span>
                      </td>

                      {/* Evidence */}
                      <td className="py-3 px-4 text-center font-mono">
                        <span className="text-slate-300 font-medium">{r.evidence_count}</span>
                        <div className="text-sm text-slate-400">{recordedValue(r.verified_evidence_count)} {h('verified')} · {h(r.evidence_integrity ?? 'NOT_VERIFIED')}</div>
                        {r.findings_count != null && r.findings_count > 0 && (
                          <span className="ml-1 text-sm text-amber-400">({r.findings_count} {h('fnd')})</span>
                        )}
                      </td>

                      {/* Actions */}
                      <td className="py-3 px-4 text-right space-x-2">
                        <button
                          type="button"
                          onClick={() => toggleCompareSelection(r.run_id)}
                          className={`px-2 py-1 rounded text-sm font-medium transition-all ${
                            isSelected
                              ? 'bg-blue-600 text-white'
                              : 'bg-slate-900 border border-slate-700 text-slate-300 hover:text-white hover:bg-slate-800'
                          }`}
                        >
                          {h(isSelected ? 'Selected' : 'Compare')}
                        </button>
                        <button
                          type="button"
                          onClick={() => onSelectRun(r.run_id)}
                          className="inline-flex flex-wrap items-center gap-1 px-2.5 py-1 rounded bg-blue-950/80 border border-blue-800/80 text-blue-300 hover:bg-blue-900 text-sm font-medium transition-all"
                        >
                          <PlayCircle className="w-3.5 h-3.5" />
                          <span>{h('Replay')}</span>
                        </button>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
        {!isLoading && error === null && runs.length > 0 && (
          <nav aria-label={h('History pagination')} className="flex flex-wrap items-center justify-between gap-4 border-t p-4 text-sm">
            <p aria-live="polite">
              {h('Showing')} {pageStart + 1}–{pageStart + pageRuns.length} {h('of')} {totalCount} {h('sessions')}
            </p>
            <div className="flex flex-wrap items-center gap-3">
              <button
                type="button"
                onClick={() => setPage(currentPage - 1)}
                disabled={currentPage === 1}
                className="rounded border px-3 py-2 text-sm disabled:opacity-50"
              >
                {h('Previous page')}
              </button>
              <span>{h('Page')} {currentPage} / {pageCount}</span>
              <button
                type="button"
                onClick={() => setPage(currentPage + 1)}
                disabled={currentPage === pageCount}
                className="rounded border px-3 py-2 text-sm disabled:opacity-50"
              >
                {h('Next page')}
              </button>
            </div>
          </nav>
        )}
      </div>
    </div>
  );
};
