import { playerLabel } from "../lib/format";
import { teamLabel, useTeamNames } from "../lib/teamNames";
import type { TimelineEvent } from "../types/matchStats";

export function EventTimeline({ events }: { events?: TimelineEvent[] }) {
  const names = useTeamNames();
  const hasEvents = Array.isArray(events) && events.length > 0;
  return (
    <section className="section">
      <h2>Event timeline</h2>
      <div className="panel timeline">
        {hasEvents ? (
          <ol style={{ margin: 0, paddingLeft: 18 }}>
            {events.map((event, index) => (
              <li key={`${event.type}-${index}`} style={{ marginBottom: 10 }}>
                <strong>{event.type}</strong>
                {" · "}
                {event.time_s === null || event.time_s === undefined ? "—" : `${event.time_s}s`}
                {" · "}
                {event.team_id ? teamLabel(event.team_id, names) : "—"}
                {" · "}
                {event.stable_id === null || event.stable_id === undefined
                  ? "—"
                  : playerLabel(event.stable_id)}
              </li>
            ))}
          </ol>
        ) : (
          <p className="timeline-empty">
            Chronological event rows are not included in the unified match stats JSON.
            Counts are shown in Event summary. This timeline will populate when
            <code> events[] </code>
            is added to the product payload — it will not be inferred from individual event CSVs.
          </p>
        )}
        <div className="legend">
          {["SHOT", "PASS", "RECOVERY", "INTERCEPTION", "GOAL"].map((kind) => (
            <span key={kind}>{kind}</span>
          ))}
        </div>
      </div>
    </section>
  );
}
