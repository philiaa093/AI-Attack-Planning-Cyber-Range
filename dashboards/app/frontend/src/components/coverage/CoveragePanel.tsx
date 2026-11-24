import React, { useEffect, useState } from 'react';
import { apiClient } from '../../api/client';
import type { RunCoverage } from '../../api/types';
import { useLanguage } from '../../i18n/LanguageContext';

interface CoveragePanelProps {
  runId: string | null;
  refreshKey?: string;
}

const statusLabel = (value: string, vi: boolean): string => {
  const labels: Record<string, [string, string]> = {
    VERIFIED: ['Đã đối chiếu hash', 'Hashes verified'],
    FAILED: ['Không xác minh được', 'Verification failed'],
    NOT_VERIFIED: ['Chưa xác minh', 'Not verified'],
    COMPLETED: ['Đã chạy', 'Completed'],
    ERROR: ['Lỗi', 'Error'],
    NOT_SELECTED: ['Không chọn', 'Not selected'],
    NOT_RUN: ['Chưa chạy', 'Not run'],
    NOT_RECORDED: ['Chưa ghi nhận', 'Not recorded'],
    UNKNOWN: ['Chưa biết', 'Unknown'],
    CHECKS_RECORDED: ['Có check được ghi nhận', 'Checks recorded'],
    RECORDED: ['Đã ghi nhận', 'Recorded'],
    PARTIAL: ['Một phần', 'Partial'],
    BOUNDED: ['Trong phạm vi giới hạn', 'Bounded'],
    INCOMPLETE: ['Chưa hoàn tất', 'Incomplete'],
    NOT_TESTED: ['Chưa kiểm tra', 'Not tested'],
    PASS: ['Đạt', 'Pass'],
    FAIL: ['Không đạt', 'Fail'],
    INCONCLUSIVE: ['Chưa kết luận', 'Inconclusive'],
    NEGATIVE: ['Không thấy dấu hiệu trong phép thử này', 'No signal in this check'],
    SIGNAL: ['Có tín hiệu', 'Signal'],
    VERIFIED_IN_LAB: ['Có bằng chứng trong lab', 'Evidence observed in lab'],
    REFUSED: ['Bị từ chối', 'Refused'],
  };
  return labels[value] ? labels[value][vi ? 0 : 1] : value;
};

const reasonLabel = (reason: string | null | undefined, vi: boolean): string | null => {
  if (!reason) return null;
  const reasons: Record<string, [string, string]> = {
    NOT_SELECTED: ['Không chọn scanner này', 'Scanner not selected'],
    NO_SCANNER_RESULT_RECORDED: ['Chưa có evidence kết quả scanner; không rõ lý do', 'No scanner result evidence; reason unknown'],
    WORKFLOW_NOT_APPROVED: ['Workflow chưa được phê duyệt', 'Workflow was not approved'],
    NO_CHECK_EVIDENCE: ['Chưa có evidence cho trường hợp này', 'No evidence for this case'],
    CHECK_CONTEXT_NOT_RECORDED_OR_MISMATCHED: ['Evidence cũ thiếu hoặc không khớp ngữ cảnh route/role', 'Historical evidence lacks or disagrees with route/role context'],
    'Invalid baseline control during bounded SQL syntax probe': ['Baseline không hợp lệ nên chưa kết luận được', 'Invalid baseline control during bounded SQL syntax probe'],
    'Incomplete response during bounded reflection probe': ['Phản hồi không đủ điều kiện để kết luận', 'Incomplete response during bounded reflection probe'],
    budget_exhausted: ['Đã hết ngân sách', 'Budget exhausted'],
    SCANNER_TIMEOUT: ['Scanner vượt thời gian chờ', 'Scanner timed out'],
    SCANNER_REFUSAL_LIMIT: ['Scanner đạt giới hạn yêu cầu bị từ chối', 'Scanner refusal limit reached'],
    PATH_INPUT_NOT_OBSERVED: ['Tham số không phải đầu vào tệp hoặc đường dẫn', 'The parameter is not a file or path input'],
    'Safety Gate refused bounded SQL syntax probe: SCAN_READ_ONLY_METHOD_REQUIRED': ['Scan riêng không gửi POST; phép thử này chưa được thực hiện', 'Separate scans do not send POST; this check was not performed'],
    'Safety Gate refused bounded reflection probe: SCAN_READ_ONLY_METHOD_REQUIRED': ['Scan riêng không gửi POST; phép thử này chưa được thực hiện', 'Separate scans do not send POST; this check was not performed'],
  };
  return reasons[reason] ? reasons[reason][vi ? 0 : 1] : reason;
};

