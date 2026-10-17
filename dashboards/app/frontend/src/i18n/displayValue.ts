import type { Language } from './translations';

// Presentation only: never use translated values in requests or audit records.
const viValues: Record<string, string> = {
  SQL_INJECTION: 'Chèn lệnh SQL', SCRIPT_INJECTION: 'Chèn mã XSS / phản chiếu nội dung', PATH_TRAVERSAL: 'Vượt đường dẫn',
  PASSIVE_ANALYSIS: 'Phân tích thụ động', PROPOSED: 'Mới đề xuất, chưa thực thi',
  SIGNAL: 'Có dấu hiệu, chưa xác nhận', NEGATIVE: 'Chưa thấy dấu hiệu trong phép thử',
  INCONCLUSIVE: 'Chưa đủ bằng chứng', VERIFIED_IN_LAB: 'Đã xác nhận trong phạm vi phép thử lab', REFUSED: 'Bị từ chối',
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
  OBJECTIVE_SATISFIED: 'Đã đạt mục tiêu kiểm tra', PROVIDER_UNAVAILABLE_HALT: 'Dừng vì dịch vụ mô hình không khả dụng',
  FALLBACK_NOT_ALLOWED: 'Không cho phép dùng phương án dự phòng', PROVIDER_ERROR_JSONDECODEERROR: 'Phản hồi của dịch vụ mô hình không phải JSON hợp lệ',
  INITIAL_RECONNAISSANCE: 'Thu thập thông tin ban đầu', IDENTIFY_GET_INPUTS: 'Xác định các đầu vào GET',
  PROBE_INPUT: 'Kiểm tra đầu vào đã quan sát', PROBE_UNTESTED_PARAMETER: 'Kiểm tra tham số chưa được thử',
  PROBE_WEB_INPUT: 'Kiểm tra đầu vào web đã quan sát', PROBE_UNTESTED_INPUT: 'Kiểm tra đầu vào chưa được thử',
  PROBE_INPUT_ACTION_WEB_003: 'Đánh giá đầu vào cho phép kiểm tra vượt đường dẫn',
  OPERATOR_STOP: 'Người vận hành đã dừng', KILL_SWITCH_ACTIVE: 'Đã bật dừng khẩn cấp',
  IMPLEMENTED: 'Đã triển khai', VALIDATED: 'Đã kiểm chứng theo phạm vi ghi nhận',
  SPEC_ONLY: 'Mới có đặc tả', DEFERRED: 'Tạm hoãn', UNRESOLVED: 'Chưa kiểm chứng',
  RULE_EXECUTED: 'Đã ghi nhận chế độ quy tắc', LLM_FALLBACK_TO_RULE: 'Chuyển sang quy tắc dự phòng',
  LLM_PROVIDER_NOT_AVAILABLE: 'Dịch vụ mô hình chưa khả dụng', LLM_PROVIDER_RECORDED: 'Đã ghi nhận chế độ mô hình',
  LLM_PROVIDER_EXECUTED: 'Đã ghi nhận chế độ mô hình', HYBRID_NOT_IMPLEMENTED: 'Chế độ kết hợp chưa được nối',
  SIMULATED_FIXTURE: 'Dữ liệu mô phỏng', IMPORTED_OFFLINE: 'Báo cáo nhập ngoại tuyến',
  RUN_STARTED: 'Phiên chạy bắt đầu', RUN_COMPLETED: 'Phiên chạy kết thúc', RUN_FAILED: 'Phiên chạy gặp lỗi',
  RUN_STOP_REQUESTED: 'Đã yêu cầu dừng phiên', RUN_STOPPING: 'Phiên chạy đang dừng', RUN_STOPPED: 'Phiên chạy đã dừng',
  AGENT_ITERATION_STARTED: 'Bắt đầu vòng xử lý', PLANNER_STARTED: 'Bắt đầu lập kế hoạch',
  PLANNER_REQUEST_STARTED: 'Đã gửi yêu cầu đến mô hình lập kế hoạch',
  PLANNER_RESPONSE_RECEIVED: 'Đã nhận phản hồi từ mô hình lập kế hoạch', PLANNER_FAILED: 'Lập kế hoạch gặp lỗi',
  PLANNER_FALLBACK: 'Chuyển sang phương án dự phòng', PLANNER_PROPOSED: 'Đã nhận đề xuất',
  SAFETY_EVALUATION_STARTED: 'Bắt đầu kiểm tra an toàn', SAFETY_DENIED: 'Đã từ chối đề xuất',
  SAFETY_PERMITTED: 'Đã cho phép đề xuất', EVIDENCE_RECORDED: 'Đã ghi bằng chứng',
  EVIDENCE_VERIFIED: 'Đã xác minh bằng chứng', OBSERVATION_RECEIVED: 'Đã nhận quan sát',
  STATE_UPDATED: 'Đã cập nhật trạng thái', AGENT_REPLANNING: 'Đang lập lại kế hoạch',
  STOP_CONDITION_REACHED: 'Đã đạt điều kiện dừng', ACTION_COMPLETED: 'Hành động kết thúc',
  ACTION_DISPATCH_STARTED: 'Bắt đầu gửi yêu cầu hành động', ACTION_FAILED: 'Hành động gặp lỗi',
  ACTION_DISPATCHED: 'Đã gửi yêu cầu hành động', VERIFICATION_COMPLETED: 'Đã hoàn tất kiểm tra lỗ hổng',
  SCANNER_STARTED: 'Bắt đầu phân tích bề mặt', SCANNER_COMPLETED: 'Đã hoàn tất phân tích bề mặt',
  BUDGET_UPDATED: 'Đã cập nhật hạn mức', FINDING_CREATED: 'Đã ghi nhận một phát hiện',
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
  'Bounded differential probing with harmless syntax vectors only; zero arbitrary SQL execution': 'Chỉ dò khác biệt bằng chuỗi cú pháp vô hại trong phạm vi giới hạn; không thực thi câu lệnh SQL tùy ý',
  'Inert marker fixtures only; zero executable JS, zero token extraction, zero browser takeover': 'Chỉ dùng dấu kiểm tra vô hại; không chạy JavaScript, không lấy mã xác thực và không chiếm quyền trình duyệt',
  'Harmless LAB_TRAVERSAL_SENTINEL probe only; zero host file access (/etc/passwd, win.ini forbidden)': 'Chỉ dùng tệp kiểm tra LAB_TRAVERSAL_SENTINEL vô hại; không truy cập tệp hệ thống máy chủ',
  'Requires an observed file/path-like input before dispatch': 'Chỉ thực hiện khi đã quan sát thấy đầu vào kiểu tệp hoặc đường dẫn',
  'Bounded test only': 'Chỉ là phép thử trong phạm vi giới hạn',
};

