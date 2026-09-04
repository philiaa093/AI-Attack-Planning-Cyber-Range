# Architecture

Status: `IMPLEMENTED`; runtime: `SPEC_ONLY`.

Scenario registry defines approved lab target and expected outcome. Observation adapter emits typed state. Planner proposes bounded actions through `RULE`, `LLM`, `RL`, or `HYBRID`. Safety gate validates target, action, sequence, rate, budget, and approval. Future executor remains separately approved. Evidence recorder preserves request, decision, observation, hash, and redaction. Evaluator compares evidence with ground truth.

No planner bypasses safety. No untyped action reaches execution. No result claim exists without evidence. Failure paths fail closed.
