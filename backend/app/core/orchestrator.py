from __future__ import annotations

import uuid
from pathlib import Path

from app.models.schemas import JobCreateRequest, JobState, JobStatus
from app.services.contract_service import validate_pipeline_contract
from app.services.lora2_service import generate_visual_assets
from app.services.lora3_service import generate_ppt_code, repair_ppt_code
from app.services.planner_service import build_planning_spec
from app.services.runner_service import run_ppt_code

MAX_RETRY = 3
ARTIFACT_ROOT = Path(__file__).resolve().parents[2] / "artifacts"


def run_serial_pipeline(request: JobCreateRequest) -> JobState:
    job_id = str(uuid.uuid4())
    state = JobState(job_id=job_id, status=JobStatus.QUEUED, request=request)

    state.status = JobStatus.PLANNING
    state.planning_spec = build_planning_spec(request)

    state.status = JobStatus.VISUAL_GENERATING
    state.visual_assets_bundle = generate_visual_assets(state.planning_spec)

    state.status = JobStatus.CODE_GENERATING
    state.ppt_code_bundle = generate_ppt_code(state.planning_spec, state.visual_assets_bundle)

    validate_pipeline_contract(
        {
            "planning_spec": state.planning_spec.model_dump(),
            "visual_assets_bundle": state.visual_assets_bundle.model_dump(),
            "ppt_code_bundle": state.ppt_code_bundle.model_dump(),
        }
    )

    job_dir = ARTIFACT_ROOT / job_id
    retries = 0
    while retries <= MAX_RETRY:
        state.status = JobStatus.EXECUTING if retries == 0 else JobStatus.RETRYING
        result = run_ppt_code(job_dir, state.ppt_code_bundle)
        state.runner_result = result
        if result.status == "ok":
            state.status = JobStatus.COMPLETED
            return state
        retries += 1
        if retries > MAX_RETRY:
            state.status = JobStatus.FAILED
            return state
        state.ppt_code_bundle = repair_ppt_code(state.ppt_code_bundle.python_code, result.traceback or "")

    state.status = JobStatus.FAILED
    return state
