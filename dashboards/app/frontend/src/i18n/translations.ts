export type Language = 'vi' | 'en';

export interface Translations {
  // App Branding & Navigation
  appTitle: string;
  appSubtitle: string;
  isolatedLab: string;
  tabOverview: string;
  tabRuns: string;
  tabCompare: string;

  // Header status
  runLabel: string;
  notStarted: string;
  planLabel: string;
  killSwitchActive: string;
  safetyGateActive: string;
  liveStream: string;

  // Operational Cards
  cyberRange: string;
  target: string;
  gateway: string;
  activeServices: string;
  dockerUnavailable: string;
  dockerUnavailableDesc: string;
  checked: string;

  autonomousAgent: string;
  state: string;
  phase: string;
  mode: string;
  factsCount: string;
  decisionsCount: string;

  safetyGate: string;
  allowedTargets: string;
  allowedActions: string;
  permitsCount: string;
  denialsCount: string;
  lastDecision: string;

  controlledExecutor: string;
  networkDispatches: string;
  rateLimit: string;
  onBudgetExhaustion: string;

  evidenceVault: string;
  verifiedEvidence: string;
  sha256Integrity: string;
  inspectEvidence: string;

  // Research Boundary
  researchBoundaryTitle: string;
  labIsolationEnforced: string;
  envLabel: string;
  publicInternet: string;
  externalTargets: string;
  execution: string;
  safetyAuthority: string;
  evidence: string;
  notAllowed: string;
  typedBounded: string;
  centralizedGate: string;
  runtimeSourced: string;

  // Pipeline Steps
  pipelineTitle: string;
  stepPreflight: string;
  stepRange: string;
  stepObserve: string;
  stepState: string;
  stepPlan: string;
  stepSafety: string;
  stepExecute: string;
  stepEvidence: string;
  stepVerify: string;
  stepComplete: string;

  // Activity & Events
  currentActivity: string;
  noActivity: string;
  liveEventStream: string;
  clearFeed: string;
  reconnectFeed: string;
  eventsCount: string;

  // Bottom Control Bar
  startAutonomousRun: string;
  pauseRun: string;
  resumeRun: string;
  stopRun: string;
  emergencyStop: string;
  preflightChecks: string;
  startRange: string;
  stopRange: string;
  confirmEmergencyStop: string;

  // Run History Page
  runHistoryTitle: string;
  runHistorySubtitle: string;
  searchPlaceholder: string;
  filterPlanner: string;
  filterMode: string;
  filterState: string;
  allPlanners: string;
  ruleOnly: string;
  llmOnly: string;
  allModes: string;
  allStates: string;
  colRun: string;
  colPlanner: string;
  colMode: string;
  colState: string;
  colIterations: string;
  colDecisions: string;
  colDispatches: string;
  colEvidence: string;
  colDuration: string;
  colActions: string;
  compareSelected: string;
  selectTwoToCompare: string;
  compareNow: string;
  actionReplay: string;
  actionCompare: string;
  totalRuns: string;

  // Run Detail Page (Replay)
  replayBannerTitle: string;
  replayBannerReadOnly: string;
  replayBannerZeroDispatches: string;
  backToHistory: string;
  timelineReplayTitle: string;
  replayStep: string;
  replayPlay: string;
  replayPause: string;
  replayPrev: string;
  replayNext: string;
  replayReset: string;
  replaySpeed: string;
  eventPayloadTitle: string;
  runProvenanceTitle: string;
  decisionOrigin: string;
  fallbackReason: string;
  metricsSummary: string;

  // Run Comparison Page
  comparisonTitle: string;
  comparisonSubtitle: string;
  exportJson: string;
  exportCsv: string;
  comparativeMetricsTitle: string;
  actionTrajectoryTitle: string;
  findingsOverlapTitle: string;
  safetyComplianceTitle: string;
  metricLabel: string;
  deltaLabel: string;
  identicalActions: string;
  trajectoryDivergence: string;
  sharedFindings: string;
  uniqueAFindings: string;
  uniqueBFindings: string;

  // Modals & General
  cancel: string;
  confirm: string;
  close: string;
  loading: string;
  retry: string;
  controlApiOffline: string;
  controlApiOfflineDesc: string;

  // Operational Cards & Evidence extras
  totalArtifacts: string;
  verifiedRecords: string;
  integrityHash: string;
  sha256Valid: string;
  unverified: string;
  latestEvidenceId: string;
  storageMode: string;
  inspect: string;

