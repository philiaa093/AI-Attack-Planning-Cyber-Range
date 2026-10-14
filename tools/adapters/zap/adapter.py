"""ZAP wrapper ngoại tuyến; không có quyền thực thi scanner."""

import re

from tools.adapters.base import BaseAdapter, build_observation, load_request_budget
from tools.parsers.zap_parser import parse_zap_results, _target


class ZapAdapter(BaseAdapter):
    ADAPTER_SOURCE = "ZAP"
    ALLOWED_ACTIONS = {"ACTION-SCAN-001": "SCAN"}

    def __init__(self):
        super().__init__()
        self._max_imports = load_request_budget()["max_actions"]
        if type(self._max_imports) is not int or not 1 <= self._max_imports <= 100:
            raise ValueError("Giới hạn import không hợp lệ")
        self._import_count = 0

    def validate_request(self, action_id, target_id, run_id):
        _target(target_id)
        if type(action_id) is not str or action_id not in self.ALLOWED_ACTIONS:
            raise ValueError("Action không được ZAP wrapper hỗ trợ")
        if type(run_id) is not str or not re.fullmatch(r"RUN-[A-Za-z0-9_-]{1,120}", run_id):
            raise ValueError("Run ID không hợp lệ")
        super().validate_request(action_id, target_id, run_id)

    def execute(self, action_id, target_id, run_id, parameters=None):
        if parameters is not None and type(parameters) is not dict:
            raise ValueError("Parameters phải là object")
        return super().execute(action_id, target_id, run_id, parameters)

    def _run(self, action_id, target_id, run_id, parameters):
        # ponytail: scanner luôn DENIED; runtime cần approval, recorder và review riêng.
        return build_observation(
            observation_id=f"OBS-SCAN-001-{run_id}",
            run_id=run_id,
            action_id=action_id,
            outcome="DENIED",
            new_facts=[],
        ), []

    def import_report(self, report, *, target_id):
        """Trả candidate data; caller giữ provenance, không tạo scan observation."""
        _target(target_id)
        if self._import_count >= self._max_imports:
            raise RuntimeError("Đã hết ngân sách import ngoại tuyến")
        # Tái dùng rate limiter; nhãn riêng không là run ID/action execution.
        self._rate_limiter.acquire("OFFLINE-ZAP-IMPORT", target_id)
        self._import_count += 1
        return parse_zap_results(report, target_id)
