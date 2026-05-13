from __future__ import annotations

import json
import queue
import re
import threading
import time
from typing import Any, Dict, Iterator, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


MANDATORY_PPTX_DATASET_RULES = """Mandatory markdown shape (parser contract — violations cause 섹션 파싱 실패):
* Emit exactly two sections, in order, with these exact single-hash headings on their own lines: `# Thinking`, `# Assistant` (do not use `##` / `###` for these titles).
* Immediately under each heading, open a fenced block: Thinking uses ```text and Assistant uses ```python. Close every block with a line that is only ```.
* Do not insert commentary, blank-heading variants, or different fence languages between the heading and the opening fence.

Mandatory python-pptx correctness:
* Never import `ChartType` from `pptx.enum.chart` — that name does not exist. For `slide.shapes.add_chart`, import and use `from pptx.enum.chart import XL_CHART_TYPE` (e.g. `XL_CHART_TYPE.PIE`, `XL_CHART_TYPE.COLUMN_CLUSTERED`).
* Chart / `ChartData`: series names and labels must be types the library expects (e.g. series title as a single string); do not pass a Python list where a scalar string is required.
* `slide.shapes.title` may be `None` on some layouts. Never assign `slide.shapes.title.text` without checking. Use e.g. `title_shape = slide.shapes.title` then `if title_shape is not None: title_shape.text = ...`, otherwise add a text box or pick a layout that defines a title placeholder.
"""

DEFAULT_DATASET_SYSTEM_PROMPT = """You are a senior Python PowerPoint automation engineer and training sample generator.

Read the user's raw PPT request and output exactly two Markdown sections:

# Thinking

```text
...
```

# Assistant

```python
...
```

Do not output JSON, JSONL, ChatML, metadata, role labels, or the system prompt. Do not add text before # Thinking or after the final Python code block.
Never output inner deliberation, self-talk, or meta reasoning sentences like "I need to...", "I'm realizing...", or "the user wants...".

# Language rules

* The Thinking section must be written in English.
* All presentation content inside the Python code must be written in English.
* Python variable names, function names, slide titles, labels, body text, captions, and placeholder text must be English.
* Preserve the user's original topic and intent.
* Do not generate Korean slide text unless the raw user request explicitly says the final PPT must be in Korean.

Defaults:

* slide count: 6
* output file: output.pptx
* slide size: 16:9 widescreen
* audience: general business audience
* style: clean premium business presentation
* assets: none, placeholder-safe
* language: English

# Thinking rules

Write a concrete pre-code implementation plan in English. The Thinking section must be specific enough to guide a full Python implementation.

The Thinking section must include:

* slide count and one builder function per slide
* deck constants: slide size, palette, fonts, margins, spacing, reusable dimensions
* helper function plan: background, text box, shape, line, card, section label, image/placeholder, footer
* layout plan for each slide, including rows, columns, x/y positions, card sizes, gaps, and alignment
* asset handling plan using os.path.exists and placeholder fallback
* python-pptx API plan using Inches, Pt, RGBColor, MSO_SHAPE, PP_ALIGN, and MSO_ANCHOR when needed
* syntax-risk checks: no undefined names, no pseudo-code, no TODO, no unsupported APIs
* main flow: initialize deck, call every slide builder, save with prs.save(output_file)

The Thinking section must not be a one-line summary. It must be a practical implementation checklist.

# Assistant rules

Output only complete, runnable Python code inside the python block. The code must generate an actual designed PowerPoint deck, not an empty presentation.

Strictly forbidden:

* minimal skeleton code
* only creating Presentation() and saving it
* placeholder-only implementation
* pseudo-code
* TODO comments
* undefined functions
* undefined variables
* explanations inside the Python code
* JSON or JSONL
* Markdown fences inside the Python code

Minimum Python code requirements:

* Import all required python-pptx modules explicitly.
* Define reusable constants for slide size, colors, fonts, margins, and spacing.
* Define a hex_to_rgb() or equivalent color helper.
* Define reusable helper functions, at minimum:

  * set_slide_background()
  * add_text_box()
  * add_card()
  * add_section_label()
  * add_footer()
  * add_image_or_placeholder()
* Define one slide builder function per slide.
* Each slide builder must create real visual content with titles, subtitles, body text, cards, shapes, lines, or decorative elements.
* Every slide must contain meaningful English presentation content derived from the raw prompt.
* Every slide must use explicit coordinates and dimensions.
* Every slide builder must be called from main().
* main() must set 16:9 widescreen dimensions unless otherwise specified.
* main() must save the presentation using the output filename from the raw prompt.

Python/PPT rules:

* Use python-pptx.
* Use explicit imports; no wildcard imports.
* Create a .pptx file when executed.
* Preserve slide count; do not skip slides.
* Use grid, row, column, or matrix layout logic for multi-card slides.
* Use consistent margins, spacing, typography hierarchy, and non-overlapping elements.
* Use only provided asset paths.
* Before image insertion, check os.path.exists(path).
* If an image is missing, draw a styled placeholder instead.
* The script must run successfully even when no assets exist.
* Require no network, external APIs, or external fonts.
* Use safe fonts: Aptos, Calibri, Arial, or Malgun Gothic.
* Use RGBColor only for python-pptx colors.
* Avoid unsupported python-pptx APIs.
* Keep the code self-contained, deterministic, and complete.
* The Python code should usually be at least 180 lines for a 6-slide deck.
* The final Python lines must be exactly:
  if __name__ == "__main__":
      main()

""" + "\n\n" + MANDATORY_PPTX_DATASET_RULES

