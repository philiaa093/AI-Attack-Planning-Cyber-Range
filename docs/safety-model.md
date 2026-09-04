# Safety Model

Status: `IMPLEMENTED`; runtime: `SPEC_ONLY`.

Gate order: parse strict schema; confirm lab mode; resolve allowlisted target ID; resolve catalog action ID; check preconditions, sequence, budget, rate, and approval; emit `ALLOW`, `DENY`, or `REVIEW` audit decision. Default is `DENY`.

`DRY_RUN` is proposal-only. SQLi, XSS, and path traversal labels never authorize arbitrary targets. No public target, credential, destructive action, policy bypass, or evidence overwrite.
