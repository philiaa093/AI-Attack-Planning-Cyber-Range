import type { Language } from './translations';

// Presentation only: never use translated values in requests or audit records.
const viValues: Record<string, string> = {
  UNKNOWN: 'Chưa xác định', TBD: 'Chờ xác định', NONE: 'Không có', IDLE: 'Chưa bắt đầu',
  HEALTHY: 'Hoạt động ổn định', UNHEALTHY: 'Hoạt động bất thường',
  RUNNING: 'Đang chạy', STARTING: 'Đang khởi động', STOPPING: 'Đang dừng',
  STOPPED: 'Đã dừng', COMPLETED: 'Đã kết thúc', INCOMPLETE: 'Chưa hoàn tất',
  COMPLETED_BOUNDED: 'Hoàn tất trong phạm vi giới hạn', FAILED: 'Gặp lỗi',
  BLOCKED: 'Bị chặn', ERROR: 'Lỗi', WARNING: 'Cần chú ý',
  PASS: 'Đạt', FAIL: 'Không đạt', VERIFIED: 'Đã xác minh', NOT_VERIFIED: 'Chưa xác minh',
  UNVERIFIED: 'Chưa xác minh', UNAVAILABLE: 'Không khả dụng', NOT_RUN: 'Chưa chạy',
  NOT_STARTED: 'Chưa bắt đầu', PENDING: 'Đang chờ', ACTIVE: 'Đang hoạt động',
  PAUSED: 'Đã tạm dừng', PAUSING: 'Đang tạm dừng', RESUMING: 'Đang tiếp tục',
  WAITING_FOR_APPROVAL: 'Chờ phê duyệt', DENIED: 'Bị từ chối', PERMITTED: 'Được cho phép',
  APPROVED: 'Đã phê duyệt', REJECTED: 'Đã từ chối', RECORDING: 'Đang ghi nhận',
  CONNECTED: 'Đã kết nối', DISCONNECTED: 'Mất kết nối', CONNECTING: 'Đang kết nối',
  RECONNECTING: 'Đang kết nối lại', LIVE: 'Trực tiếp',
  RULE: 'Theo quy tắc', LLM: 'Mô hình ngôn ngữ', RL: 'Học tăng cường', HYBRID: 'Kết hợp',
  MANUAL: 'Thủ công', ASSISTED: 'Có trợ giúp', AUTONOMOUS: 'Tự động',
  PREFLIGHT: 'Kiểm tra điều kiện', PREFLIGHT_READY: 'Đủ điều kiện', PREFLIGHT_BLOCKED: 'Chưa đủ điều kiện',
  OBSERVE: 'Quan sát', OBSERVATION: 'Quan sát', STATE: 'Trạng thái', PLAN: 'Lập kế hoạch',
  PLANNING: 'Lập kế hoạch', SAFETY: 'An toàn', EXECUTE: 'Thực thi', EXECUTION: 'Thực thi',
  EVIDENCE: 'Bằng chứng', VERIFY: 'Xác minh', COMPLETE: 'Kết thúc', RANGE: 'Môi trường',
  PRE_ENGAGEMENT: 'Chuẩn bị', INTELLIGENCE_GATHERING: 'Thu thập thông tin',
  THREAT_MODELING: 'Mô hình hóa mối đe dọa', VULNERABILITY_ANALYSIS: 'Phân tích điểm yếu',
  EXPLOITATION: 'Kiểm chứng tác động', POST_EXPLOITATION: 'Đánh giá sau kiểm chứng', REPORTING: 'Báo cáo',
  DISCOVERY: 'Khám phá', ANALYSIS: 'Phân tích', RECON: 'Thu thập thông tin',
  ALL: 'Tất cả', PLANNER: 'Lập kế hoạch', DISPATCH: 'Gửi yêu cầu',
  MISSING_API_KEY: 'Chưa cấu hình khóa API', BUDGET_EXHAUSTED: 'Đã hết hạn mức của phiên',
  NO_PROGRESS_LOOP: 'Dừng vì không có tiến triển', MAX_DECISIONS_REACHED: 'Đã đạt giới hạn quyết định',
  OPERATOR_STOP: 'Người vận hành đã dừng', KILL_SWITCH_ACTIVE: 'Đã bật dừng khẩn cấp',
  IMPLEMENTED: 'Đã triển khai', VALIDATED: 'Đã kiểm chứng theo phạm vi ghi nhận',
  SPEC_ONLY: 'Mới có đặc tả', DEFERRED: 'Tạm hoãn', UNRESOLVED: 'Chưa kiểm chứng',
  RULE_EXECUTED: 'Đã ghi nhận chế độ quy tắc', LLM_FALLBACK_TO_RULE: 'Chuyển sang quy tắc dự phòng',
  LLM_PROVIDER_NOT_AVAILABLE: 'Dịch vụ mô hình chưa khả dụng', LLM_PROVIDER_RECORDED: 'Đã ghi nhận chế độ mô hình',
  LLM_PROVIDER_EXECUTED: 'Đã ghi nhận chế độ mô hình', HYBRID_NOT_IMPLEMENTED: 'Chế độ kết hợp chưa được nối',
  SIMULATED_FIXTURE: 'Dữ liệu mô phỏng', IMPORTED_OFFLINE: 'Báo cáo nhập ngoại tuyến',
  RUN_STARTED: 'Phiên chạy bắt đầu', RUN_COMPLETED: 'Phiên chạy kết thúc', RUN_FAILED: 'Phiên chạy gặp lỗi',
  AGENT_ITERATION_STARTED: 'Bắt đầu vòng xử lý', PLANNER_STARTED: 'Bắt đầu lập kế hoạch',
  PLANNER_REQUEST_STARTED: 'Đã yêu cầu lập kế hoạch', PLANNER_FAILED: 'Lập kế hoạch gặp lỗi',
  PLANNER_FALLBACK: 'Chuyển sang phương án dự phòng', PLANNER_PROPOSED: 'Đã nhận đề xuất',
  SAFETY_EVALUATION_STARTED: 'Bắt đầu kiểm tra an toàn', SAFETY_DENIED: 'Đã từ chối đề xuất',
  SAFETY_PERMITTED: 'Đã cho phép đề xuất', EVIDENCE_RECORDED: 'Đã ghi bằng chứng',
  EVIDENCE_VERIFIED: 'Đã xác minh bằng chứng', OBSERVATION_RECEIVED: 'Đã nhận quan sát',
  STATE_UPDATED: 'Đã cập nhật trạng thái', AGENT_REPLANNING: 'Đang lập lại kế hoạch',
  STOP_CONDITION_REACHED: 'Đã đạt điều kiện dừng', ACTION_COMPLETED: 'Hành động kết thúc',
  ACTION_FAILED: 'Hành động gặp lỗi', ACTION_DISPATCHED: 'Đã gửi yêu cầu',
  KILL_SWITCH_ACTIVATED: 'Đã bật dừng khẩn cấp', EMERGENCY_STOP_ACTIVATED: 'Đã dừng khẩn cấp',
  'NOT CALLED': 'Chưa được gọi', PERMIT: 'Cho phép', EVALUATING: 'Đang đánh giá',
  TARGET_NOT_ALLOWLISTED: 'Mục tiêu ngoài danh sách cho phép',
  DEMO_DENIAL_PROPOSAL: 'Đề xuất minh họa trường hợp từ chối', POLICY_DENIAL: 'Bị chính sách từ chối',
  DOCKER_AVAILABLE: 'Khả năng truy cập Docker', LOCAL_IMAGES: 'Ảnh môi trường có sẵn',
  CANONICAL_POLICY: 'Chính sách chuẩn', EVIDENCE_STORAGE_WRITABLE: 'Khả năng ghi bằng chứng',
  RUNTIME_SERVICES: 'Dịch vụ thực nghiệm', DOCKER_UNAVAILABLE: 'Docker chưa khả dụng',
  IMAGES_UNAVAILABLE: 'Chưa có ảnh môi trường', POLICY_MISMATCH: 'Chính sách không khớp',
  STORAGE_UNWRITABLE: 'Không thể ghi vào kho lưu trữ', SERVICES_STOPPED: 'Các dịch vụ đã dừng',
  INFO: 'Thông tin', LOW: 'Thấp', MEDIUM: 'Trung bình', HIGH: 'Cao', CRITICAL: 'Nghiêm trọng',
  SECURITY_VERIFICATION: 'Ghi nhận kiểm chứng an toàn', SURFACE_DISCOVERY: 'Ghi nhận bề mặt ứng dụng',
  POLICY_ENFORCEMENT: 'Áp dụng chính sách', DENY_DEMO_COMPLETED: 'Đã kết thúc minh họa từ chối',
  EMERGENCY_KILL_SWITCH_ACTIVATED: 'Đã bật dừng khẩn cấp', DISCOVERY_SURFACE_COMPLETE: 'Đã kết thúc thu thập bề mặt ứng dụng',
  INTENT: 'Ý định thực hiện', RESULT: 'Kết quả', DASHBOARD_RUN_SCOPE: 'Phạm vi của phiên',
  'ecommerce & gateway present': 'Đã có ứng dụng thương mại điện tử và cổng kết nối',
  'Target & Action allowlisted': 'Mục tiêu và hành động thuộc danh sách cho phép',
  'Policy mismatch': 'Chính sách không khớp', 'Services running': 'Các dịch vụ đang chạy',
  'Services currently stopped': 'Các dịch vụ hiện đã dừng',
  'Observed Security Verification': 'Ghi nhận kiểm chứng an toàn',
  'Pause requested': 'Đã yêu cầu tạm dừng', 'Resume requested': 'Đã yêu cầu tiếp tục',
  'Stop requested': 'Đã yêu cầu dừng', 'Run startup rejected': 'Yêu cầu bắt đầu bị từ chối',
  'Proposal approved by operator': 'Người vận hành đã phê duyệt đề xuất',
  'Proposal rejected by operator': 'Người vận hành đã từ chối đề xuất',
  'Pause requested; execution will halt before next boundary': 'Đã yêu cầu tạm dừng trước bước xử lý tiếp theo',
  'Resume requested; execution continuing': 'Đã yêu cầu tiếp tục phiên',
  'Another run is currently active': 'Một phiên khác đang hoạt động',
  'No active runner instance': 'Chưa có phiên thực thi đang hoạt động',
  'Emergency kill switch activated. Dispatches halted.': 'Đã bật dừng khẩn cấp và chặn gửi yêu cầu',
  'All lab services stopped': 'Các dịch vụ thực nghiệm đã dừng',
  'No owned services to stop': 'Không có dịch vụ thuộc phiên này để dừng',
};