LM_STUDIO_TIMEOUT_SECONDS = 600
LIVE_ANSWER_QUEUE_SIZE = 1000

DEFAULT_DATASET_RETRY_SYSTEM_PROMPT = """You are a python-pptx repair engineer for a locked training sample.

The User Prompt and Thinking sections are already finalized and FROZEN. You must not reinterpret the topic, slide count, layout plan, filenames, or constraints from them. Your only deliverable is a replacement for the Assistant Python block: one complete, runnable script that implements the frozen Thinking plan and satisfies the frozen User Prompt.

Output rules:
* Return exactly one markdown fenced block: ```python ... ``` containing the full script (imports through if __name__ == "__main__": main()).
* Fix the runtime error in the traceback without changing the deck intent.
* Never import ChartType from pptx.enum.chart — use XL_CHART_TYPE for add_chart.
* slide.shapes.title may be None; never assign .text without checking.
* Chart series names must be strings where the API expects a string, not lists.
* No TODO, no pseudo-code, no markdown fences inside the Python code.
"""

DEFAULT_DATASET_THINKING_RETRY_SYSTEM_PROMPT = """You are a dataset repair engineer for a python-pptx training sample.

The previous markdown output is missing or malformed only in the # Thinking section. Regenerate ONLY the Thinking body from the raw user request and any available locked context.

Output rules:
* Return only the Thinking text body. Do not include # Thinking, markdown fences, JSON, role labels, or commentary.
* Write in English.
* Preserve the raw request's topic, audience, slide count, output filename, visual style, and constraints.
* Produce a concrete pre-code implementation plan for python-pptx.
* Include slide count, one builder function per slide, deck constants, helper functions, per-slide layout positions, asset fallback handling, python-pptx APIs, syntax-risk checks, and main flow.
* Do not output inner deliberation, self-talk, pseudo-code, TODO, or Python code.
"""