const matrixLabel = (value: string, vi: boolean): string => {
  if (!vi) return value;
  const labels: Record<string, string> = {
    USER_A: 'Người dùng A', USER_B: 'Người dùng B', USER: 'Người dùng', ADMIN: 'Quản trị',
    OWNER: 'Chủ sở hữu', OTHER_USER: 'Người dùng khác', GUEST: 'Khách',
    ANONYMOUS: 'Chưa đăng nhập', AUTHENTICATED: 'Đã đăng nhập', EXPIRED: 'Phiên hết hạn',
    VALID_LOGIN: 'Đăng nhập hợp lệ', INVALID_CSRF: 'CSRF không hợp lệ',
    INVALID_CSRF_NO_EFFECT: 'Giỏ hàng sau CSRF không hợp lệ', VALID_CHECKOUT: 'Thanh toán hợp lệ',
    DUPLICATE_CHECKOUT: 'Thanh toán lặp', OWN_ORDER: 'Đơn của mình', OTHER_USERS_ORDER: 'Đơn của người khác',
    ADMIN_ACCESS: 'Truy cập quản trị', BACKWARD_TRANSITION: 'Chuyển trạng thái ngược',
    SHIP_ORDER: 'Chuyển đơn sang đã giao vận', ADMIN_MUTATION: 'Sửa dữ liệu quản trị',
    ADMIN_ORDER_MUTATION: 'Người dùng thường đổi trạng thái đơn',
    VALID_CSRF_CONTROL: 'Đối chứng CSRF hợp lệ',
    EXPIRED_SESSION: 'Phiên hết hạn', MISSING_CSRF: 'Thiếu CSRF',
    'Login succeeds': 'Đăng nhập thành công', 'Admin login succeeds': 'Quản trị đăng nhập thành công',
    'Cart remains unchanged': 'Giỏ hàng không thay đổi', 'One order created': 'Tạo một đơn',
    'No duplicate order': 'Không tạo đơn trùng', 'Access denied': 'Truy cập bị từ chối',
    'Access denied without a write': 'Từ chối và không ghi dữ liệu', 'Order becomes shipped': 'Đơn chuyển sang đã giao vận',
    'HTTP 403 and no order or cart change': 'HTTP 403, không tạo đơn hoặc đổi giỏ hàng',
    'HTTP 403 and order status unchanged': 'HTTP 403, trạng thái đơn không đổi',
  };
  return labels[value] ?? value;
};

const verificationLimit = (action: string, vi: boolean): string => {
  const labels: Record<string, [string, string]> = {
    'ACTION-WEB-001': ['Chỉ kiểm tra dấu hiệu cú pháp; không chứng minh truy cập dữ liệu.', 'Syntax signals only; data access is not established.'],
    'ACTION-WEB-002': ['Dùng marker trơ; không chứng minh thực thi trong trình duyệt.', 'Inert markers only; browser execution is not established.'],
    'ACTION-WEB-003': ['Chỉ dùng sentinel trong lab.', 'Lab sentinel only.'],
  };
  return labels[action]?.[vi ? 0 : 1] ?? '';
};

