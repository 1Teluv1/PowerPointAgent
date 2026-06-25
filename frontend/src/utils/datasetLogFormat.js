const TOKEN_STREAM_MAX_CHARS = 200_000;

export function formatLogTimestamp(ts) {
  const date = ts ? new Date(ts) : new Date();
  const hours = String(date.getHours()).padStart(2, "0");
  const minutes = String(date.getMinutes()).padStart(2, "0");
  const seconds = String(date.getSeconds()).padStart(2, "0");
  const ms = String(date.getMilliseconds()).padStart(3, "0");
  return `${hours}:${minutes}:${seconds}.${ms}`;
}

function tagPrefix(tag) {
  if (!tag) return "LOG";
  return String(tag).split(".")[0];
}

function buildMetaSuffix(meta) {
  const parts = Object.entries(meta)
    .filter(([, value]) => value !== null && value !== undefined && value !== "")
    .map(([key, value]) => `${key}=${value}`);
  return parts.length ? ` ${parts.join(" ")}` : "";
}

export function formatTaggedLogLine(event) {
  const ts = formatLogTimestamp(
    typeof event?.timestamp === "number" ? event.timestamp * 1000 : event?.ts ?? Date.now()
  );

  if (event?.type === "log") {
    const tag = event.tag || "LOG";
    const meta = buildMetaSuffix({
      stage: event.stage,
      attempt: event.attempt,
      chunk_index: event.chunk_index,
      chunk_total: event.chunk_total,
      item_index: event.item_index,
      status: event.status
    });
    return {
      id: `${ts}-${tag}-${Math.random().toString(36).slice(2, 6)}`,
      ts,
      tag,
      tagPrefix: tagPrefix(tag),
      level: event.level || "info",
      text: `[${ts}] [${tag}]${meta} ${event.message || ""}`.trim()
    };
  }

  if (event?.type === "repair_plan") {
    const tag = "REPAIR.PLAN";
    const meta = buildMetaSuffix({
      stage: event.stage,
      attempt: event.attempt,
      repair_target: event.repair_target,
      failure_kind: event.failure_kind
    });
    return {
      id: `${ts}-${tag}-${Math.random().toString(36).slice(2, 6)}`,
      ts,
      tag,
      tagPrefix: "REPAIR",
      level: "info",
      text: `[${ts}] [${tag}]${meta} ${event.content || "repair plan"}`.trim()
    };
  }

  if (event?.type === "start") {
    const tag = "LM.START";
    const meta = buildMetaSuffix({
      stage: event.stage,
      model: event.model
    });
    return {
      id: `${ts}-${tag}-${Math.random().toString(36).slice(2, 6)}`,
      ts,
      tag,
      tagPrefix: "LM",
      level: "info",
      text: `[${ts}] [${tag}]${meta}`.trim()
    };
  }

  if (event?.type === "end") {
    const tag = "LM.END";
    const meta = buildMetaSuffix({
      stage: event.stage,
      model: event.model,
      tokens: event.token_count
    });
    return {
      id: `${ts}-${tag}-${Math.random().toString(36).slice(2, 6)}`,
      ts,
      tag,
      tagPrefix: "LM",
      level: "info",
      text: `[${ts}] [${tag}]${meta}`.trim()
    };
  }

  if (event?.type === "error") {
    const tag = "ERROR";
    const meta = buildMetaSuffix({ stage: event.stage, model: event.model });
    return {
      id: `${ts}-${tag}-${Math.random().toString(36).slice(2, 6)}`,
      ts,
      tag,
      tagPrefix: "ERROR",
      level: "error",
      text: `[${ts}] [${tag}]${meta} ${event.content || "LM Studio 오류"}`.trim()
    };
  }

  return null;
}

export function appendTokenStream(prev, event, { showReasoning = true } = {}) {
  const channel = event?.channel || "content";
  if (channel === "reasoning" && !showReasoning) {
    return prev;
  }

  if (event?.type === "start") {
    const separator = `\n\n--- ${event.stage || "lm_studio"} ---\n`;
    const next = `${prev}${separator}`;
    return next.length > TOKEN_STREAM_MAX_CHARS ? next.slice(-TOKEN_STREAM_MAX_CHARS) : next;
  }

  if (event?.type === "delta") {
    const chunk = event.content || "";
    if (!chunk) return prev;
    const prefix = channel === "reasoning" ? "[reasoning] " : "";
    const next = `${prev}${prefix}${chunk}`;
    return next.length > TOKEN_STREAM_MAX_CHARS ? next.slice(-TOKEN_STREAM_MAX_CHARS) : next;
  }

  return prev;
}

export function eventToTaggedLine(event) {
  return formatTaggedLogLine(event);
}
