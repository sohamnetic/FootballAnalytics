import { videoLabel } from "../lib/format";
import { teamLabel, useTeamNames } from "../lib/teamNames";
import type { MatchStats } from "../types/matchStats";

export function MatchHeader({ stats }: { stats: MatchStats }) {
  const { match } = stats;
  const names = useTeamNames();
  return (
    <header className="match-header">
      <div>
        <div className="kicker">Football Analytics</div>
        <h1>Match dashboard</h1>
        <div className="meta-row">
          <div>
            Camera / video
            <br />
            <strong>{videoLabel(match.video)}</strong>
          </div>
          <div>
            Analysis window
            <br />
            <strong>
              {displayWindow(match.start_time_s, match.duration_s)} · {match.fps} fps
            </strong>
          </div>
          <div>
            Pipeline
            <br />
            <strong>{stats.pipeline_version ?? "—"}</strong>
          </div>
        </div>
      </div>
      <div className="team-pills">
        <div className="team-pill a">
          <span>Home side</span>
          <strong>{teamLabel("team_a", names)}</strong>
        </div>
        <div className="team-pill b">
          <span>Away side</span>
          <strong>{teamLabel("team_b", names)}</strong>
        </div>
      </div>
    </header>
  );
}

function displayWindow(start: number | null, duration: number | null): string {
  if (duration === null || duration === undefined) return "Full match";
  const origin = start ?? 0;
  const end = origin + duration;
  return `${origin}s – ${end}s (${duration}s)`;
}