export const CoveragePanel: React.FC<CoveragePanelProps> = ({ runId, refreshKey }) => {
  const { lang } = useLanguage();
  const vi = lang === 'vi';
  const [data, setData] = useState<RunCoverage | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);
  const [refresh, setRefresh] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setData(null);
    setError(false);
    if (!runId) {
      setLoading(false);
      return () => { cancelled = true; };
    }
    setLoading(true);
    apiClient.getRunCoverage(runId)
      .then(value => { if (!cancelled) setData(value); })
      .catch(() => { if (!cancelled) setError(true); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [runId, refreshKey, refresh]);

  return (
    <section aria-label={vi ? 'Phạm vi kiểm tra' : 'Coverage'} className="space-y-4 rounded-lg border border-slate-700 bg-[#111724] p-4 text-sm text-slate-200">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="font-semibold">{vi ? 'Phạm vi và phần chưa kiểm tra' : 'Coverage and untested cases'}</h3>
          <p className="mt-1 max-w-3xl text-xs text-slate-400">{vi ? 'Chỉ tổng hợp evidence của phiên này. Test fixture và số request không chứng minh ứng dụng đã được kiểm tra toàn diện.' : 'Only evidence from this run is summarized. Fixture tests and request counts do not establish complete application coverage.'}</p>
        </div>
        {runId && <button type="button" onClick={() => setRefresh(value => value + 1)} className="rounded border border-slate-600 px-2 py-1 text-xs text-slate-200 focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-400">{vi ? 'Cập nhật' : 'Refresh'}</button>}
      </div>
      {!runId && <p className="text-slate-400">{vi ? 'Chưa chọn phiên.' : 'No run selected.'}</p>}
      {loading && <p role="status" className="text-slate-400">{vi ? 'Đang đọc evidence…' : 'Reading evidence…'}</p>}
      {error && <p role="alert" className="text-rose-300">{vi ? 'Không đọc được coverage của phiên. Thử cập nhật lại.' : 'Could not read run coverage. Try refreshing.'}</p>}
      {data && <>
        <p className="text-xs text-slate-400">{vi ? 'Tính toàn vẹn bản ghi' : 'Record integrity'}: <span className={data.integrity === 'VERIFIED' ? 'text-emerald-300' : 'text-amber-300'}>{statusLabel(data.integrity, vi)}</span> · {data.record_count} {vi ? 'bản ghi' : 'records'}</p>
        {data.integrity !== 'VERIFIED' ? <p className="text-amber-200">{vi ? 'Chưa thể hiển thị kết quả coverage khi evidence không được xác minh.' : 'Coverage cannot be displayed without verified evidence.'}</p> : <>
          <p className="text-xs text-slate-400">{vi ? 'Phạm vi phiên' : 'Run scope'}: {data.scope?.execution_scope ?? (vi ? 'chưa ghi nhận' : 'not recorded')}</p>
          <div className="grid gap-4 lg:grid-cols-2">
            <section aria-label={vi ? 'Coverage scanner' : 'Scanner coverage'} className="space-y-2 rounded border border-slate-700 p-3">
              <h4 className="font-medium">Scanner</h4>
              {(data.scope?.execution_scope === 'scan' || (data.scope?.execution_scope === 'combined' && data.scope.workflow_approved === false)) && <p className="text-xs text-slate-400">{vi ? 'Restore môi trường scan' : 'Scan environment restore'}: {statusLabel(data.scan_isolation?.restore ?? 'UNKNOWN', vi)}</p>}
              {data.scanners.map(scanner => {
                const seed = scanner.seed_coverage;
                return <div key={scanner.tool} className="border-t border-slate-800 pt-2 text-xs">
                  <p className="text-slate-200">{scanner.tool}: {statusLabel(scanner.status, vi)} · {statusLabel(scanner.coverage, vi)}</p>
                  {typeof seed.requested_seed_count === 'number' && typeof seed.observed_seed_count === 'number' && <p className="mt-1 text-slate-400">{vi ? 'URL đã gửi / đã quan sát' : 'URLs requested / observed'}: {seed.requested_seed_count} / {seed.observed_seed_count}</p>}
                  {typeof seed.not_requested_seed_count === 'number' && seed.not_requested_seed_count > 0 && <p className="text-amber-200">{seed.not_requested_seed_count} {vi ? 'URL chưa gửi; lý do cụ thể chưa được ghi.' : 'URLs not requested; the specific reason was not recorded.'}</p>}
                  {seed.options_truncated === true && <p className="text-amber-200">{vi ? 'Danh sách lựa chọn bị giới hạn.' : 'Option list truncated.'}</p>}
                  {typeof scanner.refused_requests === 'number' && scanner.refused_requests > 0 && <p className="text-amber-200">{scanner.refused_requests} {vi ? 'yêu cầu bị từ chối' : 'requests refused'}</p>}
                  {typeof scanner.candidate_count === 'number' && <p className="text-slate-400">{scanner.candidate_count} {vi ? 'candidate cần xác minh' : 'unconfirmed candidates'}</p>}
                  {scanner.reason && <p className="text-amber-200">{reasonLabel(scanner.reason, vi)}</p>}
                </div>;
              })}
            </section>
            <section aria-label={vi ? 'Coverage workflow' : 'Workflow coverage'} className="space-y-2 rounded border border-slate-700 p-3">
              <h4 className="font-medium">{vi ? 'Workflow cố định' : 'Fixed workflow'}</h4>
              <p className="text-xs text-slate-300">{statusLabel(data.workflow.status, vi)} · {data.workflow.recorded_checks} {vi ? 'check có evidence' : 'checks with evidence'}</p>
              <p className="text-xs text-slate-400">{vi ? 'Restore' : 'Restore'}: {statusLabel(data.workflow.restore, vi)}</p>
              {data.workflow.reason && <p className="text-xs text-amber-200">{reasonLabel(data.workflow.reason, vi)}</p>}
              <p className="text-xs text-slate-400">{vi ? 'Workflow được ghi riêng; không xem đây là kết quả scanner.' : 'The workflow is recorded separately from scanners.'}</p>
            </section>
          </div>
          <section aria-label={vi ? 'Kiểm tra nội bộ' : 'Internal verification'} className="space-y-2">
            <h4 className="font-medium">{vi ? 'Kiểm tra nội bộ theo bề mặt' : 'Internal verification by surface'}</h4>
            <p className="text-xs text-slate-400">{vi ? 'Kết quả chỉ áp dụng cho phép thử và bề mặt được ghi.' : 'Results apply only to the recorded check and surface.'}</p>
            {data.verifications.length === 0 ? <p className="text-xs text-slate-400">{vi ? 'Chưa ghi nhận kết quả kiểm tra nội bộ.' : 'No internal verification result recorded.'}</p> : data.verifications.map(item => <div key={`${item.action}:${item.resource}:${item.parameter}`} className="rounded border border-slate-800 p-2 text-xs">
              <p className="break-all text-slate-200">{item.action} · {item.resource} · {item.parameter} · {item.attempts} {vi ? 'lượt' : 'attempts'}</p>
              <p className="mt-1 text-amber-200">{statusLabel(item.classification, vi)}{item.reason ? ` — ${reasonLabel(item.reason, vi)}` : ''}</p>
              <p className="mt-1 text-slate-400">{verificationLimit(item.action, vi)}</p>
            </div>)}
          </section>
          <section aria-label={vi ? 'Matrix kiểm tra' : 'Check matrix'} className="space-y-2">
            <h4 className="font-medium">{vi ? 'Matrix route × role × trạng thái đăng nhập' : 'Route × role × authentication matrix'}</h4>
            <p className="text-xs text-slate-400">{vi ? 'Các dòng dự kiến chưa có evidence vẫn để trống kết quả. Bảng không tự chạy thêm case.' : 'Planned rows remain untested without evidence. This table does not execute additional cases.'}</p>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[760px] text-left text-xs">
                <thead className="border-b border-slate-700 text-slate-400"><tr><th className="p-2">Route</th><th className="p-2">Role</th><th className="p-2">{vi ? 'Đăng nhập' : 'Auth state'}</th><th className="p-2">{vi ? 'Trường hợp' : 'Case'}</th><th className="p-2">{vi ? 'Kỳ vọng' : 'Expected'}</th><th className="p-2">{vi ? 'Kết quả' : 'Result'}</th></tr></thead>
                <tbody>{data.matrix.map(row => <tr key={row.check} className="border-b border-slate-800 align-top">
                  <td className="p-2 break-all">{row.method} {row.route}</td><td className="p-2">{matrixLabel(row.role, vi)}</td><td className="p-2">{matrixLabel(row.auth_state, vi)}</td>
                  <td className="p-2">{matrixLabel(row.case, vi)}{row.negative && <span className="ml-1 text-amber-300">{vi ? 'phủ định' : 'negative'}</span>}</td>
                  <td className="p-2 text-slate-400">{matrixLabel(row.expected, vi)}</td>
                  <td className="p-2"><span className={row.status === 'PASS' ? 'text-emerald-300' : row.status === 'FAIL' ? 'text-rose-300' : 'text-amber-200'}>{statusLabel(row.status, vi)}</span>
                    {row.http_status != null && ` · HTTP ${row.http_status}`}
                    {row.reason && <p className="mt-1 text-slate-400">{reasonLabel(row.reason, vi)}</p>}
                    {row.evidence_id && <p className="mt-1 break-all text-slate-500">{row.evidence_id}</p>}
                  </td>
                </tr>)}</tbody>
              </table>
            </div>
            {data.legacy_workflow_checks.length > 0 && <details className="text-xs text-slate-400"><summary className="cursor-pointer">{vi ? 'Check cũ chưa đủ ngữ cảnh' : 'Legacy checks without full context'} ({data.legacy_workflow_checks.length})</summary>
              {data.legacy_workflow_checks.map(check => <p className="mt-1 break-all" key={check.evidence_id}>{check.check}: {statusLabel(check.status, vi)} · {check.evidence_id}</p>)}
            </details>}
          </section>
        </>}
      </>}
    </section>
  );
};
