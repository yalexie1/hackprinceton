import type { RunEvent } from "./types";

// Fast-forward preserves the next user decision and never skips a terminal event.
export function replayBatch(events: RunEvent[], start: number, fast: boolean) {
  const batch: RunEvent[] = [];
  let next = start;
  while (next < events.length) {
    const event = events[next++];
    batch.push(event);
    if (
      !fast ||
      event.type === "question" ||
      event.type === "done" ||
      event.type === "error"
    )
      break;
  }
  return { batch, next };
}
