import { useMemo, useState } from "react";
import { displayPercent, displaySeconds, displayValue, playerLabel } from "../lib/format";
import { teamLabel, useTeamNames } from "../lib/teamNames";
import type { PlayerStats } from "../types/matchStats";

type Filter = "all" | "team_a" | "team_b";
type SortKey =
  | "possession"
  | "goals"
  | "shots"
  | "passes"
  | "interceptions"
  | "recoveries";

const SORT_FIELD: Record<SortKey, keyof PlayerStats> = {
  possession: "ball_possession_time_seconds",
  goals: "goals",
  shots: "shots",
  passes: "successful_passes",
  interceptions: "interceptions",
  recoveries: "ball_recoveries",
};

export function PlayerTable({ players }: { players: PlayerStats[] }) {
  const names = useTeamNames();
  const [filter, setFilter] = useState<Filter>("all");
  const [sort, setSort] = useState<SortKey>("possession");

  const rows = useMemo(() => {
    const filtered = players.filter((p) => {
      if (p.team_id !== "team_a" && p.team_id !== "team_b") return false;
      if (filter === "all") return true;
      return p.team_id === filter;
    });
    const key = SORT_FIELD[sort];
    return [...filtered].sort((a, b) => Number(b[key] ?? 0) - Number(a[key] ?? 0));
  }, [players, filter, sort]);

  return (
    <section className="section">
      <h2>Player statistics</h2>
      <div className="controls">
        {(["all", "team_a", "team_b"] as Filter[]).map((id) => (
          <button
            key={id}
            className={`chip ${filter === id ? "active" : ""}`}
            onClick={() => setFilter(id)}
            type="button"
          >
            {id === "all" ? "All" : teamLabel(id, names)}
          </button>
        ))}
        <label className="select" style={{ display: "inline-flex", gap: 8, alignItems: "center" }}>
          Sort
          <select value={sort} onChange={(e) => setSort(e.target.value as SortKey)}>
            <option value="possession">Possession</option>
            <option value="goals">Goals</option>
            <option value="shots">Shots</option>
            <option value="passes">Passes</option>
            <option value="interceptions">Interceptions</option>
            <option value="recoveries">Recoveries</option>
          </select>
        </label>
      </div>
      <div className="panel table-wrap">
        <table>
          <thead>
            <tr>
              <th>Player</th>
              <th>Team</th>
              <th>Possession time</th>
              <th>Goals</th>
              <th>Shots</th>
              <th>SOT</th>
              <th>Shot accuracy</th>
              <th>Shot conversion</th>
              <th>Successful passes</th>
              <th>Pass accuracy</th>
              <th>Interceptions</th>
              <th>Recoveries</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((player) => (
              <PlayerRow key={player.stable_id} player={player} />
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

export function PlayerRow({ player }: { player: PlayerStats }) {
  const names = useTeamNames();
  const teamClass = player.team_id === "team_a" ? "a" : "b";
  return (
    <tr>
      <td className="player-id">{playerLabel(player.stable_id)}</td>
      <td>
        <span className={`team-tag ${teamClass}`}>{teamLabel(player.team_id, names)}</span>
      </td>
      <td>{displaySeconds(player.ball_possession_time_seconds)}</td>
      <td>{displayValue(player.goals)}</td>
      <td>{displayValue(player.shots)}</td>
      <td>{displayValue(player.shots_on_target)}</td>
      <td className={player.shot_accuracy === null ? "nullish" : ""}>
        {displayPercent(player.shot_accuracy)}
      </td>
      <td className={player.shot_conversion_rate === null ? "nullish" : ""}>
        {displayPercent(player.shot_conversion_rate)}
      </td>
      <td>{displayValue(player.successful_passes)}</td>
      <td className="nullish">{displayPercent(player.pass_accuracy)}</td>
      <td>{displayValue(player.interceptions)}</td>
      <td>{displayValue(player.ball_recoveries)}</td>
    </tr>
  );
}
