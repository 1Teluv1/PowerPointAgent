from __future__ import annotations

from app.core.orchestrator import run_serial_pipeline
from app.models.schemas import JobCreateRequest


def main():
    req = JobCreateRequest(topic="스모크 테스트", audience="개발팀", tone="간결", slide_count=2)
    state = run_serial_pipeline(req)
    print(f"job_id={state.job_id}")
    print(f"status={state.status.value}")
    if state.runner_result:
        print(f"runner_status={state.runner_result.status}")
        print(f"pptx_path={state.runner_result.pptx_path}")


if __name__ == "__main__":
    main()
