export const PIPELINE_STAGES = [
  { key: "queued", label: "Queued" },
  { key: "planning", label: "Planning" },
  { key: "visual_generating", label: "Visuals" },
  { key: "code_generating", label: "Code" },
  { key: "executing", label: "Execute" },
  { key: "retrying", label: "Retry" },
  { key: "completed", label: "Complete" },
  { key: "failed", label: "Failed" }
];

export class PipelineStageModel {
  constructor(currentStatus) {
    this.currentStatus = currentStatus ?? "queued";
    this.currentIndex = PIPELINE_STAGES.findIndex((stage) => stage.key === this.currentStatus);
  }

  resolveStepState(stage, index) {
    if (this.currentStatus === "failed") {
      if (stage.key === "failed") return "failed";
      if (index < PIPELINE_STAGES.length - 1) return "done";
      return "idle";
    }

    if (this.currentStatus === "completed") {
      return "done";
    }

    if (this.currentIndex === -1) {
      return "idle";
    }

    if (index < this.currentIndex) return "done";
    if (index === this.currentIndex) return "active";
    return "idle";
  }

  listItems() {
    return PIPELINE_STAGES.map((stage, index) => ({
      ...stage,
      index: index + 1,
      state: this.resolveStepState(stage, index)
    }));
  }

  currentLabel() {
    const matched = PIPELINE_STAGES.find((stage) => stage.key === this.currentStatus);
    return matched ? matched.label : "Unknown";
  }
}
