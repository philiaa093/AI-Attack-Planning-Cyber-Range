# System Boundaries

Status: `IMPLEMENTED`; runtime: `SPEC_ONLY`.

Inside: approved isolated Web Cyber Range, synthetic observations, typed planner state, bounded action catalog, policy decisions, and redacted evidence.

Outside: public targets, production systems, Internet scanning, credentials, unrestricted shell, dynamic code, arbitrary destinations, destructive operations, and unapproved data.

Trust crossings: scenario/model input to parser; parser to planner; planner to policy; policy to future executor; executor observation to evidence. Validate and canonicalize at each crossing. Fail closed on malformed or missing data.
