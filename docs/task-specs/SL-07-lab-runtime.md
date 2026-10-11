# SL-07 — Product E2E, Docker lab và restore

## Status

`IMPLEMENTED`. Đã hoàn thành cấu hình Docker Compose (`cyber-range/compose.yaml`), Gateway reverse proxy (`cyber-range/runtime/gateway.py`), build image và xác thực trực tiếp trên môi trường live Docker qua kịch bản `scripts/cyber-range/verify_live_docker.py` (8/8 pha PASS) và bộ test tích hợp `tests/integration/test_ecommerce_gateway_e2e.py` (17 tests PASS). Chưa có independent review / approval; không tự nâng `VALIDATED`.

## Purpose

Chứng minh ứng dụng ShopLab chạy đúng qua Reverse Proxy Gateway trong môi trường Docker lab cô lập (`internal: true`), bảo đảm tính bền vững của dữ liệu qua container lifecycle (restart, replacement), khả năng phục hồi baseline an toàn và thu thập đầy đủ receipts thực tế từ Docker engine.

## Background

Sau khi hoàn thiện các tính năng nghiệp vụ từ SL-01 đến SL-06, SL-07 đưa ShopLab vào vận hành thực tế trong cyber-range: target container được cô lập trong mạng nội bộ không có cổng mở ra host, chỉ có thể truy cập qua Gateway loopback `127.0.0.1:18088`. Toàn bộ các tuyên bố về storage durability, session isolation, failure injection và restore được kiểm chứng trực tiếp bằng Docker receipts, không sử dụng mock hay simulation.

## Scope

- Cấu hình hạ tầng: `cyber-range/compose.yaml`, `cyber-range/targets/manifests/targets.json`
- Gateway runtime: `cyber-range/runtime/gateway.py`, `cyber-range/runtime/Dockerfile`
- Target container: `cyber-range/targets/ecommerce/Dockerfile`, `cyber-range/targets/ecommerce/app.py`
- Verification scripts: `scripts/cyber-range/verify_live_docker.py`, `tests/integration/test_ecommerce_gateway_e2e.py`
- Services sở hữu: `lab-ecommerce`, `gateway-ecommerce`

## Out of Scope

Không public bind ra IP mạng ngoài (chỉ loopback `127.0.0.1`), không Internet scanning, không AI exploitation (SL-08), không mount Docker socket, không chạy các lệnh hủy diệt toàn cục (`docker prune`).

## Inputs

Source code ShopLab (SL-01..SL-06), `compose.yaml`, image build contexts cho target và gateway, named volume `ecommerce-data`.

## Outputs

Docker images (`cyber-range-lab-ecommerce:latest`, `cyber-range-gateway:latest`), running containers (`cyber-range-lab-ecommerce-1`, `cyber-range-gateway-ecommerce-1`), receipts kiểm thử live Docker 8/8 pha, receipts teardown và bảo toàn volume.

## Interfaces

- Gateway Ingress: `http://127.0.0.1:18088` (Loopback only).
- Target Internal: `http://lab-ecommerce:8080` (Internal `lab` network only, không có host port binding).
- Gateway Health check: `GET http://127.0.0.1:18088/health` trả về `200 OK` (`{"status": "ok", "target_id": "lab-ecommerce"}`).
- Gateway Error mapping: khi target unreachable, trả về `502 Bad Gateway` an toàn.

## Data Contracts

- Docker Compose v5/v2: Mạng `lab` với cờ `internal: true`.
- Mount Contract: Named volume `ecommerce-data` gắn vào `/app/data` (read-write, phân quyền user `nobody`).
- Receipts: Ghi nhận đầy đủ Container IDs, Image IDs/Digests, HTTP status codes, JSON health payloads, và log xác thực.

## Dependencies

SL-02, SL-03, SL-04, SL-05, SL-06; liên kết TASK-011 và TASK-014.

## Implementation Requirements

