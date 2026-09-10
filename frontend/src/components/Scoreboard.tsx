import { displayPercent, displayValue } from "../lib/format";
import { teamLabel, useTeamNames } from "../lib/teamNames";
import type { MatchStats } from "../types/matchStats";

export function Scoreboard({ stats }: { stats: MatchStats }) {
  const a = stats.teams.team_a;
  const b = stats.teams.team_b;
  const names = useTeamNames();
  return (
    <section className="panel scoreboard" aria-label="Scoreboard">
      <div className="score-row">
        <div className="score-team a">{teamLabel("team_a", names)}</div>
        <div className="score-num">
          {displayValue(a.goals)} — {displayValue(b.goals)}
        </div>
        <div className="score-team b">{teamLabel("team_b", names)}</div>
      </div>
      <div className="score-sub">
        <Mini label="Possession" left={displayPercent(a.possession_percentage)} right={displayPercent(b.possession_percentage)} />
        <Mini label="Shots" left={displayValue(a.shots)} right={displayValue(b.shots)} />
        <Mini label="Shots on target" left={displayValue(a.shots_on_target)} right={displayValue(b.shots_on_target)} />
      </div>
    </section>
  );
}

function Mini({
  label,
  left,
  right,
}: {
  label: string;
  left: string;
  right: string;
}) {
  return (
    <div className="score-mini">
      <div className="label">{label}</div>
      <div className="vals">
        <span>{left}</span>
        <b>—</b>
        <span>{right}</span>
      </div>
    </div>
  );
}