export function displayValue(value: string | null | undefined, lang: Language): string {
  if (!value) return '—';
  if (lang !== 'vi') return value;
  const key = Object.prototype.hasOwnProperty.call(viValues, value) ? value : value.toUpperCase();
  const translated = Object.prototype.hasOwnProperty.call(viValues, key) ? viValues[key] : undefined;
  if (translated) return translated;
  if (value.includes(':')) {
    const parts = value.split(':');
    const localized = parts.map(part => displayValue(part.trim(), lang));
    if (localized.some((part, index) => part !== parts[index].trim())) return localized.join(': ');
  }
  if (value.startsWith('APPROVAL_ACTION_MISMATCH_')) return `Phê duyệt không khớp hành động (${value.slice(25)})`;
  for (const [prefix, label] of Object.entries({
    'POLICY_ERROR:': 'Lỗi chính sách', 'SERVICES_UNAVAILABLE:': 'Dịch vụ chưa khả dụng',
    'Discovered Web Endpoint: ': 'Đường dẫn ứng dụng đã ghi nhận', 'Safety Gate Refusal: ': 'Cổng an toàn từ chối',
  })) {
    if (value.startsWith(prefix)) return `${label}: ${displayValue(value.slice(prefix.length).trim(), lang)}`;
  }
  const messages: [RegExp, string][] = [
    [/^No SQL syntax anomaly observed/, 'Không phát hiện bất thường cú pháp SQL trong phép thử giới hạn'],
    [/^Inert sentinel is properly HTML-escaped/, 'Dấu kiểm tra vô hại đã được mã hóa HTML an toàn'],
    [/^Inert probe marker was not reflected/, 'Dấu kiểm tra vô hại không bị phản chiếu trong nội dung trả về'],
    [/^Traversal probe was reflected by the response/, 'Chuỗi kiểm tra vượt đường dẫn chỉ bị phản chiếu; chưa chứng minh đọc được tệp'],
    [/^Observed input is not file\/path-like/, 'Đầu vào đã quan sát không phải kiểu tệp hoặc đường dẫn; không thực hiện phép kiểm tra vượt đường dẫn'],
    [/^Path traversal probe rejected with HTTP (\d+)/, 'Phép kiểm tra vượt đường dẫn bị từ chối với mã HTTP $1'],
    [/^No sentinel disclosure observed/, 'Không quan sát thấy nội dung tệp kiểm tra bị lộ'],
  ];
  for (const [pattern, replacement] of messages) {
    if (pattern.test(value)) return value.replace(pattern, replacement);
  }
  return value;
}

const viTools: Record<string, string> = {
  'AutonomousRunner HTTP health probe': 'Bộ kiểm tra tình trạng HTTP',
  ObservationDrivenDiscovery: 'Bộ khám phá dựa trên quan sát',
  PassiveSurfaceAnalyzer: 'Bộ phân tích bề mặt thụ động',
  SafeInputVerificationExecutor: 'Bộ kiểm tra đầu vào SQL an toàn',
  SafeReflectionVerificationExecutor: 'Bộ kiểm tra phản chiếu XSS an toàn',
  SafePathFixtureVerificationExecutor: 'Bộ kiểm tra vượt đường dẫn an toàn',
};

export function displayTool(value: string | null | undefined, lang: Language): string {
  if (!value) return '—';
  return lang === 'vi' ? (viTools[value] ?? value) : value;
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