1. Topology cô lập: Target `lab-ecommerce` chỉ kết nối vào mạng `lab` (`internal: true`), không mở bất kỳ port nào ra host. Host connection trực tiếp tới port 8080 của target bị từ chối.
2. Gateway Ingress: `gateway-ecommerce` kết nối mạng `ingress` và `lab`, xuất bản duy nhất trên loopback `127.0.0.1:18088:8080`.
3. Persistent Storage: Dữ liệu SQLite (`shoplab.sqlite3`) và hóa đơn (`invoices/`) lưu trên named volume `cyber-range_ecommerce-data` mount tại `/app/data`.
4. Process Restart & Container Replacement: Dữ liệu đơn hàng, đánh giá và hóa đơn tồn tại nguyên vẹn sau khi khởi động lại container (`docker restart`) hoặc thay thế container bằng ID mới (`docker rm -f` + `compose up`).
5. Failure Handling: Khi target container bị dừng (`docker stop`), gateway trả về `502 Bad Gateway` sạch sẽ, không rò rỉ IP hay cấu trúc mạng nội bộ. Khi target bật lại, gateway tự phục hồi.
6. Baseline Restore: Chạy qua ephemeral container (`restore_baseline("/app/data")`), thu hồi toàn bộ session cũ (403), xóa đơn hàng và review thử nghiệm, phục hồi catalog ban đầu.
7. Bounded Teardown: Dừng đúng các owned services (`docker compose stop lab-ecommerce gateway-ecommerce`), bảo toàn named volume.

## Safety Requirements

Chỉ bind loopback `127.0.0.1`. Không mount Docker socket (`/var/run/docker.sock`). Không bind mount nhạy cảm từ host. Chạy container dưới user không đặc quyền `nobody`. Không scan hay kết nối ra Internet.

## Testing Requirements

| Case | Scenario | Expected |
|---|---|---|
| R01 | Health check qua Gateway loopback (`127.0.0.1:18088/health`) | Trả về 200 OK, target_id: lab-ecommerce |
| R02 | Full product flow Client A (Register, Login, Cart, Checkout, Order, Invoice, Review) | 100% các bước thành công qua Gateway |
| R03 | Two client sessions & IDOR isolation (Bob vs Alice) | Sessions độc lập; Bob truy cập đơn hoặc hóa đơn Alice nhận 404; `/admin` trả về 403 |
| R04 | Container restart (`docker restart cyber-range-lab-ecommerce-1`) | Dữ liệu đơn hàng, hóa đơn và review tồn tại nguyên vẹn |
| R05 | Container replacement (`docker rm -f` + `compose up`) | Container ID mới; dữ liệu trên named volume bảo toàn |
| R06 | Target failure injection (Target down -> Gateway response -> Target recover) | Trả về 502 Bad Gateway không leak hostname; phục hồi 200 OK |
| R07 | Restore to seed baseline via ephemeral container | Sessions cũ bị 403; đơn và review reset; catalog gốc bảo toàn |
| R08 | Bounded teardown (`docker compose stop`) | Owned containers chuyển sang Exited; volume được giữ nguyên |

## Acceptance Criteria

Tất cả các pha kiểm thử trên môi trường Docker thật (R01–R08) đều PASS với receipts thực tế từ daemon. Bộ test Gateway E2E `tests/integration/test_ecommerce_gateway_e2e.py` (17 tests) đạt 100% PASS. Kịch bản xác thực `scripts/cyber-range/verify_live_docker.py` hoàn thành trọn vẹn 8/8 pha, exit code 0.

## Evidence Required

Command receipts thực tế:
- `python -B scripts/cyber-range/verify_live_docker.py`: ALL LIVE DOCKER RUNTIME VERIFICATIONS PASSED, exit 0.
- `python -B -m unittest discover -s tests/integration -p "test_ecommerce_gateway_e2e.py"`: 17 tests PASS, exit 0.
- `docker compose -f cyber-range/compose.yaml config`: topology validated.
- `docker inspect`: container IDs, internal network IP, volume mount mode `rw`.
- `python -B scripts/validation/validate_scaffold.py`: SCAFFOLD VALID, exit 0.
Không ghi token, password hoặc dữ liệu nhạy cảm trong receipts.

## Failure Conditions

Target container publish port trực tiếp ra host, gateway lắng nghe trên public interface (`0.0.0.0`), mất dữ liệu sau khi container restart/replacement, rò rỉ topology nội bộ khi 502, hoặc teardown xóa nhầm tài nguyên không liên quan.

## Related Guides

[Cyber Range](../guides/03-cyber-range-fundamentals.md), [Safety](../guides/17-cyber-range-safety.md).

## Related Runbooks

[Start range](../runbooks/start-cyber-range.md), [Validate isolation](../runbooks/validate-isolation.md), [Restore range](../runbooks/restore-range.md), [Stop range](../runbooks/stop-cyber-range.md). Không tự authorize các procedures.

## Related ADRs

[ADR-013](../adr/ADR-013-runtime-vertical-slice.md), [Evidence immutability](../adr/ADR-010-evidence-immutability.md).
