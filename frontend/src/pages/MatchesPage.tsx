import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { listMatches, type MatchRecord } from "../api/getMatchStats";
import { ProductNav } from "../components/ProductNav";

export function MatchesPage() {
  const [rows, setRows] = useState<MatchRecord[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listMatches()
      .then((data) => setRows(data.matches || []))
      .catch((err: unknown) => setError(err instanceof Error ? err.message : "Failed to load"));
  }, []);

  return (
    <div className="app">
      <ProductNav />
      <section>
        <div className="kicker">Archive</div>
        <h1>Previous matches</h1>
        {error ? <p className="error">{error}</p> : null}
        <div className="match-list">
          {rows.length === 0 ? <p className="muted">No matches yet.</p> : null}
          {rows.map((row) => (
            <article className="panel match-card" key={row.match_id}>
              <div>
                <h2>
                  {row.team_a || "Team A"}{" "}
                  {row.goals_a ?? "—"} — {row.goals_b ?? "—"}{" "}
                  {row.team_b || "Team B"}
                </h2>
                <p className="muted">{row.filename}</p>
                <p className="muted">
                  {row.status === "completed" ? "Analyzed" : row.status}{" "}
                  {row.completed_at || row.created_at
                    ? new Date(row.completed_at || row.created_at || "").toLocaleString()
                    : ""}
                </p>
              </div>
              {row.status === "completed" ? (
                <Link className="btn primary" to={`/matches/${row.match_id}`}>
                  View
                </Link>
              ) : row.status === "processing" || row.status === "queued" ? (
                <Link className="btn ghost" to={`/matches/${row.match_id}/processing`}>
                  Status
                </Link>
              ) : (
                <Link className="btn ghost" to={`/matches/${row.match_id}/setup`}>
                  Setup
                </Link>
              )}
            </article>
          ))}
        </div>
      </section>
    </div>
  );
}
