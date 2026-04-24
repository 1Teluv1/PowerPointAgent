from app.models.schemas import JobCreateRequest
from app.services.lora2_service import generate_visual_assets
from app.services.lora3_service import generate_ppt_code
from app.services.planner_service import build_planning_spec
from app.services.contract_service import validate_pipeline_contract


def test_pipeline_contract_validation():
    req = JobCreateRequest(topic="테스트", audience="내부", tone="중립", slide_count=2)
    planning = build_planning_spec(req)
    assets = generate_visual_assets(planning)
    code = generate_ppt_code(planning, assets)

    payload = {
        "planning_spec": planning.model_dump(),
        "visual_assets_bundle": assets.model_dump(),
        "ppt_code_bundle": code.model_dump(),
    }
    validate_pipeline_contract(payload)
