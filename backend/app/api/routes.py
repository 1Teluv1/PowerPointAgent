from __future__ import annotations

from pathlib import Path
from typing import Dict

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.core.orchestrator import ARTIFACT_ROOT, run_serial_pipeline
from app.models.schemas import (
    DatasetAutoGenerateRequest,
    DatasetAutoGenerateResponse,
    DatasetPreviewResponse,
    DatasetStatsResponse,
    DatasetUpsertRequest,
    DatasetUpsertResponse,
    JobCreateRequest,
    JobState,
    PythonValidationRequest,
    PythonValidationResponse,
    RawPromptPoolConsumeRequest,
    RawPromptPoolConsumeResponse,
    RawPromptPoolGenerateRequest,
    RawPromptPoolResponse,
)
from app.services.dataset_service import (
    TOOL_ARTIFACT_ROOT,
    auto_generate_dataset_entry,
    consume_raw_prompt_pool,
    generate_raw_prompt_pool,
    get_preview,
    get_raw_prompt_pool,
    get_stats,
    upsert_pair,
    validate_python_and_save_ppt,
)
from app.services.lm_studio_service import LMStudioError

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


@router.post("/tools/dataset", response_model=DatasetUpsertResponse)
def upsert_dataset(payload: DatasetUpsertRequest) -> DatasetUpsertResponse:
    key = upsert_pair(
        payload.user_prompt,
        payload.asset_code,
        payload.python_code,
        payload.asset_system_prompt,
        payload.python_system_prompt,
    )
    validation = validate_python_and_save_ppt(payload.python_code)
    return DatasetUpsertResponse(key=key, asset_updated=True, python_updated=True, validation=validation)


@router.get("/tools/dataset/stats", response_model=DatasetStatsResponse)
def dataset_stats() -> DatasetStatsResponse:
    return DatasetStatsResponse(files=get_stats())


@router.get("/tools/dataset/{dataset_type}/preview", response_model=DatasetPreviewResponse)
def dataset_preview(dataset_type: str, limit: int = 20, query: str = "") -> DatasetPreviewResponse:
    if dataset_type not in {"asset", "python"}:
        raise HTTPException(status_code=400, detail="dataset_type must be 'asset' or 'python'")
    safe_limit = min(max(limit, 1), 200)
    records = get_preview(dataset_type, safe_limit, query)
    file_name = "asset_lora.jsonl" if dataset_type == "asset" else "python_lora.jsonl"
    return DatasetPreviewResponse(file=file_name, records=records)


@router.post("/tools/dataset/python/validate", response_model=PythonValidationResponse)
def validate_python(payload: PythonValidationRequest) -> PythonValidationResponse:
    return validate_python_and_save_ppt(payload.python_code)


@router.post("/tools/dataset/auto-generate", response_model=DatasetAutoGenerateResponse)
def auto_generate_dataset(payload: DatasetAutoGenerateRequest) -> DatasetAutoGenerateResponse:
    return auto_generate_dataset_entry(payload)


@router.post("/tools/dataset/raw-prompts/generate", response_model=RawPromptPoolResponse)
def generate_raw_prompts(payload: RawPromptPoolGenerateRequest) -> RawPromptPoolResponse:
    try:
        return generate_raw_prompt_pool(payload)
    except LMStudioError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/tools/dataset/raw-prompts", response_model=RawPromptPoolResponse)
def raw_prompt_pool() -> RawPromptPoolResponse:
    return get_raw_prompt_pool()


@router.post("/tools/dataset/raw-prompts/consume", response_model=RawPromptPoolConsumeResponse)
def consume_raw_prompts(payload: RawPromptPoolConsumeRequest) -> RawPromptPoolConsumeResponse:
    try:
        return consume_raw_prompt_pool(payload)
    except LMStudioError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/tools/dataset/python-runs/{run_id}/pptx")
def download_python_run_pptx(run_id: str) -> FileResponse:
    path = TOOL_ARTIFACT_ROOT / run_id / "output.pptx"
    if not Path(path).exists():
        raise HTTPException(status_code=404, detail="PPT file not found")
    return FileResponse(path, media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation")


@router.get("/tools/dataset/previews/{run_id}/{file_name}")
def download_python_run_preview(run_id: str, file_name: str) -> FileResponse:
    if Path(file_name).name != file_name:
        raise HTTPException(status_code=400, detail="Invalid preview file name")
    path = TOOL_ARTIFACT_ROOT / run_id / "thumbnails" / file_name
    if not Path(path).exists():
        raise HTTPException(status_code=404, detail="Preview image not found")
    return FileResponse(path, media_type="image/png")
