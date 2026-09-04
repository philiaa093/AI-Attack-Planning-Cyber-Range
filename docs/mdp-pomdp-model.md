# MDP/POMDP Model

Status: `IMPLEMENTED`; runtime: `SPEC_ONLY`.

MDP state `s` contains approved facts and normalized observations. Action `a` comes from finite catalog. Transition `T(s,a,s')` is scenario-defined. Reward `R(s,a,s')` measures progress minus safety, cost, and uncertainty penalties. Terminal states represent success, refusal, failure, or budget exhaustion.

POMDP belief `b(s)` represents partial observation. Observation model `O(o|s,a)` updates belief only from approved observations. Uncertainty cannot authorize broader scope; planner requests allowed observation or stops.

Finite horizon, bounded actions, allowlists, rate limits, approval, and fail-closed policy are mandatory. Probabilities, weights, and horizon are `TBD`.
