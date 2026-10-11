# Demo giáo viên — ShopLab

## Phạm vi và trạng thái
Demo 8 phút 30 giây: ShopLab thật → observations → discovery → normalization → StateManager → RULE proposal → safety → evidence → lifecycle summary. Chỉ GET trong lab, seed `/`, tối đa 8 requests/pages; không submit forms, scan, exploit, provider Internet hoặc restore.

Root receipts của lần trước đã biến mất; nguyên nhân chưa chứng minh được: `EVIDENCE_DISAPPEARANCE_ROOT_CAUSE=UNRESOLVED`. Không sử dụng các con số lịch sử thiếu receipts để nghiệm thu. Runner hiện ghi append-only tại `scripts/demo/demo-output/<run-id>/`, không dựa vào temp hoặc run cũ. Số resources/requests/forms/facts lấy từ invocation hiện tại.

**Không phải full PTES:** coordinator không được gọi; mọi phase PTES là `NOT_RUN`. Policy exploitation `NOT_AUTHORIZED`, post-exploitation `NOT_RUN`. Không nói target an toàn hay không có vulnerabilities.

## Khả năng hiện có

| Component | Available | Command/API | Demo-ready? | Limitation |
|---|---|---|---|---|
| Docker/ShopLab | Có | Compose lab-ecommerce + gateway-ecommerce | Chỉ READY sau health/current receipt checks | Images local bắt buộc; không build/pull |
| Gateway | Có | http://127.0.0.1:18088 | Health GET qua gate | Configuration check không chứng minh toàn bộ egress |
| Discovery | Có | ObservationDrivenDiscovery.run('/') | Có, bounded | BFS HTML links, metadata forms; không route dictionary |
| Recorder | Có | DurableEvidenceRecorder(...approved_root, exclusive_creation=True) | Có | Unique writes/hash không phải WORM filesystem |
| Normalizer | Có | ObservationNormalizer.normalize | Qua discovery | ENDPOINT/SERVICE facts không phải findings |
| StateManager | Có | apply_observation/decrement_requests/decrement_seconds | Có | Discovery apply đúng một lần; không re-ingest |
| Planner adapter | Có | get_minimized_planner_state | Có | Redacted state, không raw HTML |
| Planner | Có | ObservedStatePlanner.propose | RULE | LLM thật không được gọi |
| Safety gate | Có | CentralizedSafetyGate.dispatch | GET lab đã approved | Proposal evaluator chỉ kiểm tra subset policy |
| Evidence verifier | Có | EvidenceVerifier.verify_directory | Multi-GET test hiện PASS | Bản core đã thay đổi đồng thời, không do demo sửa |
| PTES coordinator | Có | PTESCoordinator.run | Chưa tích hợp | Double apply tại discovery/state adapter; mock restore readiness |
| Fixture | Có | test_professor_demo.py | 21 tests | 16 tests cũ + 5 preservation checks; không live proof |
| Evidence recorder | Có | assessment/ và health/ trong current run | Canonical verifier kiểm lại sau stop | Không mở raw HTTP result trước lớp |
| Demo UI receipt | Có | summary.json + summary.sha256 + post-run-verification.json | Re-open/hash/reference checks | Summary không phải authoritative evidence; không overwrite |

## BEFORE DEMO

- Chạy từ repo gốc `E:\PBL6_FINAL`, không dùng worktree thiếu core untracked.
- Docker Desktop đang hoạt động; hai images local đã có.
- Không chạy `verify_live_docker.py` để trình bày: script đó có business writes/replacement/restore.
- Chuẩn bị browser tại Gateway; không nhập tài khoản hoặc bí mật vào terminal.
- Cờ `--approve-read-only` là xác nhận scope cho invocation này (target lab-ecommerce, GET, seed `/`, budget, thời hạn 180 giây), không suy từ plan approval.

## START / RUN

```powershell
python -B scripts/demo/run_professor_demo.py --mode presentation --approve-read-only --start
```

Giữ website chạy để giảng viên mở home → products → một product detail. Runner chỉ start hai services cố định; existing running services không restart/recreate. Không pull/build, không global down/prune.

Rehearsal có cleanup ngay:

```powershell
python -B scripts/demo/run_professor_demo.py --mode presentation --approve-read-only --start --stop-owned
```

