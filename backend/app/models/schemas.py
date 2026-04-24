from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class JobStatus(str, Enum):
    QUEUED = "queued"
    PLANNING = "planning"
    VISUAL_GENERATING = "visual_generating"
    CODE_GENERATING = "code_generating"
    EXECUTING = "executing"
    RETRYING = "retrying"
    COMPLETED = "completed"
    FAILED = "failed"


class JobCreateRequest(BaseModel):
    topic: str
    audience: str
    tone: str
    slide_count: int = Field(default=10, ge=1, le=50)
    requirements: List[str] = Field(default_factory=list)


class SlideSpec(BaseModel):
    index: int
    title: str
    asset_needs: List[str]
    narrative: str


class PlanningSpec(BaseModel):
    schema_version: str = "1.0.0"
    presentation_goal: str
    tone: str
    slides: List[SlideSpec]
    lora2_tasks: List[Dict[str, Any]]
    lora3_constraints: Dict[str, Any]


class VisualAsset(BaseModel):
    asset_id: str
    type: str
    layout_code: str
    placement: Dict[str, float]
    slide_index: int


class VisualAssetsBundle(BaseModel):
    schema_version: str = "1.0.0"
    assets: List[VisualAsset]
    asset_manifest: List[Dict[str, Any]]


class PPTCodeBundle(BaseModel):
    schema_version: str = "1.0.0"
    python_code: str
    expected_outputs: List[str]


class RunnerResult(BaseModel):
    status: str
    logs: List[str]
    pptx_path: Optional[str] = None
    error_type: Optional[str] = None
    traceback: Optional[str] = None


class JobState(BaseModel):
    job_id: str
    status: JobStatus
    request: JobCreateRequest
    planning_spec: Optional[PlanningSpec] = None
    visual_assets_bundle: Optional[VisualAssetsBundle] = None
    ppt_code_bundle: Optional[PPTCodeBundle] = None
    runner_result: Optional[RunnerResult] = None


class DatasetUpsertRequest(BaseModel):
    user_prompt: str = Field(min_length=1)
    asset_system_prompt: str = Field(min_length=1)
    python_system_prompt: str = Field(min_length=1)
    asset_code: str = Field(min_length=1)
    python_code: str = Field(min_length=1)


class DatasetUpsertResponse(BaseModel):
    key: str
    asset_updated: bool
    python_updated: bool
    validation: Optional["PythonValidationResponse"] = None


class DatasetFileStats(BaseModel):
    name: str
    path: str
    records: int
    size_bytes: int
    updated_at: Optional[str] = None


class DatasetStatsResponse(BaseModel):
    files: List[DatasetFileStats]


class DatasetPreviewResponse(BaseModel):
    file: str
    records: List[Dict[str, Any]]


class PythonValidationRequest(BaseModel):
    python_code: str = Field(min_length=1)


class PythonValidationResponse(BaseModel):
    status: Literal["ok", "error"]
    logs: List[str]
    error_type: Optional[str] = None
    traceback: Optional[str] = None
    pptx_download_url: Optional[str] = None
