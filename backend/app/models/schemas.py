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


class DatasetAutoGenerateRequest(BaseModel):
    raw_prompt: str = Field(min_length=1)
    lmstudio_endpoint: str = Field(default="http://localhost:1234/v1/chat/completions", min_length=1)
    lmstudio_model: str = Field(default="local-model", min_length=1)
    max_retries: int = Field(default=2, ge=0, le=5)
    system_prompt: Optional[str] = None


class DatasetAutoAttempt(BaseModel):
    attempt: int
    stage: Literal["generate", "repair"]
    status: Literal["ok", "error"]
    error_type: Optional[str] = None
    traceback: Optional[str] = None
    logs: List[str] = Field(default_factory=list)


class DatasetAutoGenerateResponse(BaseModel):
    status: Literal["ok", "error"]
    key: Optional[str] = None
    generated_markdown: Optional[str] = None
    parsed_user_prompt: Optional[str] = None
    parsed_thinking: Optional[str] = None
    parsed_python_code: Optional[str] = None
    attempts: List[DatasetAutoAttempt] = Field(default_factory=list)
    validation: Optional[PythonValidationResponse] = None
    dataset_row: Optional[Dict[str, Any]] = None
    error_type: Optional[str] = None
    traceback: Optional[str] = None


class RawPromptPoolGenerateRequest(BaseModel):
    lmstudio_endpoint: str = Field(default="http://localhost:1234/v1/chat/completions", min_length=1)
    lmstudio_model: str = Field(default="local-model", min_length=1)
    prompt_count: int = Field(default=100, ge=1, le=200)
    topic_seed: str = Field(default="diverse business PowerPoint presentation requests", min_length=1)


class RawPromptPoolConsumeRequest(BaseModel):
    count: int = Field(default=1, ge=1, le=50)
    lmstudio_endpoint: str = Field(default="http://localhost:1234/v1/chat/completions", min_length=1)
    lmstudio_model: str = Field(default="local-model", min_length=1)
    max_retries: int = Field(default=2, ge=0, le=5)


class RawPromptPoolItem(BaseModel):
    id: str
    index: int
    prompt: str
    status: Literal["pending", "processing", "done", "failed"]
    key: Optional[str] = None
    pptx_download_url: Optional[str] = None
    thumbnail_urls: List[str] = Field(default_factory=list)
    error_type: Optional[str] = None
    traceback: Optional[str] = None


class RawPromptPoolSummary(BaseModel):
    total: int
    pending: int
    processing: int
    done: int
    failed: int


class RawPromptPoolResponse(BaseModel):
    system_prompt: Optional[str] = None
    summary: RawPromptPoolSummary
    items: List[RawPromptPoolItem] = Field(default_factory=list)


class RawPromptPoolConsumeItemResult(BaseModel):
    prompt_id: str
    status: Literal["ok", "error"]
    key: Optional[str] = None
    prompt: str
    pptx_download_url: Optional[str] = None
    thumbnail_urls: List[str] = Field(default_factory=list)
    attempts: List[DatasetAutoAttempt] = Field(default_factory=list)
    error_type: Optional[str] = None
    traceback: Optional[str] = None


class RawPromptPoolConsumeResponse(BaseModel):
    processed: int
    success: int
    failed: int
    summary: RawPromptPoolSummary
    results: List[RawPromptPoolConsumeItemResult] = Field(default_factory=list)
