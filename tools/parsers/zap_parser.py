"""Kiểm tra report ZAP JSON ngoại tuyến và trả scanner results dạng candidate."""

import math
import json
import re
from urllib.parse import urlsplit

from tools.adapters.base import build_scanner_result, validate_target

MAX_JSON_BYTES = 1024 * 1024
MAX_DEPTH = 16
MAX_SITES = 1
MAX_ALERTS = 1000
MAX_INSTANCES = 2000
MAX_URI_CHARS = 2048

# Chuẩn hóa thứ bậc confidence của ZAP, không phải xác suất đã hiệu chuẩn.
_CONFIDENCE_MAP = {str(code): code / 4 for code in range(5)}
_FINDING_TYPE_MAP = {
    "SQL Injection": "sqli",
    "SQL Injection - MySQL": "sqli",
    "SQL Injection - PostgreSQL": "sqli",
    "Cross Site Scripting": "xss",
    "Cross Site Scripting (Reflected)": "xss",
    "Cross Site Scripting (Persistent)": "xss",
    "Path Traversal": "path-traversal",
}


def _check_json(report):
    """Giới hạn cấu trúc và chuỗi trước khi encoder có thể tạo chunk lớn."""
    remaining = MAX_JSON_BYTES
    ancestors = set()

    def charge(size):
        nonlocal remaining
        remaining -= size
        if remaining < 0:
            raise ValueError("Report JSON vượt giới hạn kích thước")

    def walk(value, depth):
        if depth > MAX_DEPTH:
            raise ValueError("Report JSON vượt giới hạn độ sâu")
        kind = type(value)
        if kind is str:
            charge(2)
            # Đếm trước cả escaping và UTF-8; không encode một chuỗi khổng lồ.
            for char in value:
                number = ord(char)
                if 0xD800 <= number <= 0xDFFF:
                    raise ValueError("Report JSON chứa Unicode không hợp lệ")
                if char in '\"\\':
                    size = 2
                elif number < 32:
                    size = 2 if char in '\b\f\n\r\t' else 6
                else:
                    size = 1 if number < 128 else 2 if number < 2048 else 3 if number < 65536 else 4
                charge(size)
        elif kind in (dict, list):
            if id(value) in ancestors:
                raise ValueError("Report JSON chứa vòng tham chiếu")
            ancestors.add(id(value))
            charge(2 + max(0, len(value) - 1))
            for key, item in value.items() if kind is dict else enumerate(value):
                if kind is dict:
                    if type(key) is not str:
                        raise ValueError("Khóa JSON phải là chuỗi")
                    walk(key, depth + 1)
                    charge(1)
                walk(item, depth + 1)
            ancestors.remove(id(value))
        elif value is None or kind is bool:
            charge(len(json.dumps(value)))
        elif kind in (int, float):
            if kind is float and not math.isfinite(value):
                raise ValueError("Report JSON chứa số không hữu hạn")
            try:
                charge(len(str(value)))
            except ValueError:
                raise ValueError("Số JSON không hợp lệ hoặc quá lớn") from None
        else:
            raise ValueError("Report phải chứa dữ liệu JSON thuần")

    walk(report, 0)
    size = 0
    for chunk in json.JSONEncoder(ensure_ascii=False, allow_nan=False, separators=(',', ':')).iterencode(report):
        size += len(chunk.encode('utf-8'))
        if size > MAX_JSON_BYTES:
            raise ValueError("Report JSON vượt giới hạn kích thước")


def _target(target_id):
    if type(target_id) is not str or not re.fullmatch(r"lab-[a-z0-9-]+", target_id):
        raise ValueError("Target lab không hợp lệ")
    try:
        validate_target(target_id)
    except ValueError:
        raise ValueError("Target không thuộc allowlist") from None


def _port(value):
    if type(value) not in (int, str) or not re.fullmatch(r"[1-9][0-9]{0,4}", str(value)):
        raise ValueError("Port không hợp lệ")
    port = int(value)
    if port > 65535:
        raise ValueError("Port không hợp lệ")
    return port


def _origin(uri, target_id):
    if type(uri) is not str or not 1 <= len(uri) <= MAX_URI_CHARS:
        raise ValueError("URI không hợp lệ hoặc vượt giới hạn")
    if any(char.isspace() or ord(char) < 32 or ord(char) == 127 for char in uri) or '\\' in uri:
        raise ValueError("URI có ký tự mơ hồ")
    try:
        parts = urlsplit(uri)
    except ValueError:
        raise ValueError("URI không hợp lệ") from None
    if parts.scheme not in ("http", "https") or not re.fullmatch(r"lab-[a-z0-9-]+(?::[1-9][0-9]{0,4})?", parts.netloc, re.IGNORECASE):
        raise ValueError("URI phải có HTTP origin lab rõ ràng")
    if parts.hostname != target_id:
        raise ValueError("URI không thuộc target")
    port = _port(parts.netloc.rsplit(':', 1)[1]) if ':' in parts.netloc else (443 if parts.scheme == "https" else 80)
    return parts.scheme, port


