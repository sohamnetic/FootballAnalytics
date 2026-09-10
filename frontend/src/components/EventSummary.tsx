import { displayValue } from "../lib/format";
import type { EventSummary } from "../types/matchStats";

export function EventSummary({ summary }: { summary: EventSummary }) {
  const tiles = [
    ["Completed passes", summary.completed_passes],
    ["Interceptions", summary.interceptions],
    ["Recoveries", summary.recoveries],
    ["Shots", summary.shots],
    ["Shots on target", summary.shots_on_target],
    ["Goals", summary.goals],
    ["Possession intervals", summary.possession_intervals],
  ] as const;

  return (
    <section className="section">
      <h2>Event summary</h2>
      <div className="panel event-grid">
        {tiles.map(([label, value]) => (
          <div className="event-tile" key={label}>
            <div className="n">{displayValue(value)}</div>
            <div className="l">{label}</div>
          </div>
        ))}
      </div>
    </section>
  );
}