**Lưu ý:** `--stop-owned` chỉ stop service invocation này start. Nếu services đã chạy trước invocation, chúng được giữ nguyên. Không có ownership xuyên invocation.

## PREFLIGHT

Khi services đã chạy:

```powershell
python -B scripts/demo/run_professor_demo.py --dry-run --approve-read-only
```

Preflight này kiểm Docker/images/policy/runtime, destinations writable, imports planner/gate, ghi evidence và GET `/health` qua gate; **không chạy discovery/planner**. Health có recorder/counters riêng, không tính vào seed inventory. `READY_FOR_DEMO` chỉ sau current-run receipt checks; coordinator bị loại khỏi requirements của pipeline này. Không có approval: health `NOT_CHECKED`, exit 2. Runtime đang dừng: `RUNTIME_UNAVAILABLE`, không READY giả. Muốn preflight live trước presentation phải có services đang chạy; presentation với `--start` tự khởi động services stopped.

## DENY DEMO

```powershell
python -B scripts/demo/run_professor_demo.py --mode deny-demo
```

Không cần Docker/approval thật. Synthetic proposal target `lab-not-approved` qua evaluator và gate thật; `DENIED`, `TARGET_NOT_ALLOWLISTED`, dispatch delta 0. Tests đối chiếu HTTP spy/server hit count, không chỉ tin counter.

Có synthetic read-only approved proposal example trước deny: `PERMITTED_PROPOSAL_ONLY`, **không execute**. Các approval/origin/rate checks chưa được proposal evaluator thực hiện là `NOT_EVALUATED`; full dispatch authorization thuộc gate khi discovery.

## FALLBACK OFFLINE

```powershell
python -B scripts/demo/run_professor_demo.py --planner llm-unavailable --allow-rule-fallback --approve-read-only --start --stop-owned
```

Injected provider callable trả unavailable; không đọc API keys, không gửi provider request. Display: `Requested mode: LLM`, `Actual mode: RULE`, `Fallback: PROVIDER_UNAVAILABLE`; provenance canonical vẫn giữ `MOCK_PROVIDER_RETURNED_EMPTY` và nhãn `PROVIDER_NOT_CALLED_OFFLINE_DEMO`. Đây là demonstration lỗi provider, không phải LLM thật. Thiếu `--allow-rule-fallback`: planner dừng `PLANNER_HALTED` và exit 2.

Preview riêng, không thay nghiệm thu đa trang:

```powershell
python -B scripts/demo/run_professor_demo.py --preview-one-page --approve-read-only --start --stop-owned
```

## TIMING / WHAT TO SAY

| Thời gian | Thấy gì | Câu nói ngắn |
|---|---|---|
| 0:00–1:00 | Pipeline và scope | “Planner đề xuất; safety mới có thẩm quyền dispatch.” |
| 1:00–2:00 | Browser home/products/detail | “Đây là ứng dụng ecommerce trong lab, không chỉ fixture HTML.” |
| 2:00–3:30 | Seed `/`, resources/links/forms | “Không cấp route list. Inventory được tạo từ HTML thực sự quan sát.” |
| 3:30–4:30 | 2–4 facts, source IDs, state/budget | “Observation được normalize và cập nhật state đúng một lần.” |
| 4:30–5:30 | RULE proposal và provenance | “Đây là rule baseline; tôi không gọi nó là kết quả LLM.” |
| 5:30–6:30 | Approve proposal-only và deny zero dispatch | “Target ngoài allowlist bị gate từ chối trước HTTP; AI không có toàn quyền.” |
| 6:30–7:30 | Hash/redaction/evidence summary | “Intent được ghi trước request, result trước request kế tiếp; writer hoặc verifier fail thì dừng.” |
| 7:30–8:30 | Lifecycle limitations/Q&A | “PTES coordinator chưa chạy nên không tự biến phase thành completed.” |

Flow: preflight → start owned services → health → bounded discovery/inventory → normalization/state → RULE proposal → proposal-only evaluation → synthetic approve/deny trên gate riêng → evidence verification → pipeline snapshot → stop-owned → kiểm tra bytes/hashes/sentinel/evidence → summary cuối. Cả `safe` và `presentation` dùng cùng pipeline, không có exploit mode.

