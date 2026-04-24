# Contract Versioning Policy

## Scope
- This policy applies to `planning_spec`, `visual_assets_bundle`, and `ppt_code_bundle`.

## Versioning
- Use `MAJOR.MINOR.PATCH`.
- Increment:
  - MAJOR: breaking schema change.
  - MINOR: backward-compatible field addition.
  - PATCH: docs/examples-only updates.

## Compatibility Rules
- Backend accepts the current MAJOR and one previous MAJOR in read mode.
- Writer modules (Planner/LoRA2/LoRA3) always emit current MAJOR.
- Remove deprecated fields only in next MAJOR.

## Validation Rules
- Validate every stage output against JSON schema before forwarding to next stage.
- On validation failure:
  - stop pipeline,
  - store offending payload,
  - return contract error to job logs.

## Contract Files
- `contracts/schemas/pipeline.contract.v1.json`: pipeline-wide contract.
- Future major revisions should create `pipeline.contract.v2.json` and migration notes.
