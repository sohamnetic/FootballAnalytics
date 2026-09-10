import { displayPercent, displayValue } from "../lib/format";
import type { TeamStats } from "../types/matchStats";

function formatStat(value: number | null, kind: "number" | "percent"): string {
  if (value === null || value === undefined) return "N/A";
  return kind === "percent" ? displayPercent(value) : displayValue(value);
}

export function StatCard({
  label,
  a,
  b,
  kind = "number",
}: {
  label: string;
  a: number | null;
  b: number | null;
  kind?: "number" | "percent";
}) {
  const left = formatStat(a, kind);
  const right = formatStat(b, kind);
  const aNum = typeof a === "number" ? a : 0;
  const bNum = typeof b === "number" ? b : 0;
  const total = aNum + bNum;
  const aPct = total > 0 ? (100 * aNum) / total : 50;
  return (
    <article className="stat-card">
      <div className="label">{label}</div>
      <div className="stat-split">
        <div className="stat-value a">{left}</div>
        <em>vs</em>
        <div className="stat-value b">{right}</div>
      </div>
      {kind !== "percent" && a !== null && b !== null ? (
        <div className="bar" aria-hidden="true">
          <i className="a" style={{ width: `${aPct}%` }} />
          <i className="b" style={{ width: `${100 - aPct}%` }} />
        </div>
      ) : null}
    </article>
  );
}

export function TeamComparison({
  teamA,
  teamB,
}: {
  teamA: TeamStats;
  teamB: TeamStats;
}) {
  const possA = teamA.possession_percentage ?? 0;
  const possB = teamB.possession_percentage ?? 0;
  const rest = Math.max(0, 100 - possA - possB);
  return (
    <section className="section">
      <h2>Team comparison</h2>
      <div className="panel comparison">
        <div className="stat-grid">
          <StatCard label="Possession %" a={teamA.possession_percentage} b={teamB.possession_percentage} kind="percent" />
          <StatCard label="Goals" a={teamA.goals} b={teamB.goals} />
          <StatCard label="Shots" a={teamA.shots} b={teamB.shots} />
          <StatCard label="Shots on target" a={teamA.shots_on_target} b={teamB.shots_on_target} />
          <StatCard label="Completed passes" a={teamA.completed_passes} b={teamB.completed_passes} />
          <StatCard label="Interceptions" a={teamA.interceptions} b={teamB.interceptions} />
          <StatCard label="Ball recoveries" a={teamA.ball_recoveries} b={teamB.ball_recoveries} />
          <StatCard label="Pass accuracy" a={teamA.pass_accuracy} b={teamB.pass_accuracy} kind="percent" />
        </div>
        <div style={{ marginTop: 16 }}>
          <div className="label" style={{ color: "var(--muted)", fontSize: 11, letterSpacing: "0.16em", textTransform: "uppercase" }}>
            Possession share of clip (remainder is loose / unknown)
          </div>
          <div className="bar" style={{ marginTop: 8, height: 10 }}>
            <i className="a" style={{ width: `${possA}%` }} />
            <i className="b" style={{ width: `${possB}%` }} />
            <i className="rest" style={{ width: `${rest}%` }} />
          </div>
        </div>
      </div>
    </section>
  );
}
