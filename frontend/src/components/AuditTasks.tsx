import type { RunEvent } from "../lib/types";

export default function AuditTasks({
  event,
  finished,
  archived = false,
}: {
  event: RunEvent;
  finished: boolean;
  archived?: boolean;
}) {
  if (!Array.isArray(event.payload.todos)) return null;
  const tasks = event.payload.todos as {
    content?: unknown;
    status?: unknown;
  }[];
  const list = (
    <ul className="event-todos">
      {tasks.map((task, i) => (
        <li key={i}>
          <span className="status-dot" />
          {String(task.content || "Audit task")}
          {!finished && !archived && (
            <small>
              {String(task.status || "pending").replaceAll("_", " ")}
            </small>
          )}
        </li>
      ))}
    </ul>
  );
  return finished || archived ? (
    <details>
      <summary>
        View the {finished ? "initial" : "earlier"} audit checklist
      </summary>
      <p>
        This is a saved checklist from an earlier point in the audit. Follow the
        activity for subsequent results. Counts and questions in this checklist
        describe that earlier plan, not the final audit.
      </p>
      {list}
    </details>
  ) : (
    list
  );
}
