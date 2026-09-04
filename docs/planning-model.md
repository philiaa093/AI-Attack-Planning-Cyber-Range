# Planning Model

Status: `IMPLEMENTED`; runtime: `SPEC_ONLY`.

Planner maps validated observation state to ordered proposals of bounded actions. Proposal contains planner mode, scenario ID, target ID, action IDs, rationale, preconditions, expected observation, risk, and policy context.

Candidate generation stays separate from authorization. Confidence never grants permission. Unknown state yields allowed observation request or refusal, not guessed target or action.

Allowed classes: SQLi, XSS, path traversal. Exact endpoints, payloads, limits, and capabilities are `TBD`.
