from __future__ import annotations

from pathlib import Path
from typing import Dict

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.core.orchestrator import ARTIFACT_ROOT, run_serial_pipeline
from app.models.schemas import JobCreateRequest, JobState

router = APIRouter()
JOB_STORE: Dict[str, JobState] = {}


@router.post("/jobs", response_model=JobState)
def create_job(payload: JobCreateRequest) -> JobState:
    state = run_serial_pipeline(payload)
    JOB_STORE[state.job_id] = state
    return state


@router.get("/jobs/{job_id}", response_model=JobState)
def get_job(job_id: str) -> JobState:
    state = JOB_STORE.get(job_id)
    if not state:
        raise HTTPException(status_code=404, detail="Job not found")
    return state


@router.get("/jobs/{job_id}/artifacts")
def get_artifacts(job_id: str) -> dict:
    state = JOB_STORE.get(job_id)
    if not state:
        raise HTTPException(status_code=404, detail="Job not found")
    return {
        "planning_spec": state.planning_spec.model_dump() if state.planning_spec else None,
        "visual_assets_bundle": state.visual_assets_bundle.model_dump() if state.visual_assets_bundle else None,
        "ppt_code_bundle": state.ppt_code_bundle.model_dump() if state.ppt_code_bundle else None,
        "runner_result": state.runner_result.model_dump() if state.runner_result else None,
    }


@router.get("/jobs/{job_id}/pptx")
def download_pptx(job_id: str) -> FileResponse:
    path = ARTIFACT_ROOT / job_id / "output.pptx"
    if not Path(path).exists():
        raise HTTPException(status_code=404, detail="PPT file not found")
    return FileResponse(path, media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation")
