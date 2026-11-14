import { describe, expect, it } from "vitest";
import { replayBatch } from "./audit-replay";
import { demoEvents, demoProperties } from "./fixtures";
import type { RunEvent } from "./types";

describe("saved audit pacing", () => {
  it("fast-forwards every shared audit without skipping a question or final result", () => {
    for (const property of demoProperties) {
      const events = demoEvents(property.sid);
      let cursor = 0;
      const revealed: RunEvent[] = [];
      while (cursor < events.length) {
        const { batch, next } = replayBatch(events, cursor, true);
        expect(
          batch
            .slice(0, -1)
            .some((event) =>
              ["question", "done", "error"].includes(event.type),
            ),
        ).toBe(false);
        revealed.push(...batch);
        cursor = next;
      }
      expect(revealed).toEqual(events);
    }
  });
  it("normal playback reveals only one event and an exhausted replay stays exhausted", () => {
    const events = demoEvents(demoProperties[0].sid);
    expect(replayBatch(events, 0, false)).toEqual({
      batch: [events[0]],
      next: 1,
    });
    expect(replayBatch(events, events.length, true)).toEqual({
      batch: [],
      next: events.length,
    });
  });
});