PTES output: `PTES COORDINATOR: NOT USED IN THIS REHEARSAL`. Nói với giảng viên: “Kiến trúc PTES coordinator đã được phát triển riêng, nhưng trong bản rehearsal này tôi chỉ trình diễn pipeline đã được khóa ổn định: discovery → state → planner → safety → evidence.”

Về AI: “Planner đọc observed state và đề xuất hành động tiếp theo. Quyền thực thi không nằm ở planner mà nằm ở safety gate.” Default `RULE` là deterministic baseline offline, không phải LLM output; provider ngoài chỉ là tùy chọn kiến trúc.

## EXPECTED OUTPUT

- Health PASS chỉ khi GET 200 đã recorded/verified.
- Discovery bounded/partial, forms submitted 0; không dump raw HTML.
- State counts lấy thực tế; SERVICE facts có thể là endpoint-derived, không phải số physical services.
- Planner RULE proposal; budget hết có thể khiến evaluator `DENIED/BUDGET_EXHAUSTED`. Không đổi kết quả cho đẹp.
- Evidence integrity `VERIFIED` chỉ sau verifier thật.
- Summary có UUID/UTC, scope, modes, decisions, counters, refs/hashes, limitations; summary SHA-256 riêng.
- Confirmed findings 0 nghĩa không có confirmation, không nghĩa target secure.

## RECEIPT PRESERVATION

Mỗi invocation dùng UUID mới và exclusive run directory; collision dừng trước dispatch. `summary.json` là presentation summary, không authoritative evidence. Canonical records do `DurableEvidenceRecorder` tạo tại `assessment/` và `health/`; summary liên kết evidence IDs/hashes/record paths.

Trước stop: lưu `pipeline-summary.json` (PENDING hoặc INCOMPLETE), `preservation-before.json` và hash mọi file hiện có. `--stop-owned` chỉ dừng container IDs thuộc invocation, không xóa receipts/evidence/manifest/baseline hoặc volume. Sau stop: re-open files, JSON, hashes, canonical verifier, evidence refs và `boundary.txt`; ghi summary cuối rồi kiểm lại và append `post-run-verification.json`. Lỗi giữ diagnostics và `INCOMPLETE/BLOCKED`, không overwrite summary đã publish; `blocked.json` nếu ghi được báo failure muộn. Exit code và post-run receipt phải được đọc cùng summary.

`receipts_preserved: YES` chỉ là phép đo tại thời điểm check, không WORM hoặc bảo đảm chống thao tác xóa bên ngoài về sau. Sentinel chứng minh boundary receipt không đổi, không chứng minh DB/session/stock reset. Hai rehearsals phải có run IDs riêng, cả hai directories cùng tồn tại và Run 1 hashes không đổi sau Run 2. Không dùng receipt lịch sử thay current run.

## FAILOVER

| Lỗi | Hành vi |
|---|---|
| Docker/images/runtime unavailable | BLOCKED, exit 2; không chuyển sang fixture giả live |
| Provider unavailable | RULE chỉ khi explicit fallback; luôn báo simulation/provenance |
| Discovery HTTP/transport error | Dừng, không proposal tiếp theo |
| Intent evidence failure | 0 HTTP |
| Result evidence failure | Request hiện tại có thể đã gửi; không request tiếp theo |
| Evidence verifier failure | Dừng trước planner; không custom verifier/bypass |
| Receipt write failure | Exit 2 và `WRITE_FAILED`, không durable receipt claim |
| Cleanup identity thay đổi | Không stop nhầm container; `UNRESOLVED` |

## STOP

Ưu tiên rehearsal invocation có `--stop-owned`. Nếu operator đã chủ động start services trước demo và muốn dừng đúng hai services sau phần browser:

```powershell
docker compose -f cyber-range/compose.yaml stop gateway-ecommerce lab-ecommerce
```

Đây là thao tác operator riêng, không receipt ownership từ runner. Giữ named volume; không `down -v`, global prune, xóa DB hoặc evidence.

## RESTORE

Runner không tạo orders/reviews hoặc submit forms, nhưng GET có thể tạo session cookies phía app; không claim sessions reset. Restore là workflow quản trị riêng, cần xác nhận data backup, services stopped/drained và approval. API `restore_baseline('/app/data')` hiện có trong app; tham khảo workflow `scripts/cyber-range/verify_live_docker.py`, **không chạy toàn script làm shortcut**. Verify orders/reviews/sessions/stock và evidence preserved phải có receipt riêng. Trong demo luôn `RESTORE NOT_RUN`.

