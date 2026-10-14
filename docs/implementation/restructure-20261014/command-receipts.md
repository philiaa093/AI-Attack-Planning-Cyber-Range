# Command receipts

| Invocation | Exit | Observation | Output |
|---|---:|---|---|
| `python -B -m unittest discover -s tests/runtime -p test_*.py` | 0 | 437 tests PASS | [output](runtime-final.txt) |
| `python -B -m unittest discover -s tests/backend -p test_*.py` | 0 | 74 tests PASS | [output](backend-after.txt) |
| `python -B -m unittest discover -s tests/unit -p test_*.py` | 0 | 143 tests PASS | [output](unit-final.txt) |
| `python -B -m unittest discover -s tests/safety -p test_*.py` | 0 | 31 tests PASS | [output](safety-final.txt) |
| `python -B -m unittest discover -s tests/contracts -p test_*.py` | 0 | 12 tests PASS | [output](contracts-final.txt) |
| `python -B -m unittest discover -s tests/planner -p test_*.py` | 0 | 16 tests PASS | [output](planner-final.txt) |
| `python -B -m unittest discover -s tests/evaluation -p test_*.py` | 0 | 7 tests PASS | [output](evaluation-final.txt) |
| `python -B -m unittest discover -s tests/pentest -p test_*.py` | 0 | 22 tests PASS | [output](pentest-final.txt) |
| `python -B -m unittest discover -s tests/scaffold -p test_*.py` | 0 | 49 tests PASS | [output](scaffold-complete.txt) |
| `python -B -m unittest discover -s scripts/demo -p test_*.py` | 0 | 21 tests PASS | [output](demo-final.txt) |
| `python -B -m unittest discover -s tests -p test_scaffold.py` | 0 | 1 test PASS | [output](root-scaffold.txt) |
| `python -B - (stdlib unittest driver, explicit exclusion of test_runtime_lifecycle.py)` | 0 | 142 integration tests PASS | [output](integration-supported.txt) |
| `python -B -m unittest discover -s tests/integration -p test_*.py` | 1 | 142 tests pass; legacy import fails | [output](integration-after.txt) |
| `python -B -m unittest test_runtime_lifecycle (isolated pre-move source copy)` | 1 | Pre-existing missing runtime.evidence | [output](legacy-baseline.txt) |
| `python -B scripts/validation/validate_scaffold.py` | 0 | SCAFFOLD VALID before receipt files added | [output](gate-complete.txt) |
| `python -B -m runtime.evaluation.evaluate_all --help` | 0 | Entry point resolves | [output](entrypoint-help.txt) |
| `python -B -m runtime.lab.cli --help` | 0 | Entry point resolves | [output](lab-entrypoint-help.txt) |
| `python -B -m runtime.audit.generate_audit_package --help` | 0 | Entry point resolves | [output](audit-entrypoint-help.txt) |
| `npm run typecheck; npm test; npm run build (frontend cwd)` | 0 | TypeScript, 37 tests, build PASS | [output](frontend-receipt.txt) |
| `git diff --check` | 0 | Clean whitespace | [output](whitespace-final.txt) |

Integration supported driver: discover each sorted tests/integration/test_*.py module except test_runtime_lifecycle.py, combine suites and run TextTestRunner. Full discovery fails; it is not described as PASS. Intermediate failed attempts are retained in separate output files.
