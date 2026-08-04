"""The analyst layer — deterministic detectors over the audit-lane snapshot.

Build spec: docs/knowledge/2026-08-04-analyst-build-plan.md. Every module here
produces structured *facts* (signals, classifications, metadata rows) from
stored rows — no module in this package calls a model, and no module writes to
the audit snapshot. The LLM memo agent lives on the web side and only ever
*receives* what these emit.

The detectors are the comparability infrastructure the feasibility test said
was missing: unit switches, cross-period restatements, opinion changes,
perimeter changes, and the two headline-conceals-composition divergences
(CAR−CET1, NPL-vs-coverage) that would have caught the Şekerbank case
automatically.
"""
