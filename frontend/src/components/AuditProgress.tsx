import type { RunEvent } from "../lib/types";

/**
 * The audit's position, at the top of the page.
 *
 * The stage log is honest but long, and in a rehearsal the thing a person wanted to know - how
 * far along is this, and is it waiting for me - was below a screenful of events. This says it
 * once, above everything.
 *
 * Progress is counted from the stages the run has actually started, not from a guess at how many
 * there will be: a run can skip a stage (no desks to score, no document to draft), so a fixed
 * denominator would either stall at 7/8 or jump. `STAGES` is the order they occur in; anything
 * unrecognised is ignored rather than mislabelled.
 */
const STAGES: { id: string; label: string }[] = [
  { id: "S1", label: "Locating" },
  { id: "S2", label: "Fetching data" },
  { id: "S3", label: "Reviewing building images" },
  { id: "S4", label: "Building the model" },
  { id: "S5", label: "Baseline" },
  { id: "S6", label: "Measures" },
  { id: "S7", label: "The plan" },
  { id: "S8", label: "Summary" },
];

export function auditProgress(events: RunEvent[], done: boolean) {
  const seen = new Set<string>();
  const finished = new Set<string>();
  for (const event of events) {
    const stage = event.stage || "";
    if (!STAGES.some((s) => s.id === stage)) continue;
    seen.add(stage);
    if (event.type === "stage_done") finished.add(stage);
  }
  const order = STAGES.filter((s) => seen.has(s.id));
  const current = order[order.length - 1];
  return {
    total: STAGES.length,
    complete: done ? STAGES.length : finished.size,
    label: done ? "Complete" : current ? current.label : "Starting",
    reached: order.length,
  };
}

export function AuditProgress({
  events,
  done,
  waiting,
}: {
  events: RunEvent[];
  done: boolean;
  waiting: boolean;
}) {
  const { total, complete, label } = auditProgress(events, done);
  // A run waiting on a person is not making progress, and a bar that keeps creeping while it
  // waits reads as "working". It says so instead.
  const state = done ? "done" : waiting ? "waiting" : "running";
  return (
    <div className={`audit-progress ${state}`} data-testid="audit-progress">
      <div className="audit-progress-row">
        <strong>{waiting && !done ? "Waiting for you" : label}</strong>
        <span>
          {complete} of {total} stages
        </span>
      </div>
      <progress
        aria-label="Audit progress"
        value={complete}
        max={total}
      />
    </div>
  );
}
