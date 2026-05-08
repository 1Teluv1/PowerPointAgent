from __future__ import annotations

from pathlib import Path
from typing import List


def export_pptx_thumbnails(pptx_path: Path, output_dir: Path) -> List[Path]:
    if not pptx_path.exists():
        raise FileNotFoundError(f"PPTX 파일을 찾을 수 없습니다: {pptx_path}")

    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        import win32com.client  # type: ignore
    except Exception as exc:
        raise RuntimeError("PPT 미리보기는 Windows PowerPoint COM(win32com)이 필요합니다.") from exc

    app = None
    presentation = None
    try:
        app = win32com.client.Dispatch("PowerPoint.Application")
        presentation = app.Presentations.Open(str(pptx_path.resolve()), WithWindow=False)
        presentation.Export(str(output_dir.resolve()), "PNG")
    finally:
        if presentation is not None:
            presentation.Close()
        if app is not None:
            app.Quit()

    thumbnails = sorted(output_dir.glob("*.PNG"))
    if not thumbnails:
        thumbnails = sorted(output_dir.glob("*.png"))
    return thumbnails