def _site_scope(site, target_id):
    hosts = [site[key] for key in ("host", "@host") if key in site]
    if not hosts or any(type(host) is not str or host.lower() != target_id for host in hosts):
        raise ValueError("Site không thuộc target")
    schemes = [site[key] for key in ("scheme", "@scheme") if key in site]
    if "@ssl" in site:
        ssl = site["@ssl"]
        if type(ssl) is bool:
            schemes.append("https" if ssl else "http")
        elif ssl in ("true", "false"):
            schemes.append("https" if ssl == "true" else "http")
        else:
            raise ValueError("Metadata SSL không hợp lệ")
    if any(type(scheme) is not str or scheme not in ("http", "https") for scheme in schemes) or len(set(schemes)) > 1:
        raise ValueError("Metadata scheme không hợp lệ")
    ports = [_port(site[key]) for key in ("port", "@port") if key in site]
    if len(set(ports)) > 1:
        raise ValueError("Metadata port không thống nhất")
    names = [_origin(site[key], target_id) for key in ("name", "@name") if key in site]
    if len(set(names)) > 1:
        raise ValueError("Metadata origin không thống nhất")
    scheme = schemes[0] if schemes else None
    port = ports[0] if ports else None
    if names:
        if (scheme is not None and scheme != names[0][0]) or (port is not None and port != names[0][1]):
            raise ValueError("Metadata origin không thống nhất")
        scheme, port = names[0]
    return scheme, port


def parse_zap_results(zap_output, target_id):
    """Parse JSON đã nạp; không đọc file, chạy ZAP hoặc xác nhận vulnerability.

    ponytail: chỉ một target/report JSON, endpoint_id=null để bỏ secrets trong
    path; XML, provenance và runtime cần phạm vi/phê duyệt riêng.
    """
    _target(target_id)
    if type(zap_output) is not dict:
        raise ValueError("Report ZAP phải là object JSON")
    _check_json(zap_output)
    sites = zap_output.get("site")
    if type(sites) is not list or len(sites) > MAX_SITES:
        raise ValueError("Danh sách site không hợp lệ hoặc vượt giới hạn")
    results = []
    alert_count = instance_count = 0
    for site in sites:
        if type(site) is not dict:
            raise ValueError("Site phải là object")
        scope = _site_scope(site, target_id)
        alerts = site.get("alerts")
        if type(alerts) is not list:
            raise ValueError("Alerts phải là danh sách")
        alert_count += len(alerts)
        if alert_count > MAX_ALERTS:
            raise ValueError("Alerts vượt giới hạn")
        for alert in alerts:
            if type(alert) is not dict or type(alert.get("alert")) is not str or not alert["alert"]:
                raise ValueError("Alert không hợp lệ")
            code = alert.get("confidence", "0")
            if type(code) not in (str, int) or str(code) not in _CONFIDENCE_MAP:
                raise ValueError("Confidence ZAP không hợp lệ")
            uris = []
            if "uri" in alert:
                uris.append(alert["uri"])
            if "instances" in alert:
                instances = alert["instances"]
                if type(instances) is not list or not instances:
                    raise ValueError("Instances phải là danh sách không rỗng")
                for instance in instances:
                    if type(instance) is not dict or "uri" not in instance:
                        raise ValueError("Instance không hợp lệ")
                    uris.append(instance["uri"])
                count = len(instances)
            else:
                count = len(uris)
            instance_count += max(1, count)
            if instance_count > MAX_INSTANCES:
                raise ValueError("Instances vượt giới hạn")
            if not uris:
                raise ValueError("Alert thiếu URI nguồn")
            for uri in uris:
                origin = _origin(uri, target_id)
                if any(expected is not None and actual != expected for actual, expected in zip(origin, scope)):
                    raise ValueError("URI không thuộc origin của site")
            finding_type = _FINDING_TYPE_MAP.get(alert["alert"])
            confidence = _CONFIDENCE_MAP[str(code)]
            if finding_type is not None and confidence > 0:
                for _ in range(count):
                    results.append(build_scanner_result("ZAP", target_id, finding_type, confidence, endpoint_id=None))
    return results