def _extract_assistant_python_fence(content: str) -> str:
    text = (content or "").strip()
    if not text:
        return ""
    m = re.search(r"```(?:python)?\s*\r?\n(.*?)\r?\n```", text, re.DOTALL | re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return text


def _extract_thinking_text(content: str) -> str:
    text = (content or "").strip()
    if not text:
        return ""
    section_match = re.search(
        r"(?:^|\n)\#\s*Thinking\s*\n\s*```(?:text)?\s*\r?\n(.*?)\r?\n```",
        text,
        re.DOTALL | re.IGNORECASE,
    )
    if section_match:
        return section_match.group(1).strip()
    fence_match = re.search(r"```(?:text)?\s*\r?\n(.*?)\r?\n```", text, re.DOTALL | re.IGNORECASE)
    if fence_match:
        return fence_match.group(1).strip()
    return re.sub(r"^\#\s*Thinking\s*", "", text, flags=re.IGNORECASE).strip()


def _dataset_system_content(system_prompt: Optional[str]) -> str:
    """Custom pool system prompt is augmented so technical rules are never dropped."""
    extra = MANDATORY_PPTX_DATASET_RULES.strip()
    base = (system_prompt or "").strip()
    if not base:
        return DEFAULT_DATASET_SYSTEM_PROMPT.strip()
    return f"{base}\n\n--- Mandatory python-pptx and markdown output (always follow) ---\n{extra}"


def _merge_error_memory_into_system(system_content: str, error_memory_addon: Optional[str]) -> str:
    """Place error memory before the main system text so the model attends to it first."""
    addon = (error_memory_addon or "").strip()
    if not addon:
        return system_content
    return f"{addon}\n\n---\n\n{system_content.rstrip()}"


class LMStudioError(RuntimeError):
    pass


_LIVE_ANSWER_SUBSCRIBERS: set[queue.Queue] = set()
_LIVE_ANSWER_LOCK = threading.Lock()


def _broadcast_live_answer(event: Dict[str, Any]) -> None:
    event_payload = {
        "timestamp": time.time(),
        **event,
    }
    with _LIVE_ANSWER_LOCK:
        subscribers = list(_LIVE_ANSWER_SUBSCRIBERS)
    for subscriber in subscribers:
        try:
            subscriber.put_nowait(event_payload)
        except queue.Full:
            pass


def subscribe_live_answer_events() -> Iterator[Dict[str, Any]]:
    subscriber: queue.Queue = queue.Queue(maxsize=LIVE_ANSWER_QUEUE_SIZE)
    with _LIVE_ANSWER_LOCK:
        _LIVE_ANSWER_SUBSCRIBERS.add(subscriber)
    try:
        yield {"type": "ready", "stage": "live_answer", "content": ""}
        while True:
            try:
                yield subscriber.get(timeout=15)
            except queue.Empty:
                yield {"type": "heartbeat", "stage": "live_answer", "content": ""}
    finally:
        with _LIVE_ANSWER_LOCK:
            _LIVE_ANSWER_SUBSCRIBERS.discard(subscriber)


def _iter_openai_sse_data(endpoint: str, payload: dict) -> Iterator[str]:
    stream_payload = dict(payload)
    stream_payload["stream"] = True
    body = json.dumps(stream_payload).encode("utf-8")
    req = Request(
        endpoint,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        },
    )
    try:
        with urlopen(req, timeout=LM_STUDIO_TIMEOUT_SECONDS) as res:
            data_lines = []
            while True:
                raw_line = res.readline()
                if not raw_line:
                    break
                line = raw_line.decode("utf-8", errors="replace").rstrip("\r\n")
                if not line:
                    if data_lines:
                        yield "\n".join(data_lines).strip()
                        data_lines = []
                    continue
                if line.startswith("data:"):
                    data_lines.append(line[5:].lstrip())
            if data_lines:
                yield "\n".join(data_lines).strip()
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise LMStudioError(f"LM Studio HTTP {exc.code}: {detail}") from exc
    except URLError as exc:
        raise LMStudioError(f"LM Studio 연결 실패: {exc.reason}") from exc
    except Exception as exc:  # pragma: no cover - defensive
        raise LMStudioError(f"LM Studio 스트리밍 요청 실패: {exc}") from exc


def _post_chat_completion(endpoint: str, payload: dict, *, stage: str = "lm_studio") -> dict:
    _broadcast_live_answer(
        {
            "type": "start",
            "stage": stage,
            "model": payload.get("model"),
            "content": "",
        }
    )
    content_parts = []
    last_payload: Dict[str, Any] = {}
    try:
        for data in _iter_openai_sse_data(endpoint, payload):
            if data == "[DONE]":
                break
            try:
                parsed = json.loads(data)
            except json.JSONDecodeError:
                continue

            if parsed.get("error"):
                message = parsed["error"].get("message", "LM Studio streaming error")
                raise LMStudioError(str(message))

            last_payload = parsed
            delta = ((parsed.get("choices") or [{}])[0].get("delta") or {})
            # reasoning_content is intentionally excluded from final assistant output.
            chunk = delta.get("content") or ""
            if chunk:
                content_parts.append(chunk)
                _broadcast_live_answer(
                    {
                        "type": "delta",
                        "stage": stage,
                        "model": payload.get("model"),
                        "content": chunk,
                    }
                )
    except LMStudioError as exc:
        _broadcast_live_answer(
            {
                "type": "error",
                "stage": stage,
                "model": payload.get("model"),
                "content": str(exc),
            }
        )
        raise

    content = "".join(content_parts)
    _broadcast_live_answer(
        {
            "type": "end",
            "stage": stage,
            "model": payload.get("model"),
            "content": "",
        }
    )
    return {
        "id": last_payload.get("id"),
        "object": "chat.completion",
        "model": last_payload.get("model") or payload.get("model"),
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": ((last_payload.get("choices") or [{}])[0]).get("finish_reason"),
            }
        ],
    }


