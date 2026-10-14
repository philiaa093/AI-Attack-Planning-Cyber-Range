import React, { useState } from 'react';
import {
  Radio,
  ChevronDown,
  ChevronRight,
  Trash2,
  Filter,
  CheckCircle2,
  XCircle,
  AlertCircle,
  PlayCircle,
  Info,
} from 'lucide-react';
import type { AgentEvent, SseConnectionStatus } from '../../api/types';
import { StatusBadge } from '../StatusBadge';
import { useLanguage } from '../../i18n/LanguageContext';
import { displayValue } from '../../i18n/displayValue';

interface EventFeedProps {
  events: AgentEvent[];
  connectionStatus: SseConnectionStatus;
  onClear: () => void;
  onReconnect: () => void;
}

export const EventFeed: React.FC<EventFeedProps> = ({
  events,
  connectionStatus,
  onClear,
  onReconnect,
}) => {
  const { lang, t } = useLanguage();
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [filterType, setFilterType] = useState<string>('ALL');
  const [viewMode, setViewMode] = useState<'milestones' | 'telemetry'>('milestones');

  const toggleExpand = (id: string) => {
    setExpandedId((prev) => (prev === id ? null : id));
  };

  const getEventBadge = (type: string) => {
    if (type.includes('DENIED') || type.includes('FAILED') || type.includes('BLOCKED')) {
      return { icon: XCircle, color: 'text-rose-400', badge: 'denied' as const };
    }
    if (type.includes('PERMITTED') || type.includes('COMPLETED') || type.includes('VERIFIED')) {
      return { icon: CheckCircle2, color: 'text-emerald-400', badge: 'pass' as const };
    }
    if (type.includes('STARTED') || type.includes('DISPATCHED') || type.includes('PROPOSED')) {
      return { icon: PlayCircle, color: 'text-blue-400', badge: 'running' as const };
    }
    if (type.includes('STOP')) {
      return { icon: AlertCircle, color: 'text-amber-400', badge: 'warning' as const };
    }
    return { icon: Info, color: 'text-slate-400', badge: 'neutral' as const };
  };

  const filteredEvents = events.filter((ev) => {
    if (viewMode === 'milestones' && !/RUN_|STOP_|KILL_|EMERGENCY_|PLANNER_PROPOSED|PLANNER_FALLBACK|SAFETY_PERMITTED|SAFETY_DENIED|ACTION_COMPLETED|ACTION_FAILED|EVIDENCE_VERIFIED/.test(ev.type)) return false;
    if (filterType === 'ALL') return true;
    if (filterType === 'SAFETY') return ev.type.includes('SAFETY') || ev.type.includes('KILL');
    if (filterType === 'PLANNER') return ev.type.includes('PLANNER');
    if (filterType === 'DISPATCH') return ev.type.includes('ACTION') || ev.type.includes('DISPATCH');
    if (filterType === 'EVIDENCE') return ev.type.includes('EVIDENCE');
    return true;
  });

  return (
    <div className="bg-[#111724] border border-slate-800/80 rounded-lg p-4 flex flex-col h-[480px] shadow-sm">
      {/* Header */}
      <div className="flex items-center justify-between pb-3 border-b border-slate-800/60 shrink-0">
        <div className="flex items-center space-x-2">
          <Radio className="w-4 h-4 text-emerald-400 animate-pulse" />
          <span className="text-xs font-semibold tracking-wider uppercase text-slate-400">
            {t.liveEventStream}
          </span>
          <span className="text-xs text-slate-500 font-mono">({events.length})</span>
        </div>

        <div className="flex items-center space-x-2">
          <StatusBadge
            status={connectionStatus === 'CONNECTED' ? 'LIVE' : connectionStatus}
            size="sm"
          />

          {connectionStatus !== 'CONNECTED' && (
            <button
              onClick={onReconnect}
              aria-label={lang === 'vi' ? "Kết nối lại luồng sự kiện" : "Reconnect event stream"}
              className="px-2 py-0.5 text-[11px] rounded bg-blue-900/60 hover:bg-blue-800 text-blue-200 border border-blue-700/50"
            >
              {t.reconnect}
            </button>
          )}

          <button
            onClick={onClear}
            title={t.clearFeed}
            aria-label={lang === 'vi' ? "Xóa bảng tin" : "Clear feed"}
            className="p-1 rounded text-slate-500 hover:text-slate-300 hover:bg-slate-800 transition-colors"
          >
            <Trash2 className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* View Mode & Filter bar */}
      <div className="flex flex-wrap items-center justify-between gap-2 py-2 border-b border-slate-800/40 text-[11px] shrink-0">
        {/* View Mode Switcher */}
        <div className="flex items-center space-x-1 bg-slate-900/90 border border-slate-800 p-0.5 rounded">
          <button
            type="button"
            onClick={() => setViewMode('milestones')}
            className={`px-2 py-0.5 rounded text-[10px] font-sans font-semibold transition-all ${
              viewMode === 'milestones'
                ? 'bg-blue-600 text-white shadow-xs'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            {t.simpleMilestones}
          </button>
          <button
            type="button"
            onClick={() => setViewMode('telemetry')}
            className={`px-2 py-0.5 rounded text-[10px] font-sans font-semibold transition-all ${
              viewMode === 'telemetry'
                ? 'bg-blue-600 text-white shadow-xs'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            {t.detailedTelemetry}
          </button>
        </div>

        {/* Category Filters */}
        <div className="flex items-center space-x-1 overflow-x-auto">
          <Filter className="w-3 h-3 text-slate-500 mr-0.5" />
          {['ALL', 'SAFETY', 'PLANNER', 'DISPATCH', 'EVIDENCE'].map((f) => (
            <button
              key={f}
              onClick={() => setFilterType(f)}
              className={`px-1.5 py-0.5 rounded text-[10px] font-mono transition-colors ${
                filterType === f
                  ? 'bg-blue-900/60 text-blue-300 border border-blue-700/60 font-semibold'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60'
              }`}
            >
              {displayValue(f, lang)}
            </button>
          ))}
        </div>
      </div>

      {/* Event list */}
      <div className="flex-1 overflow-y-auto mt-2 space-y-1.5 pr-1">
        {filteredEvents.length === 0 ? (
          <div className="h-full flex flex-col items-center justify-center text-slate-600 text-xs font-mono">
            <Radio className="w-6 h-6 mb-2 text-slate-700" />
            <span>{t.awaitingEvents}</span>
          </div>
        ) : (
          [...filteredEvents].reverse().map((ev) => {
            const isExpanded = expandedId === ev.event_id;
            const meta = getEventBadge(ev.type);
            const time = ev.timestamp_utc ? new Date(ev.timestamp_utc).toLocaleTimeString() : '—';
            const Icon = meta.icon;

            // Simplified Milestone Title
            let milestoneSummary = ev.type;
            const p = ev.payload || {};
            if (viewMode === 'milestones') {
              if (ev.type.includes('PROPOSAL') || ev.type.includes('PLANNER')) {
                milestoneSummary = lang === 'vi'
                  ? `ĐỀ XUẤT: ${p.action_id || p.action || 'Hành động'} — ${displayValue(String(p.reason || 'Bước chiến lược'), lang)}`
                  : `PROPOSE: ${p.action_id || p.action || 'ACTION'} — ${p.reason || 'Strategic step'}`;
              } else if (ev.type.includes('PERMITTED')) {
                milestoneSummary = lang === 'vi'
                  ? `CỔNG AN TOÀN: CHO PHÉP [Mục tiêu: ${p.target || 'lab-ecommerce'}]`
                  : `SAFETY GATE: PERMITTED [Target: ${p.target || 'lab-ecommerce'}]`;
              } else if (ev.type.includes('DENIED')) {
                milestoneSummary = lang === 'vi' ? 'CỔNG AN TOÀN: TỪ CHỐI [0 YÊU CẦU MẠNG ĐƯỢC GỬI]' : `SAFETY GATE REFUSAL: DENIED [0 NETWORK DISPATCHES]`;
              } else if (ev.type.includes('DISPATCH') || ev.type.includes('ACTION_EXEC')) {
                milestoneSummary = `${lang === 'vi' ? 'THỰC THI' : 'EXECUTE'}: HTTP ${p.method ?? '—'} ${p.path ?? '—'} -> ${p.status_code ?? '—'}`;
              } else if (ev.type.includes('EVIDENCE')) {
                milestoneSummary = `${lang === 'vi' ? 'BẰNG CHỨNG' : 'EVIDENCE'}: SHA-256 ${String(p.sha256 || p.evidence_id || '').slice(0, 16)}...`;
              }
            }

            return (
              <div
                key={ev.event_id}
                className="bg-slate-900/80 border border-slate-800/70 rounded p-2 text-xs hover:border-slate-700 transition-colors"
              >
                <div
                  onClick={() => toggleExpand(ev.event_id)}
                  className="flex items-center justify-between cursor-pointer select-none"
                >
                  <div className="flex items-center space-x-2 truncate">
                    {isExpanded ? (
                      <ChevronDown className="w-3.5 h-3.5 text-slate-500 shrink-0" />
                    ) : (
                      <ChevronRight className="w-3.5 h-3.5 text-slate-500 shrink-0" />
                    )}
                    <Icon className={`w-3.5 h-3.5 shrink-0 ${meta.color}`} />
                    <span className="font-mono text-slate-400 text-[11px] shrink-0">{time}</span>
                    <span className="font-mono font-semibold text-slate-200 truncate">{displayValue(ev.type, lang)}</span>
                    {viewMode === 'milestones' && milestoneSummary !== ev.type && (
                      <span className="text-[11px] text-cyan-300 font-sans truncate hidden sm:inline" title={milestoneSummary}>
                        — {milestoneSummary}
                      </span>
                    )}
                  </div>

                  <div className="flex items-center space-x-2 shrink-0">
                    {ev.phase && (
                      <span className="text-[10px] font-mono text-indigo-400/90 bg-indigo-950/40 px-1.5 py-0.2 rounded border border-indigo-900/30">
                        {displayValue(ev.phase, lang)}
                      </span>
                    )}
                    {typeof ev.iteration === 'number' && (
                      <span className="text-[10px] font-mono text-slate-400">
                        #{ev.iteration}
                      </span>
                    )}
                  </div>
                </div>

                {isExpanded && (
                  <div className="mt-2 pt-2 border-t border-slate-800/60 font-mono text-[11px] space-y-1 text-slate-300">
                    <div className="flex justify-between text-slate-400 text-[10px]">
                      <span>{lang === 'vi' ? "Mã sự kiện:" : "ID:"} {ev.event_id}</span>
                      <span>{lang === 'vi' ? "Lượt chạy:" : "RUN:"} {ev.run_id}</span>
                    </div>

                    <div className="mt-1 bg-slate-950 p-2 rounded border border-slate-800 overflow-x-auto text-[11px] text-slate-300">
                      <pre className="whitespace-pre-wrap font-mono">
                        {JSON.stringify(ev.payload, null, 2)}
                      </pre>
                    </div>
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
};
