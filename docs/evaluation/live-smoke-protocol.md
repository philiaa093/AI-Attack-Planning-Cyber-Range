# Live Smoke Test Protocol for Real LLM Provider (Development Only)

> Status: `REAL_PROVIDER_LIVE_SMOKE_PENDING_AUTHORIZATION`  
> Target: Development Scenario `S1` Only  
> Constraint: Strictly Bounded Tokens, No Prompt Tuning, Isolated Results Directory  

---

## 1. Safety & Experimental Invariants

1. **Explicit Authorization Required**: Live inference against external or local LLM endpoints consumes tokens/compute and must be explicitly authorized by the researcher/operator.
2. **Zero Held-Out Contamination**: Live smoke testing is strictly confined to development scenario `scenario_s1_straight.json` (`S1`). Access to held-out test scenarios `H01–H12` is unconditionally blocked.
3. **Bounded Execution Limits**:
   - Maximum planning steps: 5 steps.
   - Maximum tokens ceiling: 1,000 total tokens (input + output).
   - Maximum HTTP attempts: 10 attempts.
   - Timeout: 30.0s per request (frozen `CONTROLLED_INFERENCE_CONFIG_V1`).
4. **Frozen Policy Integrity**: No prompt modification, system prompt tuning, temperature alterations, or hybrid scoring weight modifications are permitted before, during, or after the smoke test.
5. **Storage Isolation**: Results of the smoke test are written strictly to `evaluation/results/smoke/` and must NEVER be mixed with official benchmark results in `evaluation/results/`.

---

## 2. Pre-requisite Configuration

The adapter dynamically resolves user-configured models via CLI overrides, `ProfileStore` (`.env`), or standard environment variables.

### Option A: Local Self-Hosted Endpoint (vLLM, Ollama, TGI - Keyless)
```bash
# Example for local Ollama running Qwen or Llama 3
export LLM_PROVIDER="openai-compatible"
export LLM_MODEL="llama3.1:8b-instruct-q8_0"
export LLM_API_BASE="http://127.0.0.1:11434/v1"
# No API key required for loopback endpoints (127.0.0.1, localhost, ::1)
```

### Option B: Remote OpenAI-Compatible Endpoint
```bash
export LLM_PROVIDER="openai-compatible"
export LLM_MODEL="your-model-id"
export LLM_API_BASE="https://api.openai.com/v1"
export OPENAI_API_KEY="sk-..."
```

### Option C: Remote Anthropic Endpoint
```bash
export LLM_PROVIDER="anthropic"
export LLM_MODEL="claude-3-5-sonnet-20241022"
export ANTHROPIC_API_KEY="sk-ant-..."
```

---

## 3. Execution Procedure

Execute the bounded live smoke test using Python directly:

```python
import os
from pathlib import Path
from runtime.planners.real_provider_adapter import (
    RealLLMProviderAdapter,
    RealLLMProviderConfig,
    ProviderBudgetGuard,
    ProviderBudgetLimits,
)
from runtime.orchestration.planner_runner import PlannerEpisodeRunner
from runtime.simulation.environment import EpisodeEnvironment
from runtime.simulation.loader import ScenarioLoader
from runtime.planners.llm_planner import LLMPlanner

# 1. Bounded Safety Ceilings
limits = ProviderBudgetLimits(
    max_decisions=5,
    max_logical_calls=5,
    max_http_attempts=10,
    max_input_tokens=800,
    max_output_tokens=200,
    max_consecutive_errors=2,
    max_cumulative_errors=3,
)
guard = ProviderBudgetGuard(limits=limits)

# 2. Resolve Config from User Profile / Environment
cfg = RealLLMProviderConfig.from_profile_or_env()
adapter = RealLLMProviderAdapter(config=cfg, budget_guard=guard)

# 3. Load S1 Development Scenario Only
repo_root = Path.cwd()
scenario_path = repo_root / "runtime" / "simulation" / "fixtures" / "scenarios" / "scenario_s1_straight.json"
scn = ScenarioLoader.load_scenario(str(scenario_path))
env = EpisodeEnvironment(scenario=scn, seed=42)

# 4. Instantiate Planner (LLM baseline or Hybrid)
planner = LLMPlanner(provider=adapter, fallback_to_rule=False)
runner = PlannerEpisodeRunner(env=env, planner=planner, max_steps=5)

# 5. Execute Bounded Smoke
smoke_results_dir = repo_root / "evaluation" / "results" / "smoke"
smoke_results_dir.mkdir(parents=True, exist_ok=True)
result = runner.run()

print(f"Smoke Completed: Steps={result.steps_taken}, Status={result.episode_status}")
print(f"Spend Accounting: {guard.get_spend_accounting_summary()}")
```

---

## 4. Verification Checklist

- [ ] HTTP 200 response received from endpoint with valid JSON decision structure.
- [ ] API keys remain 100% absent from console output, logs, and trace artifacts.
- [ ] Cumulative tokens consumed strictly < 1000.
- [ ] `evaluation/results/` contains 0 `SCN-HELD*` files.
- [ ] Working tree status documented; smoke artifacts kept in `evaluation/results/smoke/`.