## PROFESSOR Q&A

1. **AI ở đâu?** Planner nhận observed state và chọn proposal schema-bound; default RULE baseline, chưa gọi LLM thật.
2. **AI đề xuất sai?** Proposal không execute trực tiếp; gate có thể từ chối target/action/approval/origin/budget/kill.
3. **Có dùng LLM thật?** Không trong tranche này. Optional unavailable demo là injected failure, actual RULE được ghi rõ.
4. **Vì sao không exploitation?** Ngoài policy/scope, không cần để chứng minh architecture và safety.
5. **Làm sao biết không biết trước routes?** Seed chỉ `/`; test đổi href route, discovery vẫn tìm từ HTML.
6. **Tránh Internet thế nào?** Origin cố định loopback, same-origin canonicalizer, mỗi request/redirect qua gate; provider không gọi. Chưa gọi configuration check là full egress proof.
7. **Evidence để làm gì?** Truy vết intent/decision/result, provenance, integrity/redaction và xử lý failure trung thực.
8. **Tách planner và safety?** Planning không thể tự cấp quyền; authorization là boundary độc lập.
9. **StateManager làm gì?** Gom normalized facts có source IDs và quản lý remaining budget; không ground truth/source code.
10. **Provider chết?** Halt nếu fallback chưa approved; nếu approved thì actual RULE + reason, không giả LLM success.
11. **Vì sao exploitation BLOCKED/NOT_RUN?** Không capability được cấp quyền. Runner chỉ ghi policy NOT_AUTHORIZED; coordinator phase chưa chạy là NOT_RUN.
12. **Mở rộng thế nào?** Sau core integration fix, reviewed contracts và per-run approval; thêm provider thực/phase exits mà không bypass gate. Không tự thêm action/payload.

## CHECKS / GIỚI HẠN BÀN GIAO

```powershell
python -B -m unittest discover -s scripts/demo -p test_professor_demo.py -v
python -B scripts/validation/validate_scaffold.py
```

Không tự nâng task status, commit hoặc independent-review approval. Validator repo có thể fail vì evidence historical/failed attempts hoặc file do agent khác tạo; bảo toàn evidence, báo exact lỗi thay vì sửa/xóa để xanh. Coordinator double-apply vẫn cần Gemini xử lý trước full PTES integration.

### Rehearsals quan sát ngày 2026-10-11

| Check | Current run ID | Exit | Thời gian CLI |
|---|---|---|---|
| Preflight live | RUN-DEMO-04bc1c3f2fa1422e9a41144d7c292e56 | 0 | 31,463 giây, gồm operator start/stop riêng |
| Presentation 1 | RUN-DEMO-30e86c66403e4625a4ba34bdc3c7bff7 | 0 | 30,350 giây |
| Presentation 2 | RUN-DEMO-52df49e052d04531b82cbeb75f2fc755 | 0 | 36,905 giây |
| Deny riêng | RUN-DEMO-4d9b0fe22bb34fbd88a2fa1fec90965b | 0 | 0,714 giây |

Hai presentations: resources 8, requests 8, forms observed 22, submitted 0, forbidden dispatch counter 0, facts 16, planner RULE, planner dispatch 0, synthetic deny delta 0. Proposal thực tế bị evaluator DENIED do requests budget hết, không đổi kết quả. Đây là measured CLI flow, không phải thời gian đã đo của toàn bộ bài nói/browser; timeline 8:30 là kịch bản trình bày.

Command receipts và sentinel nằm tại `demo-output/BASELINE-8559a32938204fd8803971d94ff8979c/`. `preservation-final.json` ghi sentinel before/after giống nhau, 253 historical evidence files không thiếu/đổi hash, hai services stopped và volume còn tồn tại. Run 1 byte-identical sau Run 2; cả hai directories cùng tồn tại khi kiểm tra. Không suy từ sentinel rằng dữ liệu nghiệp vụ đã reset. Nguyên nhân mất receipts cũ vẫn UNRESOLVED; các runs này là run mới, không tái tạo evidence cũ.

Deny-only chỉ chứng minh ca safety; không đủ để hiển thị live pipeline READY. Chạy preflight/presentation hiện tại để xác nhận readiness trước buổi demo. Không dùng dữ liệu bảng này thay current invocation.
