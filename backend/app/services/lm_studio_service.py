from __future__ import annotations

import json
from typing import Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


DEFAULT_DATASET_SYSTEM_PROMPT = """You are a Python PowerPoint training sample generator.

Convert the user's raw PPT request into exactly three Markdown sections:

# User Prompt
```text
An improved English PPT generation prompt.
```

# Thinking
```text
A concise implementation plan for python-pptx code generation.
```

# Assistant
```python
Complete runnable python-pptx code.
```

Rules:
* Output only these three sections.
* Do not output JSON, JSONL, ChatML, metadata, or extra text.
* User Prompt must be structured, English, and deterministic.
* Thinking must focus on layout planning, helper functions, asset handling, and syntax-risk prevention.
* Assistant must contain complete runnable Python code, not a minimal skeleton.
* Use English PPT content unless the user explicitly requests another language.
"""

LM_STUDIO_TIMEOUT_SECONDS = 600


class LMStudioError(RuntimeError):
    pass


def _post_chat_completion(endpoint: str, payload: dict) -> dict:
    body = json.dumps(payload).encode("utf-8")
    req = Request(
        endpoint,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with urlopen(req, timeout=LM_STUDIO_TIMEOUT_SECONDS) as res:
            raw = res.read().decode("utf-8")
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise LMStudioError(f"LM Studio HTTP {exc.code}: {detail}") from exc
    except URLError as exc:
        raise LMStudioError(f"LM Studio 연결 실패: {exc.reason}") from exc
    except Exception as exc:  # pragma: no cover - defensive
        raise LMStudioError(f"LM Studio 요청 실패: {exc}") from exc

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise LMStudioError("LM Studio 응답이 JSON 형식이 아닙니다.") from exc
    return parsed


def _extract_content(payload: dict) -> str:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise LMStudioError("LM Studio 응답에 choices가 없습니다.")
    first = choices[0]
    if not isinstance(first, dict):
        raise LMStudioError("LM Studio choices 형식이 올바르지 않습니다.")
    message = first.get("message")
    if not isinstance(message, dict):
        raise LMStudioError("LM Studio 응답에 message가 없습니다.")
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise LMStudioError("LM Studio 응답 content가 비어 있습니다.")
    return content


def generate_markdown_sample(
    *,
    endpoint: str,
    model: str,
    raw_prompt: str,
    system_prompt: Optional[str] = None,
) -> str:
    payload = {
        "model": model,
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": (system_prompt or DEFAULT_DATASET_SYSTEM_PROMPT).strip()},
            {"role": "user", "content": raw_prompt},
        ],
    }
    res = _post_chat_completion(endpoint, payload)
    return _extract_content(res)


def generate_raw_prompt_system_prompt(*, endpoint: str, model: str, topic_seed: str) -> str:
    prompt = f"""Create a system prompt for generating diverse raw PowerPoint requests.

The system prompt will be used to generate training raw prompts for a python-pptx dataset automation tool.
Topic seed: {topic_seed}

The system prompt must instruct the model to:
- create realistic user requests for full PowerPoint presentations
- vary industries, target audiences, slide counts, styles, constraints, and asset requirements
- include deterministic requirements such as output filename, language, slide size, and no external APIs
- avoid producing code
- output raw user prompts only when asked

Return only the system prompt text. Do not wrap it in JSON or markdown.
"""
    payload = {
        "model": model,
        "temperature": 0.3,
        "messages": [
            {"role": "system", "content": "You write concise and precise dataset-generation system prompts."},
            {"role": "user", "content": prompt},
        ],
    }
    res = _post_chat_completion(endpoint, payload)
    return _extract_content(res).strip()


def generate_raw_prompt_list(
    *,
    endpoint: str,
    model: str,
    system_prompt: str,
    prompt_count: int,
    topic_seed: str,
) -> str:
    prompt = f"""Generate {prompt_count} unique raw PowerPoint generation requests.

Topic seed: {topic_seed}

Return valid JSON only in this exact shape:
{{
  "prompts": [
    "raw prompt 1",
    "raw prompt 2"
  ]
}}

Requirements:
- exactly {prompt_count} prompts
- each prompt must be self-contained and suitable as a user request
- do not include markdown fences
- do not include Python code
- prompts must be diverse and detailed enough for generating 3-section markdown dataset samples
"""
    payload = {
        "model": model,
        "temperature": 0.7,
        "max_tokens": 24000,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
    }
    res = _post_chat_completion(endpoint, payload)
    return _extract_content(res)


def repair_markdown_sample(
    *,
    endpoint: str,
    model: str,
    raw_prompt: str,
    previous_markdown: str,
    failed_python_code: str,
    traceback_text: str,
) -> str:
    repair_prompt = f"""The previous output failed runtime validation.

Original request:
{raw_prompt}

Previous markdown output:
{previous_markdown}

Failed python code:
```python
{failed_python_code}
```

Runtime traceback:
```text
{traceback_text}
```

Regenerate the answer in the exact same 3 markdown sections format.
The Assistant python code must be executable and must use supported python-pptx APIs only.
Never use unsupported shape enums like MSO_SHAPE.LINE or MSO_SHAPE.CHECK.
Use slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, ...) for line segments.
"""
    payload = {
        "model": model,
        "temperature": 0.1,
        "messages": [
            {"role": "system", "content": DEFAULT_DATASET_SYSTEM_PROMPT.strip()},
            {"role": "user", "content": repair_prompt},
        ],
    }
    res = _post_chat_completion(endpoint, payload)
    return _extract_content(res)
