import { PipelineStageModel } from "../domain/pipelineStage";

export default function PipelineStatusStepper({ status }) {
  const stageModel = new PipelineStageModel(status);
  const steps = stageModel.listItems();

  return (
    <>
      <ol className="steps" aria-live="polite">
        {steps.map((step) => (
          <li key={step.key} className="step" data-state={step.state}>
            <span className="dot">{step.index}</span>
            <strong>{step.label}</strong>
            <span className="state">{step.state.toUpperCase()}</span>
          </li>
        ))}
      </ol>
      <div className="current" role="status">
        Current: {stageModel.currentLabel()}
      </div>
    </>
  );
}