  // CurrentActivity extras
  currentPhase: string;
  iteration: string;
  activePlanner: string;
  observedFacts: string;
  targetHost: string;
  proposedAction: string;
  safetyGateDecision: string;
  pendingEvaluation: string;
  permitted: string;
  denied: string;
  lastDecisionDetail: string;
  remainingBudget: string;
  lastEvent: string;
  waitingForRun: string;

  // EventFeed extras
  liveEventFeed: string;
  reconnect: string;
  clearStream: string;
  awaitingEvents: string;

  // StartRunModal
  configureLaunchRun: string;
  executionScenarioMode: string;
  executionControlMode: string;
  modeDenyDemoTitle: string;
  modeDenyDemoDesc: string;
  modeAutonomousTitle: string;
  modeAutonomousDesc: string;
  modePresentationTitle: string;
  modePresentationDesc: string;
  controlAutonomousTitle: string;
  controlAutonomousDesc: string;
  controlAssistedTitle: string;
  controlAssistedDesc: string;
  controlManualTitle: string;
  controlManualDesc: string;
  plannerStrategy: string;
  labTarget: string;
  maxDecisionsLimit: string;
  allowFallbackToRule: string;
  singleStepPreview: string;
  launchExecution: string;
  startingRun: string;

  // PreflightModal
  preflightTitle: string;
  executingChecks: string;
  preflightPassedDesc: string;
  preflightBlockedDesc: string;
  identifiedBlockers: string;
  executedChecks: string;
  rerunPreflight: string;
  noPreflightResult: string;

  // ProposalReviewCard
  operatorApprovalRequired: string;
  executionPausedSafeBoundary: string;
  safetyEvaluationProvenance: string;
  decisionRationale: string;
  rejectProposal: string;
  confirmReject: string;
  rejectionReason: string;
  approveAndExecute: string;

  // EvidenceInspectorModal
  evidenceVaultInspector: string;
  findingsAndSurfaces: string;
  cryptographicLedger: string;
  artifactPayloadViewer: string;
  noFindingsRecorded: string;
  noEvidenceRecorded: string;
  decodedContent: string;
  loadingCryptographicRecord: string;
  copy: string;
  copied: string;

  // Presentation Mode & Readiness
  demoView: string;
  operatorView: string;
  presentationMode: string;
  currentStepHero: string;
  currentAction: string;
  safetyGateDecisionHero: string;
  permittedZeroDispatches: string;
  guaranteedZeroDispatches: string;
  simpleMilestones: string;
  detailedTelemetry: string;
  quickScenarios: string;
  scenarioSafeRecon: string;
  scenarioSafetyDeny: string;
  scenarioAssisted: string;
  systemReadiness: string;
  readinessReady: string;
  readinessDegraded: string;
  readinessBlocked: string;
  llmProvenanceHonestBadge: string;
}