export function displayValue(value: string | null | undefined, lang: Language): string {
  if (!value) return '—';
  if (lang !== 'vi') return value;
  const key = Object.prototype.hasOwnProperty.call(viValues, value) ? value : value.toUpperCase();
  const translated = Object.prototype.hasOwnProperty.call(viValues, key) ? viValues[key] : undefined;
  if (translated) return translated;
  if (value.startsWith('APPROVAL_ACTION_MISMATCH_')) return `Phê duyệt không khớp hành động (${value.slice(25)})`;
  for (const [prefix, label] of Object.entries({
    'POLICY_ERROR:': 'Lỗi chính sách', 'SERVICES_UNAVAILABLE:': 'Dịch vụ chưa khả dụng',
    'Discovered Web Endpoint: ': 'Đường dẫn ứng dụng đã ghi nhận', 'Safety Gate Refusal: ': 'Cổng an toàn từ chối',
  })) {
    if (value.startsWith(prefix)) return `${label}: ${displayValue(value.slice(prefix.length).trim(), lang)}`;
  }
  return value;
}

export function displayNotification(value: string, lang: Language): string {
  if (lang !== 'vi') return value;
  const prefixes: Record<string, string> = {
    'Preflight execution failed': 'Kiểm tra điều kiện gặp lỗi',
    'Range Start initiated': 'Đã yêu cầu khởi động môi trường',
    'Range Stop response': 'Phản hồi dừng môi trường',
    'Failed to start lab': 'Không thể khởi động môi trường',
    'Failed to stop lab': 'Không thể dừng môi trường',
    'Autonomous run started': 'Đã bắt đầu phiên',
    'Failed to start run': 'Không thể bắt đầu phiên',
    'Failed to pause run': 'Không thể tạm dừng phiên',
    'Failed to resume run': 'Không thể tiếp tục phiên',
    'Approval failed': 'Phê duyệt không thành công',
    'Rejection failed': 'Không thể ghi nhận từ chối',
    'Failed to stop run': 'Không thể dừng phiên',
    'EMERGENCY KILL SWITCH ACTIVATED': 'Đã bật dừng khẩn cấp',
    'Emergency stop error': 'Dừng khẩn cấp gặp lỗi',
  };
  const separator = value.indexOf(':');
  const prefix = value.slice(0, separator);
  return separator > -1 && Object.prototype.hasOwnProperty.call(prefixes, prefix)
    ? `${prefixes[prefix]}: ${displayValue(value.slice(separator + 1).trim(), lang)}`
    : displayValue(value, lang);
}
