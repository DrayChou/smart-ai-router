# Legacy/Optional Modules

This project defaults to a YAML + tag‑based routing path. The following
modules are kept for compatibility or advanced/experimental scenarios and are
not required in the default flow.

- core/router/*
  - base.py (VirtualModelGroup routing abstractions)
  - strategies/* (non‑default strategy implementations)
- core/routing/*
  - candidate_finder.py, channel_scorer.py, router.py (older refactors)
  - filters.py, size_filters.py (some utilities still used; do not remove)
- core/models/virtual_model.py (VirtualModelGroup data model)

Guidance
- Prefer JSONRouter + services:
  - Tag extraction: core/services/tag_processor.py
  - Scoring: core/services/scoring.py (delegated by JSONRouter)
- Keep provider/channel configuration in YAML (config/router_config.yaml); do
  not introduce a database unless you need advanced multi‑user/admin features.
- If you fork for enterprise use, you can wire database tables and migrate the
  routing path back to DB‑driven configs. Avoid mixing both flows.

Removal Policy
- We keep legacy modules until they are fully unused. Before removal, mark them
  as deprecated in code comments and ensure references are gone.
