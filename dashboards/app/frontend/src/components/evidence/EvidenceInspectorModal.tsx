import React, { useState, useEffect } from 'react';
import {
  X,
  Database,
  AlertTriangle,
  CheckCircle,
  FileText,
  Search,
  ExternalLink,
  ChevronRight,
  RefreshCw,
  Copy,
  Check,
} from 'lucide-react';
import { apiClient } from '../../api/client';
import type {
  EvidenceItem,
  FindingItem,
  EvidenceDetailResponse,
  RunSummaryResponse,
} from '../../api/types';
import { StatusBadge } from '../StatusBadge';
import { useLanguage } from '../../i18n/LanguageContext';
import { displayValue } from '../../i18n/displayValue';

interface EvidenceInspectorModalProps {
  runId: string | null;
  isOpen: boolean;
  onClose: () => void;
}

export const EvidenceInspectorModal: React.FC<EvidenceInspectorModalProps> = ({
  runId,
  isOpen,
  onClose,
}) => {
  const { lang, t } = useLanguage();
  const [activeTab, setActiveTab] = useState<'findings' | 'evidence'>('findings');
  const [loading, setLoading] = useState<boolean>(false);
  const [summary, setSummary] = useState<RunSummaryResponse | null>(null);
  const [evidenceItems, setEvidenceItems] = useState<EvidenceItem[]>([]);
  const [findings, setFindings] = useState<FindingItem[]>([]);
  const [selectedEvidenceId, setSelectedEvidenceId] = useState<string | null>(null);
  const [evidenceDetail, setEvidenceDetail] = useState<EvidenceDetailResponse | null>(null);
  const [detailLoading, setDetailLoading] = useState<boolean>(false);
  const [copiedHash, setCopiedHash] = useState<boolean>(false);
  const [searchQuery, setSearchQuery] = useState<string>('');

  useEffect(() => {
    if (isOpen && runId) {
      loadData(runId);
    } else {
      setSelectedEvidenceId(null);
      setEvidenceDetail(null);
    }
  }, [isOpen, runId]);

  const loadData = async (rId: string) => {
    setLoading(true);
    try {
      const [sumRes, evRes, fndRes] = await Promise.allSettled([
        apiClient.getRunSummary(rId),
        apiClient.getRunEvidence(rId),
        apiClient.getRunFindings(rId),
      ]);

      if (sumRes.status === 'fulfilled') setSummary(sumRes.value);
      if (evRes.status === 'fulfilled') setEvidenceItems(evRes.value.items);
      if (fndRes.status === 'fulfilled') setFindings(fndRes.value.items);
    } catch {
      // non-fatal
    } finally {
      setLoading(false);
    }
  };

  const handleSelectEvidence = async (evId: string) => {
    if (!runId) return;
    setSelectedEvidenceId(evId);
    setDetailLoading(true);
    try {
      const detail = await apiClient.getRunEvidenceDetail(runId, evId);
      setEvidenceDetail(detail);
    } catch {
      setEvidenceDetail(null);
    } finally {
      setDetailLoading(false);
    }
  };

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
    setCopiedHash(true);
    setTimeout(() => setCopiedHash(false), 2000);
  };

  if (!isOpen) return null;

  const filteredFindings = findings.filter(
    (f) =>
      f.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
      f.category.toLowerCase().includes(searchQuery.toLowerCase()) ||
      f.detail.toLowerCase().includes(searchQuery.toLowerCase()) ||
      f.finding_id.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const filteredEvidence = evidenceItems.filter(
    (e) =>
      e.evidence_id.toLowerCase().includes(searchQuery.toLowerCase()) ||
      e.artifact_type.toLowerCase().includes(searchQuery.toLowerCase()) ||
      e.sha256.toLowerCase().includes(searchQuery.toLowerCase())
  );

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-4">
      <div className="bg-[#0f172a] border border-slate-700/80 rounded-xl shadow-2xl w-full max-w-6xl max-h-[92vh] flex flex-col overflow-hidden animate-in fade-in zoom-in-95 duration-150">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-800 bg-slate-900/60">
          <div className="flex items-center space-x-3">
            <div className="p-2 bg-emerald-500/10 rounded-lg border border-emerald-500/20 text-emerald-400">
              <Database className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center space-x-2">
                <h2 className="text-base font-semibold text-slate-100">{t.evidenceVaultInspector}</h2>
                {summary && (
                  <StatusBadge
                    status={summary.integrity_status}
                    variant={summary.integrity_status === 'VERIFIED' ? 'verified' : 'neutral'}
                  />
                )}
              </div>
              <p className="text-xs font-mono text-slate-400">{lang === 'vi' ? "Lượt chạy:" : "Run:"} {runId || (lang === 'vi' ? 'Chưa có' : 'N/A')}</p>
            </div>
          </div>

          <div className="flex items-center space-x-2">
            <button
              onClick={() => runId && loadData(runId)}
              disabled={loading}
              className="p-1.5 text-slate-400 hover:text-slate-200 rounded-lg hover:bg-slate-800 transition-colors"
              title={lang === 'vi' ? "Làm mới" : "Refresh"}
            >
              <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            </button>
            <button
              onClick={onClose}
              className="p-1.5 text-slate-400 hover:text-slate-200 rounded-lg hover:bg-slate-800 transition-colors"
              title={lang === 'vi' ? "Đóng" : "Close"}
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Top Summary Bar */}
        {summary && (
          <div className="grid grid-cols-2 md:grid-cols-6 gap-3 px-6 py-3 bg-slate-900/30 border-b border-slate-800/80 text-xs font-mono">
            <div>
              <span className="text-slate-500 block text-[10px]">{lang === 'vi' ? "MỤC TIÊU" : "TARGET"}</span>
              <span className="text-slate-300 font-medium">{summary.target}</span>
            </div>
            <div>
              <span className="text-slate-500 block text-[10px]">{lang === 'vi' ? "YÊU CẦU ĐÃ GỬI" : "DISPATCHES"}</span>
              <span className="text-emerald-400 font-semibold">{summary.network_dispatches}</span>
            </div>
            <div>
              <span className="text-slate-500 block text-[10px]">{lang === 'vi' ? "QUYẾT ĐỊNH" : "DECISIONS"}</span>
              <span className="text-slate-200 font-medium">{summary.decisions_count}</span>
            </div>
            <div>
              <span className="text-slate-500 block text-[10px]">{lang === 'vi' ? "TỆP BẰNG CHỨNG" : "ARTIFACTS"}</span>
              <span className="text-slate-200 font-medium">{summary.evidence_count}</span>
            </div>
            <div>
              <span className="text-slate-500 block text-[10px]">{lang === 'vi' ? "ĐÃ XÁC MINH (SHA-256)" : "VERIFIED (SHA-256)"}</span>
              <span className="text-emerald-400 font-semibold">{summary.verified_count}</span>
            </div>
            <div>
              <span className="text-slate-500 block text-[10px]">{lang === 'vi' ? "LÝ DO DỪNG" : "STOP REASON"}</span>
              <span className="text-slate-300 truncate block" title={summary.stop_reason ? displayValue(summary.stop_reason, lang) : ''}>
                {summary.stop_reason ? displayValue(summary.stop_reason, lang) : (lang === 'vi' ? 'Chưa có' : 'N/A')}
              </span>
            </div>
          </div>
        )}

        {/* Tabs & Search */}
        <div className="flex items-center justify-between px-6 py-3 border-b border-slate-800/60 bg-slate-900/40">
          <div className="flex space-x-2">
            <button
              onClick={() => {
                setActiveTab('findings');
                setSelectedEvidenceId(null);
              }}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                activeTab === 'findings'
                  ? 'bg-blue-600 text-white shadow-sm'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60'
              }`}
            >
              {t.findingsAndSurfaces} ({findings.length})
            </button>
            <button
              onClick={() => setActiveTab('evidence')}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                activeTab === 'evidence'
                  ? 'bg-blue-600 text-white shadow-sm'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60'
              }`}
            >
              {t.cryptographicLedger} ({evidenceItems.length})
            </button>
          </div>

          <div className="relative w-64">
            <Search className="w-3.5 h-3.5 absolute left-2.5 top-2.5 text-slate-500" />
            <input
              type="text"
              placeholder={lang === 'vi' ? "Tìm mã, tiêu đề, SHA-256..." : "Search ID, title, SHA-256..."}
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full bg-slate-900/80 border border-slate-800 rounded-lg pl-8 pr-3 py-1.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-blue-500"
            />
          </div>
        </div>

        {/* Content Body */}
        <div className="flex-1 overflow-hidden grid grid-cols-1 md:grid-cols-12">
          {/* Main List Table (Tabs) */}
          <div
            className={`${
              selectedEvidenceId ? 'md:col-span-7' : 'md:col-span-12'
            } overflow-y-auto p-4 border-r border-slate-800/60 space-y-2`}
          >
            {activeTab === 'findings' ? (
              filteredFindings.length === 0 ? (
                <div className="py-12 text-center text-slate-500 text-xs">
                  {t.noFindingsRecorded}
                </div>
              ) : (
                <div className="space-y-2">
                  {filteredFindings.map((f) => (
                    <div
                      key={f.finding_id}
                      className="bg-slate-900/60 border border-slate-800 rounded-lg p-3 hover:border-slate-700 transition-colors"
                    >
                      <div className="flex items-center justify-between mb-1.5">
                        <div className="flex items-center space-x-2">
                          <span
                            className={`px-2 py-0.5 rounded text-[10px] font-semibold uppercase font-mono ${
                              f.severity === 'HIGH' || f.severity === 'CRITICAL'
                                ? 'bg-red-500/10 text-red-400 border border-red-500/20'
                                : f.severity === 'MEDIUM'
                                ? 'bg-amber-500/10 text-amber-400 border border-amber-500/20'
                                : f.severity === 'LOW'
                                ? 'bg-blue-500/10 text-blue-400 border border-blue-500/20'
                                : 'bg-slate-800 text-slate-300'
                            }`}
                          >
                            {displayValue(f.severity, lang)}
                          </span>
                          <span className="text-xs font-semibold text-slate-200">{displayValue(f.title, lang)}</span>
                        </div>
                        <span className="text-[10px] font-mono text-slate-500">{displayValue(f.category, lang)}</span>
                      </div>
                      <p className="text-xs text-slate-400 mb-2">{displayValue(f.detail, lang)}</p>
                      {f.evidence_refs && f.evidence_refs.length > 0 && (
                        <div className="flex items-center space-x-2 text-[10px] font-mono">
                          <span className="text-slate-500">{lang === 'vi' ? "Tham chiếu:" : "Trace:"}</span>
                          {f.evidence_refs.map((ref) => (
                            <button
                              key={ref}
                              onClick={() => {
                                setActiveTab('evidence');
                                handleSelectEvidence(ref);
                              }}
                              className="text-emerald-400 bg-emerald-500/10 px-1.5 py-0.5 rounded border border-emerald-500/20 hover:bg-emerald-500/20 flex items-center space-x-1"
                            >
                              <span>{ref}</span>
                              <ExternalLink className="w-2.5 h-2.5" />
                            </button>
                          ))}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )
            ) : filteredEvidence.length === 0 ? (
              <div className="py-12 text-center text-slate-500 text-xs">
                {t.noEvidenceRecorded}
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs font-mono">
                  <thead>
                    <tr className="border-b border-slate-800 text-slate-500 text-[10px]">
                      <th className="pb-2 font-medium">{lang === 'vi' ? "MÃ BẰNG CHỨNG" : "EVIDENCE ID"}</th>
                      <th className="pb-2 font-medium">{lang === 'vi' ? "LOẠI" : "TYPE"}</th>
                      <th className="pb-2 font-medium">{lang === 'vi' ? "TÍNH TOÀN VẸN SHA-256" : "SHA-256 INTEGRITY"}</th>
                      <th className="pb-2 font-medium text-right">{lang === 'vi' ? "KÍCH THƯỚC" : "SIZE"}</th>
                      <th className="pb-2 text-right">{lang === 'vi' ? "THAO TÁC" : "ACTION"}</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/40">
                    {filteredEvidence.map((item) => (
                      <tr
                        key={item.evidence_id}
                        className={`hover:bg-slate-800/40 transition-colors cursor-pointer ${
                          selectedEvidenceId === item.evidence_id ? 'bg-blue-600/10' : ''
                        }`}
                        onClick={() => handleSelectEvidence(item.evidence_id)}
                      >
                        <td className="py-2.5 text-slate-200 font-medium">{item.evidence_id}</td>
                        <td className="py-2.5 text-slate-400">{displayValue(item.artifact_type, lang)}</td>
                        <td className="py-2.5">
                          {item.verified ? (
                            <span className="inline-flex items-center space-x-1 text-emerald-400 text-[11px]">
                              <CheckCircle className="w-3 h-3" />
                              <span>{lang === 'vi' ? "ĐÃ XÁC MINH" : "VERIFIED"}</span>
                            </span>
                          ) : (
                            <span className="inline-flex items-center space-x-1 text-red-400 text-[11px]">
                              <AlertTriangle className="w-3 h-3" />
                              <span>{lang === 'vi' ? "CHƯA XÁC MINH" : "UNVERIFIED"}</span>
                            </span>
                          )}
                        </td>
                        <td className="py-2.5 text-slate-400 text-right">
                          {item.size_bytes > 0 ? `${item.size_bytes} B` : '—'}
                        </td>
                        <td className="py-2.5 text-right">
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              handleSelectEvidence(item.evidence_id);
                            }}
                            className="p-1 text-slate-400 hover:text-blue-400 transition-colors"
                            title={lang === 'vi' ? "Xem nội dung bằng chứng" : "Inspect Payload"}
                          >
                            <ChevronRight className="w-4 h-4" />
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          {/* Right Inspection Drawer Pane */}
          {selectedEvidenceId && (
            <div className="md:col-span-5 bg-slate-950/60 p-4 overflow-y-auto flex flex-col space-y-3">
              <div className="flex items-center justify-between pb-2 border-b border-slate-800">
                <div className="flex items-center space-x-2">
                  <FileText className="w-4 h-4 text-emerald-400" />
                  <span className="text-xs font-semibold text-slate-200">{t.artifactPayloadViewer}</span>
                </div>
                <button
                  onClick={() => setSelectedEvidenceId(null)}
                  className="p-1 text-slate-400 hover:text-slate-200"
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              </div>

              {detailLoading ? (
                <div className="py-12 text-center text-slate-500 text-xs">
                  <RefreshCw className="w-4 h-4 animate-spin mx-auto mb-2 text-blue-400" />
                  {t.loadingCryptographicRecord}
                </div>
              ) : evidenceDetail ? (
                <div className="space-y-3 text-xs">
                  {/* Meta */}
                  <div className="bg-slate-900 border border-slate-800 rounded-lg p-3 space-y-1.5 font-mono text-[11px]">
                    <div className="flex justify-between">
                      <span className="text-slate-500">{lang === 'vi' ? "Mã" : "ID"}</span>
                      <span className="text-slate-200 font-semibold">{evidenceDetail.evidence_id}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-slate-500">{lang === 'vi' ? "LOẠI" : "TYPE"}</span>
                      <span className="text-slate-300">{displayValue(evidenceDetail.artifact_type, lang)}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-slate-500">{lang === 'vi' ? "KÍCH THƯỚC" : "SIZE"}</span>
                      <span className="text-slate-300">{evidenceDetail.size_bytes} {lang === 'vi' ? 'byte' : 'bytes'}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-slate-500">{lang === 'vi' ? "TÍNH TOÀN VẸN" : "INTEGRITY"}</span>
                      <span
                        className={`font-semibold ${
                          evidenceDetail.verified ? 'text-emerald-400' : 'text-red-400'
                        }`}
                      >
                        {evidenceDetail.verified ? (lang === 'vi' ? 'SHA-256 TRÙNG KHỚP' : 'SHA-256 MATCH') : (lang === 'vi' ? 'MÃ BĂM KHÔNG KHỚP' : 'HASH MISMATCH')}
                      </span>
                    </div>
                    <div className="pt-1.5 border-t border-slate-800">
                      <div className="flex items-center justify-between">
                        <span className="text-slate-500">SHA-256</span>
                        <button
                          onClick={() => copyToClipboard(evidenceDetail.sha256)}
                          className="text-[10px] text-blue-400 hover:text-blue-300 flex items-center space-x-1"
                        >
                          {copiedHash ? <Check className="w-2.5 h-2.5" /> : <Copy className="w-2.5 h-2.5" />}
                          <span>{copiedHash ? t.copied : t.copy}</span>
                        </button>
                      </div>
                      <span className="text-[10px] text-slate-400 break-all select-all font-mono block mt-0.5">
                        {evidenceDetail.sha256}
                      </span>
                    </div>
                  </div>

                  {/* Content viewer */}
                  <div>
                    <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-400 mb-1 block">
                      {t.decodedContent}
                    </span>
                    <pre className="bg-slate-900/90 border border-slate-800 rounded-lg p-3 text-[11px] font-mono text-slate-300 overflow-x-auto max-h-96 select-text whitespace-pre-wrap">
                      {typeof evidenceDetail.content === 'object'
                        ? JSON.stringify(evidenceDetail.content, null, 2)
                        : String(evidenceDetail.content || (lang === 'vi' ? 'Trống' : 'Empty'))}
                    </pre>
                  </div>
                </div>
              ) : (
                <div className="py-8 text-center text-slate-500 text-xs">{lang === 'vi' ? "Không tải được tệp bằng chứng." : "Failed to load evidence artifact."}</div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