def post_chat_completion_stream(endpoint: str, payload: dict) -> Iterator[bytes]:
    for data in _iter_openai_sse_data(endpoint, payload):
        yield f"data: {data}\n\n".encode("utf-8")
        if data == "[DONE]":
            return


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
    error_memory_addon: Optional[str] = None,
) -> str:
    system = _merge_error_memory_into_system(
        _dataset_system_content(system_prompt),
        error_memory_addon,
    )
    payload = {
        "model": model,
        "temperature": 0.1,
        "repeat_penalty": 1.1,
        "max_tokens": 12000,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": raw_prompt},
        ],
    }
    res = _post_chat_completion(endpoint, payload, stage="generate_markdown_sample")
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
- when downstream code is generated, require valid python-pptx usage: never `ChartType` from `pptx.enum.chart` (use `XL_CHART_TYPE`), guard `slide.shapes.title` for None before `.text`, and exact `# Thinking` / `# Assistant` markdown sections with ```text / ```python fences

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
    res = _post_chat_completion(endpoint, payload, stage="generate_raw_prompt_system_prompt")
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
    res = _post_chat_completion(endpoint, payload, stage=f"generate_raw_prompt_list:{prompt_count}")
    return _extract_content(res)


def repair_thinking_only(
    *,
    endpoint: str,
    model: str,
    raw_prompt: str,
    fixed_user_prompt: str,
    previous_markdown: str,
    error_memory_addon: Optional[str] = None,
) -> str:
    user_message = f"""Regenerate ONLY the missing or malformed Thinking section body.

Original raw request:
{raw_prompt}

--- LOCKED # User Prompt body or raw prompt fallback ---
{fixed_user_prompt}

--- Previous markdown output with malformed Thinking section ---
{previous_markdown}

Return only the Thinking text body."""
    system = _merge_error_memory_into_system(
        DEFAULT_DATASET_THINKING_RETRY_SYSTEM_PROMPT.strip(),
        error_memory_addon,
    )
    payload = {
        "model": model,
        "temperature": 0.05,
        "repeat_penalty": 1.1,
        "max_tokens": 4000,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user_message},
        ],
    }
    res = _post_chat_completion(endpoint, payload, stage="repair_thinking_only")
    raw = _extract_content(res)
    extracted = _extract_thinking_text(raw)
    if not extracted.strip():
        raise LMStudioError("재시도 응답에서 Thinking 본문을 찾지 못했습니다.")
    return extracted


def repair_assistant_python_only(
    *,
    endpoint: str,
    model: str,
    raw_prompt: str,
    fixed_user_prompt: str,
    fixed_thinking: str,
    failed_python_code: str,
    traceback_text: str,
    error_memory_addon: Optional[str] = None,
) -> str:
    user_message = f"""Python execution failed. Regenerate ONLY the Assistant Python script.

Original raw request (context):
{raw_prompt}

--- LOCKED # User Prompt body (verbatim; do not change meaning in code) ---
{fixed_user_prompt}

--- LOCKED # Thinking body (verbatim; code must follow this plan) ---
{fixed_thinking}

--- Previous Assistant Python (replace entirely) ---
```python
{failed_python_code}
```

--- Runtime traceback ---
```text
{traceback_text}
```

Return one ```python fenced block with the full fixed script."""
    system = _merge_error_memory_into_system(
        DEFAULT_DATASET_RETRY_SYSTEM_PROMPT.strip(),
        error_memory_addon,
    )
    payload = {
        "model": model,
        "temperature": 0.05,
        "repeat_penalty": 1.1,
        "max_tokens": 12000,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user_message},
        ],
    }
    res = _post_chat_completion(endpoint, payload, stage="repair_assistant_python_only")
    raw = _extract_content(res)
    extracted = _extract_assistant_python_fence(raw)
    if not extracted.strip():
        raise LMStudioError("재시도 응답에서 Python 코드 블록을 찾지 못했습니다.")
    return extracted


def repair_markdown_sample(
    *,
    endpoint: str,
    model: str,
    raw_prompt: str,
    previous_markdown: str,
    failed_python_code: str,
    traceback_text: str,
    error_memory_addon: Optional[str] = None,
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

Regenerate the answer in the exact same 2 markdown sections format.
The Assistant python code must be executable and must use supported python-pptx APIs only.
Never use unsupported shape enums like MSO_SHAPE.LINE or MSO_SHAPE.CHECK.
Use slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, ...) for line segments.
Do not import ChartType from pptx.enum.chart; use XL_CHART_TYPE. Never assign to slide.shapes.title.text unless title is not None.
Use headings exactly `# Thinking`, `# Assistant` with ```text / ```python fences as in the system prompt.
Do not output inner deliberation or meta commentary. Output only the required 2 sections.
"""
    system = _merge_error_memory_into_system(
        DEFAULT_DATASET_SYSTEM_PROMPT.strip(),
        error_memory_addon,
    )
    payload = {
        "model": model,
        "temperature": 0.05,
        "repeat_penalty": 1.1,
        "max_tokens": 12000,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": repair_prompt},
        ],
    }
    res = _post_chat_completion(endpoint, payload, stage="repair_markdown_sample")
    return _extract_content(res)
