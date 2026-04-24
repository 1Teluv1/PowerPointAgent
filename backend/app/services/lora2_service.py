from __future__ import annotations

from app.models.schemas import PlanningSpec, VisualAsset, VisualAssetsBundle


def generate_visual_assets(planning_spec: PlanningSpec) -> VisualAssetsBundle:
    assets = []
    manifest = []
    for slide in planning_spec.slides:
        asset_id = f"slide_{slide.index:02d}_asset"
        svg = (
            "<svg width='640' height='300' xmlns='http://www.w3.org/2000/svg'>"
            "<rect width='640' height='300' fill='#F4F6FA'/>"
            f"<text x='24' y='48' font-size='22'>{slide.title}</text>"
            "</svg>"
        )
        assets.append(
            VisualAsset(
                asset_id=asset_id,
                type="svg",
                layout_code=svg,
                placement={"x": 1.0, "y": 1.5, "w": 8.0, "h": 3.5},
                slide_index=slide.index,
            )
        )
        manifest.append({"asset_id": asset_id, "slide_index": slide.index, "format": "svg"})

    return VisualAssetsBundle(assets=assets, asset_manifest=manifest)
