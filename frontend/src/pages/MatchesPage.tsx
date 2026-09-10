import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { deleteMatch, listMatches, type MatchRecord } from "../api/getMatchStats";
import { ProductNav } from "../components/ProductNav";

export function MatchesPage() {
  const [rows, setRows] = useState<MatchRecord[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<string | null>(null);

  function refresh() {
    return listMatches()
      .then((data) => setRows(data.matches || []))
      .catch((err: unknown) => setError(err instanceof Error ? err.message : "Failed to load"));
  }

  useEffect(() => {
    refresh();
  }, []);

  async function onDelete(row: MatchRecord) {
    const ok = window.confirm(`Delete ${row.filename || "this match"}? This cannot be undone.`);
    if (!ok) return;
    setDeleting(row.match_id);
    setError(null);
    try {
      await deleteMatch(row.match_id);
      setRows((current) => current.filter((item) => item.match_id !== row.match_id));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not delete match");
    } finally {
      setDeleting(null);
    }
  }

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
              <div className="match-actions">
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
                <button
                  className="btn danger"
                  type="button"
                  disabled={deleting === row.match_id || row.status === "processing" || row.status === "queued"}
                  onClick={() => onDelete(row)}
                >
                  {deleting === row.match_id ? "Deleting…" : "Delete"}
                </button>
              </div>
            </article>
          ))}
        </div>
      </section>
    </div>
  );
}
