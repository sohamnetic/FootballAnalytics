import { boolLabel, displayValue } from "../lib/format";
import type { MatchStats } from "../types/matchStats";

export function DataQuality({ stats }: { stats: MatchStats }) {
  const q = stats.data_quality;
  const tiles = [
    ["Identity quality", stats.identity_quality],
    ["Stable IDs", displayValue(q.stable_ids)],
    ["Estimated visible players", q.estimated_visible_players],
    ["Team assignment uncertainty", boolLabel(q.team_assignment_uncertainty)],
    ["Manual goal geometry", boolLabel(q.goal_geometry_manual)],
    ["Pass attempts available", boolLabel(q.pass_attempts_available)],
  ] as const;

  return (
    <section className="section">
      <h2>Data quality</h2>
      <div className="panel quality-grid">
        {tiles.map(([label, value]) => (
          <div className="quality-tile" key={label}>
            <div className="n" style={{ fontSize: 22 }}>{value}</div>
            <div className="l">{label}</div>
          </div>
        ))}
      </div>
    </section>
  );
}