export const translations: Record<Language, Translations> = {
  vi: {
    // App Branding & Navigation
    appTitle: 'Trung tâm nghiên cứu',
    appSubtitle: 'An toàn ứng dụng web · Phòng thực nghiệm',
    isolatedLab: 'Môi trường cách ly',
    tabOverview: 'Tổng quan',
    tabRuns: 'Lịch sử phiên',
    tabCompare: 'So sánh',

    // Header status
    runLabel: 'Phiên chạy:',
    notStarted: 'Chưa bắt đầu',
    planLabel: 'Kế hoạch:',
    killSwitchActive: 'Đã bật dừng khẩn cấp',
    safetyGateActive: 'Cổng an toàn đang hoạt động',
    liveStream: 'Sự kiện trực tiếp',

    // Operational Cards
    cyberRange: 'Môi trường thực nghiệm',
    target: 'Mục tiêu',
    gateway: 'Cổng kết nối',
    activeServices: 'Dịch vụ đang chạy',
    dockerUnavailable: 'Docker Không khả dụng',
    dockerUnavailableDesc: 'Cần Docker Desktop để khởi động môi trường thực nghiệm.',
    checked: 'Kiểm tra lúc',

    autonomousAgent: 'Tác nhân tự động',
    state: 'Trạng thái',
    phase: 'Giai đoạn PTES',
    mode: 'Chế độ',
    factsCount: 'Dữ kiện đã ghi nhận',
    decisionsCount: 'Số quyết định',

    safetyGate: 'Cổng An toàn',
    allowedTargets: 'Mục tiêu cho phép',
    allowedActions: 'Hành động cho phép',
    permitsCount: 'Lượt chấp thuận',
    denialsCount: 'Lượt từ chối',
    lastDecision: 'Quyết định gần nhất',

    controlledExecutor: 'Bộ thực thi có kiểm soát',
    networkDispatches: 'Yêu cầu mạng đã gửi',
    rateLimit: 'Giới hạn tần suất',
    onBudgetExhaustion: 'Khi hết hạn mức',

    evidenceVault: 'Kho bằng chứng',
    verifiedEvidence: 'Bằng chứng đã xác minh',
    sha256Integrity: 'Toàn vẹn SHA-256',
    inspectEvidence: 'Xem bằng chứng',

    // Research Boundary
    researchBoundaryTitle: 'Phạm vi nghiên cứu và an toàn',
    labIsolationEnforced: 'Môi trường được cách ly',
    envLabel: 'Môi trường',
    publicInternet: 'Internet Công cộng',
    externalTargets: 'Mục tiêu Bên ngoài',
    execution: 'Thực thi',
    safetyAuthority: 'Thẩm quyền An toàn',
    evidence: 'Bằng chứng',
    notAllowed: 'NGHIÊM CẤM',
    typedBounded: 'ĐỊNH KIỂU / CÓ GIỚI HẠN',
    centralizedGate: 'CỔNG AN TOÀN TRUNG TÂM',
    runtimeSourced: 'Ghi nhận từ phiên chạy',

    // Pipeline Steps
    pipelineTitle: 'Tiến trình xử lý',
    stepPreflight: 'Kiểm tra điều kiện',
    stepRange: 'Môi trường',
    stepObserve: 'Quan sát',
    stepState: 'Trạng thái',
    stepPlan: 'Lập kế hoạch',
    stepSafety: 'An toàn',
    stepExecute: 'Thực thi',
    stepEvidence: 'Bằng chứng',
    stepVerify: 'Xác minh',
    stepComplete: 'Kết thúc',

    // Activity & Events
    currentActivity: 'Hoạt động hiện tại',
    noActivity: 'Hiện chưa có hành động nào đang diễn ra',
    liveEventStream: 'Sự kiện trực tiếp',
    clearFeed: 'Xóa bảng tin',
    reconnectFeed: 'Kết nối lại',
    eventsCount: 'sự kiện',

    // Bottom Control Bar
    startAutonomousRun: 'Bắt đầu Phiên chạy Tự hành',
    pauseRun: 'Tạm dừng Phiên chạy',
    resumeRun: 'Tiếp tục Phiên chạy',
    stopRun: 'Dừng Phiên chạy',
    emergencyStop: 'DỪNG KHẨN CẤP',
    preflightChecks: 'Kiểm tra điều kiện',
    startRange: 'Khởi động môi trường',
    stopRange: 'Dừng môi trường',
    confirmEmergencyStop: 'Xác nhận Dừng Khẩn Cấp?',

    // Run History Page
    runHistoryTitle: 'Lịch sử phiên',
    runHistorySubtitle: 'Xem lại diễn biến, quyết định và bằng chứng của từng phiên đã lưu.',
    searchPlaceholder: 'Tìm mã phiên, kịch bản hoặc mục tiêu…',
    filterPlanner: 'Bộ Lập kế hoạch',
    filterMode: 'Chế độ Điều khiển',
    filterState: 'Trạng thái Phiên chạy',
    allPlanners: 'Tất cả bộ lập kế hoạch',
    ruleOnly: 'Theo quy tắc',
    llmOnly: 'Mô hình ngôn ngữ',
    allModes: 'Tất cả Chế độ',
    allStates: 'Tất cả Trạng thái',
    colRun: 'Phiên chạy & Kịch bản',
    colPlanner: 'Bộ Lập kế hoạch',
    colMode: 'Chế độ',
    colState: 'Trạng thái',
    colIterations: 'Lặp lại',
    colDecisions: 'Quyết định',
    colDispatches: 'Yêu cầu mạng',
    colEvidence: 'Bằng chứng',
    colDuration: 'Thời gian',
    colActions: 'Thao tác',
    compareSelected: 'So sánh các Phiên chạy Đã chọn',
    selectTwoToCompare: 'Chọn hai phiên để đối chiếu số liệu đã ghi nhận.',
    compareNow: 'So sánh Ngay',
    actionReplay: 'Xem lại',
    actionCompare: 'So sánh',
    totalRuns: 'tổng số phiên chạy',

    // Run Detail Page (Replay)
    replayBannerTitle: 'Đang xem lại phiên đã lưu',
    replayBannerReadOnly: 'Chỉ đọc',
    replayBannerZeroDispatches: 'Không gửi yêu cầu đến mục tiêu',
    backToHistory: 'Quay lại Lịch sử',
    timelineReplayTitle: 'Diễn biến phiên',
    replayStep: 'Bước',
    replayPlay: 'Phát',
    replayPause: 'Tạm dừng',
    replayPrev: 'Bước trước',
    replayNext: 'Bước sau',
    replayReset: 'Tua lại đầu',
    replaySpeed: 'Tốc độ',
    eventPayloadTitle: 'Dữ liệu sự kiện',
    runProvenanceTitle: 'Nguồn dữ liệu của phiên',
    decisionOrigin: 'Nguồn quyết định',
    fallbackReason: 'Lý do kích hoạt dự phòng',
    metricsSummary: 'Tổng hợp Chỉ số Thực thi',

    // Run Comparison Page
    comparisonTitle: 'So sánh hai phiên',
    comparisonSubtitle: 'Đối chiếu số liệu, chuỗi hành động và kết quả đã ghi nhận.',
    exportJson: 'Xuất tệp JSON',
    exportCsv: 'Xuất tệp CSV',
    comparativeMetricsTitle: 'Đối chiếu số liệu',
    actionTrajectoryTitle: 'Chuỗi hành động',
    findingsOverlapTitle: 'Các ghi nhận trùng nhau',
    safetyComplianceTitle: 'Kiểm tra an toàn',
    metricLabel: 'Chỉ số',
    deltaLabel: 'Chênh lệch',
    identicalActions: 'Hành động đồng nhất',
    trajectoryDivergence: 'Quỹ đạo phân kỳ',
    sharedFindings: 'Ghi nhận chung',
    uniqueAFindings: 'Riêng cho Phiên chạy A',
    uniqueBFindings: 'Riêng cho Phiên chạy B',

    // Modals & General
    cancel: 'Hủy bỏ',
    confirm: 'Xác nhận',
    close: 'Đóng',
    loading: 'Đang tải...',
    retry: 'Thử lại',
    controlApiOffline: 'Mất kết nối máy chủ',
    controlApiOfflineDesc: 'Không thể lấy dữ liệu từ máy chủ tại:',

    // Operational Cards & Evidence extras
    totalArtifacts: 'Tổng số tệp bằng chứng',
    verifiedRecords: 'Bản ghi đã xác minh',
    integrityHash: 'Mã băm toàn vẹn',
    sha256Valid: 'SHA-256 HỢP LỆ',
    unverified: 'CHƯA XÁC MINH',
    latestEvidenceId: 'Mã bằng chứng mới nhất',
    storageMode: 'Cơ chế lưu trữ',
    inspect: 'Kiểm tra',

    // CurrentActivity extras
    currentPhase: 'Giai đoạn Hiện tại',
    iteration: 'Vòng lặp',
    activePlanner: 'Bộ Lập kế hoạch',
    observedFacts: 'Tri thức Đã ghi nhận',
    targetHost: 'Máy chủ Mục tiêu',
    proposedAction: 'Hành động Đề xuất',
    safetyGateDecision: 'Phán quyết Cổng An toàn',
    pendingEvaluation: 'CHỜ ĐÁNH GIÁ',
    permitted: 'ĐÃ PHÊ DUYỆT',
    denied: 'BỊ TỪ CHỐI',
    lastDecisionDetail: 'Chi tiết Quyết định Trước:',
    remainingBudget: 'Hạn mức còn lại',
    lastEvent: 'Sự kiện Gần nhất:',
    waitingForRun: 'Đang chờ khởi tạo phiên chạy',

    // EventFeed extras
    liveEventFeed: 'Luồng Sự kiện Trực tiếp',
    reconnect: 'Kết nối lại',
    clearStream: 'Xóa luồng',
    awaitingEvents: 'Chưa nhận được sự kiện của phiên.',

    // StartRunModal
    configureLaunchRun: 'Cấu hình & Bắt đầu Phiên chạy Tự hành',
    executionScenarioMode: 'Kịch bản Thực thi',
    executionControlMode: 'Chế độ Điều khiển Thực thi',
    modeDenyDemoTitle: 'Minh họa từ chối ngoài phạm vi',
    modeDenyDemoDesc: 'Đề xuất mục tiêu ngoài phạm vi (lab-not-approved). Kiểm chứng Cổng An toàn chặn đứng trước khi thực thi. Đảm bảo 0 lượt phát mạng.',
    modeAutonomousTitle: 'Phiên tự động',
    modeAutonomousDesc: 'Thực hiện chu trình tự hành khép kín: Quan sát -> Trạng thái -> Kế hoạch -> Kiểm tra an toàn -> Thực thi -> Ghi bằng chứng -> Xác minh toàn vẹn. Cần môi trường Docker hoạt động.',
    modePresentationTitle: 'Phiên trình diễn',
    modePresentationDesc: 'Kịch bản trình diễn tiêu chuẩn với token ủy quyền sẵn, giới hạn tần suất chặt chẽ và xác thực biên an toàn.',
    controlAutonomousTitle: 'Tự động',
    controlAutonomousDesc: 'Thực thi khép kín toàn bộ khi được Cổng An toàn cho phép',
    controlAssistedTitle: 'Có trợ giúp',
    controlAssistedDesc: 'Tự động đọc an toàn, các hành động chủ động cần người vận hành phê duyệt',
    controlManualTitle: 'Thủ công',
    controlManualDesc: 'Chờ phê duyệt rõ ràng từ người vận hành cho từng hành động riêng lẻ',
    plannerStrategy: 'Bộ lập kế hoạch',
    labTarget: 'Mục tiêu thực nghiệm',
    maxDecisionsLimit: 'Giới hạn Quyết định Tối đa',
    allowFallbackToRule: 'Cho phép dự phòng theo quy tắc khi mô hình ngôn ngữ gặp lỗi',
    singleStepPreview: 'Xem trước một bước',
    launchExecution: 'Bắt đầu Thực thi',
    startingRun: 'Đang khởi tạo...',

    // PreflightModal
    preflightTitle: 'Kiểm tra điều kiện môi trường',
    executingChecks: 'Đang thực hiện các kiểm tra môi trường thực tế...',
    preflightPassedDesc: 'Tất cả điều kiện tiên quyết của môi trường đã đáp ứng đầy đủ',
    preflightBlockedDesc: 'Môi trường chưa đáp ứng đủ điều kiện. Xem chi tiết bên dưới.',
    identifiedBlockers: 'Các rào cản được phát hiện',
    executedChecks: 'Các phép kiểm tra đã thực thi',
    rerunPreflight: 'Kiểm tra lại',
    noPreflightResult: 'Chưa có kết quả kiểm tra. Nhấn Kiểm tra lại để xác thực.',

    // ProposalReviewCard
    operatorApprovalRequired: 'Yêu cầu Phê duyệt từ Người Vận hành',
    executionPausedSafeBoundary: 'Thực thi tạm dừng tại biên giới an toàn, chờ quyết định từ người vận hành',
    safetyEvaluationProvenance: 'Đánh giá An toàn & Nguồn gốc',
    decisionRationale: 'Căn cứ Quyết định / Cơ sở Quan sát',
    rejectProposal: 'Từ chối Đề xuất',
    confirmReject: 'Xác nhận Từ chối',
    rejectionReason: 'Lý do Từ chối',
    approveAndExecute: 'Phê duyệt & Thực thi',

    // EvidenceInspectorModal
    evidenceVaultInspector: 'Kiểm tra bằng chứng',
    findingsAndSurfaces: 'Các ghi nhận',
    cryptographicLedger: 'Danh sách bằng chứng',
    artifactPayloadViewer: 'Nội dung bằng chứng',
    noFindingsRecorded: 'Chưa có ghi nhận cho phiên này.',
    noEvidenceRecorded: 'Chưa có bằng chứng được ghi lại.',
    decodedContent: 'Nội dung bản ghi',
    loadingCryptographicRecord: 'Đang tải bản ghi…',
    copy: 'Sao chép',
    copied: 'Đã chép',

    // Presentation Mode & Readiness
    demoView: 'Thuyết trình',
    operatorView: 'Chi tiết',
    presentationMode: 'Chế độ Thuyết trình',
    currentStepHero: 'Bước Thực thi Hiện tại',
    currentAction: 'Hành động Đang thực hiện',
    safetyGateDecisionHero: 'Quyết định Cổng An toàn',
    permittedZeroDispatches: 'CHẤP THUẬN — Phát lệnh HTTP an toàn',
    guaranteedZeroDispatches: 'TỪ CHỐI — ĐẢM BẢO 0 LƯỢT PHÁT MẠNG RA NGOÀI',
    simpleMilestones: 'Các mốc chính',
    detailedTelemetry: 'Toàn bộ sự kiện',
    quickScenarios: 'Kịch bản trình diễn',
    scenarioSafeRecon: 'Kịch bản 1: Thăm dò An toàn (Tự hành)',
    scenarioSafetyDeny: 'Kịch bản 2: Cổng An toàn Từ chối Vi phạm',
    scenarioAssisted: 'Kịch bản 3: Chế độ Trợ lý Có Phê duyệt',
    systemReadiness: 'Độ Sẵn sàng Hệ thống',
    readinessReady: 'Sẵn sàng trình diễn',
    readinessDegraded: 'Có thể xem lại lịch sử',
    readinessBlocked: 'BỊ CHẶN BỞI LỖI',
    llmProvenanceHonestBadge: 'Mô hình ngôn ngữ chưa chạy — chưa cấu hình khóa API',
  },
  en: {
    // App Branding & Navigation
    appTitle: 'Autonomous Cyber Range Control Center',
    appSubtitle: 'Research Prototype: Bounded Autonomous Discovery & Policy Enforcement',
    isolatedLab: 'ISOLATED LAB',
    tabOverview: 'Overview',
    tabRuns: 'Runs',
    tabCompare: 'Compare',

    // Header status
    runLabel: 'Run:',
    notStarted: 'NOT STARTED',
    planLabel: 'Plan:',
    killSwitchActive: 'KILL SWITCH ACTIVE',
    safetyGateActive: 'SAFETY GATE ACTIVE',
    liveStream: 'LIVE STREAM',

    // Operational Cards
    cyberRange: 'Cyber Range',
    target: 'Target',
    gateway: 'Gateway',
    activeServices: 'Services Active',
    dockerUnavailable: 'Docker Unavailable',
    dockerUnavailableDesc: 'Start Docker Desktop to run live cyber range',
    checked: 'Checked',

    autonomousAgent: 'Autonomous Agent',
    state: 'State',
    phase: 'PTES Phase',
    mode: 'Mode',
    factsCount: 'Observed Facts',
    decisionsCount: 'Decisions',

    safetyGate: 'Safety Gate',
    allowedTargets: 'Allowed Targets',
    allowedActions: 'Allowed Actions',
    permitsCount: 'Permits',
    denialsCount: 'Denials',
    lastDecision: 'Last Decision',

    controlledExecutor: 'Controlled Executor',
    networkDispatches: 'Network Dispatches',
    rateLimit: 'Rate Limit',
    onBudgetExhaustion: 'On Budget Exhaustion',

    evidenceVault: 'Evidence Vault',
    verifiedEvidence: 'Verified Evidence',
    sha256Integrity: 'SHA-256 VALID',
    inspectEvidence: 'Inspect Evidence',

    // Research Boundary
    researchBoundaryTitle: 'RESEARCH & SAFETY BOUNDARY INVARIANTS',
    labIsolationEnforced: 'LAB ISOLATION ENFORCED',
    envLabel: 'Environment',
    publicInternet: 'Public Internet',
    externalTargets: 'External Targets',
    execution: 'Execution',
    safetyAuthority: 'Safety Authority',
    evidence: 'Evidence',
    notAllowed: 'NOT ALLOWED',
    typedBounded: 'TYPED / BOUNDED',
    centralizedGate: 'CENTRALIZED SAFETY GATE',
    runtimeSourced: 'RUNTIME-SOURCED',

    // Pipeline Steps
    pipelineTitle: 'Autonomous Closed-Loop Pipeline',
    stepPreflight: 'PREFLIGHT',
    stepRange: 'RANGE',
    stepObserve: 'OBSERVE',
    stepState: 'STATE',
    stepPlan: 'PLAN',
    stepSafety: 'SAFETY',
    stepExecute: 'EXECUTE',
    stepEvidence: 'EVIDENCE',
    stepVerify: 'VERIFY',
    stepComplete: 'COMPLETE',

    // Activity & Events
    currentActivity: 'Current Agent Activity',
    noActivity: 'No active command executing at this time',
    liveEventStream: 'Live Runtime Event Stream',
    clearFeed: 'Clear feed',
    reconnectFeed: 'Reconnect',
    eventsCount: 'events',

    // Bottom Control Bar
    startAutonomousRun: 'Start Autonomous Run',
    pauseRun: 'Pause Run',
    resumeRun: 'Resume Run',
    stopRun: 'Stop Run',
    emergencyStop: 'EMERGENCY STOP',
    preflightChecks: 'Preflight Checks',
    startRange: 'Start Range',
    stopRange: 'Stop Range',
    confirmEmergencyStop: 'Confirm Emergency Stop?',

    // Run History Page
    runHistoryTitle: 'Execution Run History',
    runHistorySubtitle: 'Filesystem-backed research experiment index — Auditable, replayable, and comparable',
    searchPlaceholder: 'Search by Run ID, scenario, target...',
    filterPlanner: 'Planner',
    filterMode: 'Control Mode',
    filterState: 'Run State',
    allPlanners: 'All Planners',
    ruleOnly: 'RULE Only',
    llmOnly: 'LLM Only',
    allModes: 'All Control Modes',
    allStates: 'All States',
    colRun: 'Run & Scenario',
    colPlanner: 'Planner',
    colMode: 'Mode',
    colState: 'State',
    colIterations: 'Iterations',
    colDecisions: 'Decisions',
    colDispatches: 'Dispatches',
    colEvidence: 'Evidence',
    colDuration: 'Duration',
    colActions: 'Actions',
    compareSelected: 'Compare Selected Runs',
    selectTwoToCompare: 'Select 2 runs from the list to compare side-by-side',
    compareNow: 'Compare Now',
    actionReplay: 'Replay',
    actionCompare: 'Compare',
    totalRuns: 'total runs',

    // Run Detail Page (Replay)
    replayBannerTitle: 'HISTORICAL REPLAY — NO LIVE EXECUTION',
    replayBannerReadOnly: 'READ-ONLY',
    replayBannerZeroDispatches: 'Zero Network Dispatches',
    backToHistory: 'Back to Run History',
    timelineReplayTitle: 'Timeline Replay',
    replayStep: 'Step',
    replayPlay: 'Play',
    replayPause: 'Pause',
    replayPrev: 'Prev',
    replayNext: 'Next',
    replayReset: 'Reset',
    replaySpeed: 'Speed',
    eventPayloadTitle: 'Event Payload Details',
    runProvenanceTitle: 'Run Provenance & Verification',
    decisionOrigin: 'Decision Origin',
    fallbackReason: 'Fallback Reason',
    metricsSummary: 'Execution Metrics Summary',

    // Run Comparison Page
    comparisonTitle: 'Planner & Run Experiment Comparison',
    comparisonSubtitle: 'Side-by-side analysis of execution metrics, trajectory divergence, and findings coverage',
    exportJson: 'Export JSON',
    exportCsv: 'Export CSV',
    comparativeMetricsTitle: 'Comparative Execution Metrics',
    actionTrajectoryTitle: 'Action Sequence Trajectory Diff',
    findingsOverlapTitle: 'Attack Surface & Findings Overlap',
    safetyComplianceTitle: 'Safety Gate Compliance Diff',
    metricLabel: 'Metric',
    deltaLabel: 'Delta',
    identicalActions: 'Identical Actions',
    trajectoryDivergence: 'Trajectory Divergence',
    sharedFindings: 'Shared Findings',
    uniqueAFindings: 'Unique to Run A',
    uniqueBFindings: 'Unique to Run B',

    // Modals & General
    cancel: 'Cancel',
    confirm: 'Confirm',
    close: 'Close',
    loading: 'Loading...',
    retry: 'Retry Connection',
    controlApiOffline: 'Control API Offline',
    controlApiOfflineDesc: 'Unable to connect to Control API backend at:',

    // Operational Cards & Evidence extras
    totalArtifacts: 'Total Artifacts',
    verifiedRecords: 'Verified Records',
    integrityHash: 'Integrity Hash',
    sha256Valid: 'SHA-256 VALID',
    unverified: 'UNVERIFIED',
    latestEvidenceId: 'Latest Evidence ID',
    storageMode: 'Storage Mode',
    inspect: 'Inspect',

    // CurrentActivity extras
    currentPhase: 'Current Phase',
    iteration: 'Iteration',
    activePlanner: 'Active Planner',
    observedFacts: 'Observed Facts',
    targetHost: 'Target Host',
    proposedAction: 'Proposed Action',
    safetyGateDecision: 'Safety Gate Decision',
    pendingEvaluation: 'PENDING EVALUATION',
    permitted: 'PERMITTED',
    denied: 'DENIED',
    lastDecisionDetail: 'Last Decision Detail:',
    remainingBudget: 'Remaining Budget',
    lastEvent: 'Last Event:',
    waitingForRun: 'Waiting for run initiation',

    // EventFeed extras
    liveEventFeed: 'Live Event Stream',
    reconnect: 'Reconnect',
    clearStream: 'Clear feed',
    awaitingEvents: 'Awaiting structured runtime events...',

    // StartRunModal
    configureLaunchRun: 'Configure & Launch Autonomous Run',
    executionScenarioMode: 'Execution Scenario Mode',
    executionControlMode: 'Execution Control Mode',
    modeDenyDemoTitle: 'Safety Deny Demo',
    modeDenyDemoDesc: 'Proposes an unapproved target (lab-not-approved). Verified that the Safety Gate blocks the action before execution. Zero network dispatch guaranteed.',
    modeAutonomousTitle: 'Autonomous Run',
    modeAutonomousDesc: 'Runs autonomous loop: observe -> state -> plan -> safety check -> execute -> record evidence -> verify integrity. Requires Docker lab services active.',
    modePresentationTitle: 'Presentation Demo',
    modePresentationDesc: 'Standard demo execution utilizing pre-authorized token with fixed rate limiting and safety boundary verification.',
    controlAutonomousTitle: 'Autonomous',
    controlAutonomousDesc: 'Full closed-loop execution when permitted by Safety Gate',
    controlAssistedTitle: 'Assisted',
    controlAssistedDesc: 'Safe read-only auto, active verifications require approval',
    controlManualTitle: 'Manual',
    controlManualDesc: 'Awaits explicit operator approval for every single action',
    plannerStrategy: 'Planner Strategy',
    labTarget: 'Lab Target',
    maxDecisionsLimit: 'Max Decisions Limit',
    allowFallbackToRule: 'Allow fallback to RULE if LLM fails',
    singleStepPreview: 'Single-step Preview Only',
    launchExecution: 'Launch Execution',
    startingRun: 'Starting Run...',

    // PreflightModal
    preflightTitle: 'Cyber Range Preflight Validation',
    executingChecks: 'Executing genuine environment validation checks...',
    preflightPassedDesc: 'All environment prerequisites met for full execution',
    preflightBlockedDesc: 'Prerequisites not satisfied. Deny-demo scenario remains testable',
    identifiedBlockers: 'Identified Blockers',
    executedChecks: 'Executed Validation Checks',
    rerunPreflight: 'Re-run Preflight',
    noPreflightResult: 'No preflight result available. Click Re-run to validate.',

    // ProposalReviewCard
    operatorApprovalRequired: 'Operator Approval Required',
    executionPausedSafeBoundary: 'Execution paused at safe trust boundary awaiting operator decision',
    safetyEvaluationProvenance: 'Safety Evaluation & Provenance',
    decisionRationale: 'Decision Rationale / Observed Basis',
    rejectProposal: 'Reject Proposal',
    confirmReject: 'Confirm Reject',
    rejectionReason: 'Rejection Reason',
    approveAndExecute: 'Approve & Execute',

    // EvidenceInspectorModal
    evidenceVaultInspector: 'Evidence Vault & Findings Inspector',
    findingsAndSurfaces: 'Findings & Surfaces',
    cryptographicLedger: 'Cryptographic Ledger',
    artifactPayloadViewer: 'Artifact Payload Viewer',
    noFindingsRecorded: 'No findings recorded for this run.',
    noEvidenceRecorded: 'No evidence artifacts recorded.',
    decodedContent: 'Decoded Content',
    loadingCryptographicRecord: 'Loading cryptographic record...',
    copy: 'Copy',
    copied: 'Copied',

    // Presentation Mode & Readiness
    demoView: 'Demo View',
    operatorView: 'Operator View',
    presentationMode: 'Presentation Mode',
    currentStepHero: 'Current Execution Step',
    currentAction: 'Active Action',
    safetyGateDecisionHero: 'Safety Gate Decision',
    permittedZeroDispatches: 'PERMITTED — Safe network dispatch allowed',
    guaranteedZeroDispatches: 'DENIED — GUARANTEED 0 OUTBOUND NETWORK DISPATCHES',
    simpleMilestones: 'Key Milestones',
    detailedTelemetry: 'Detailed Telemetry',
    quickScenarios: 'Quick Demo Presets',
    scenarioSafeRecon: 'Preset 1: Safe Recon (Autonomous)',
    scenarioSafetyDeny: 'Preset 2: Safety Gate Refusal (Injection/OOB)',
    scenarioAssisted: 'Preset 3: Assisted Human Approval',
    systemReadiness: 'System Demo Readiness',
    readinessReady: 'READY FOR DEMO',
    readinessDegraded: 'DEGRADED (REPLAY ONLY)',
    readinessBlocked: 'BLOCKED BY ISSUES',
    llmProvenanceHonestBadge: 'LLM PROVIDER E2E NOT RUN — CREDENTIAL NOT CONFIGURED',
  },
};
