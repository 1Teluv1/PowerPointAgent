from __future__ import annotations

from typing import List

from app.models.schemas import JobCreateRequest, PlanningSpec, SlideSpec


def build_planning_spec(request: JobCreateRequest) -> PlanningSpec:
    slides: List[SlideSpec] = []
    for idx in range(1, request.slide_count + 1):
        slides.append(
            SlideSpec(
                index=idx,
                title=f"{request.topic} - Slide {idx}",
                asset_needs=["process_flow"] if idx == 1 else ["chart_or_table"],
                narrative=f"{request.topic}에 대한 핵심 메시지를 {request.audience} 대상 톤({request.tone})으로 설명",
            )
        )

    return PlanningSpec(
        presentation_goal=f"{request.topic} 관련 의사결정 지원",
        tone=request.tone,
        slides=slides,
        lora2_tasks=[
            {
                "slide_index": s.index,
                "asset_needs": s.asset_needs,
                "style": request.tone,
            }
            for s in slides
        ],
        lora3_constraints={
            "library": "python-pptx",
            "serial_processing": True,
        },
    )
