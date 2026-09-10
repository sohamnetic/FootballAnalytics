import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { getMatch, startAnalysis } from "../api/getMatchStats";
import { ProductNav } from "../components/ProductNav";

export function SetupPage() {
  const { matchId } = useParams();
  const navigate = useNavigate();
  const [filename, setFilename] = useState("Video");
  const [teamA, setTeamA] = useState("Team A");
  const [teamB, setTeamB] = useState("Team B");
  const [camera, setCamera] = useState("Camera 001");
  const [analysis, setAnalysis] = useState<"full" | "window">("full");
  const [startTime, setStartTime] = useState("0");
  const [duration, setDuration] = useState("40");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!matchId) return;
    getMatch(matchId)
      .then((row) => {
        setFilename(row.filename || "Video");
        setTeamA(row.team_a || "Team A");
        setTeamB(row.team_b || "Team B");
        setCamera(row.camera || "Camera 001");
      })
      .catch((err: unknown) => setError(err instanceof Error ? err.message : "Match not found"));
  }, [matchId]);

  async function onStart() {
    if (!matchId) return;
    setBusy(true);
    setError(null);
    try {
      await startAnalysis(matchId, {
        team_a: teamA,
        team_b: teamB,
        camera,
        analysis,
        start_time_s: analysis === "window" ? Number(startTime) : 0,
        duration_s: analysis === "window" ? Number(duration) : null,
      });
      navigate(`/matches/${matchId}/processing`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not start analysis");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="app">
      <ProductNav />
      <section className="panel form-panel">
        <div className="kicker">Match setup</div>
        <h1>Ready to analyze</h1>
        <label className="field">
          Video
          <input value={filename} readOnly />
        </label>
        <label className="field">
          Team A
          <input value={teamA} onChange={(e) => setTeamA(e.target.value)} />
        </label>
        <label className="field">
          Team B
          <input value={teamB} onChange={(e) => setTeamB(e.target.value)} />
        </label>
        <label className="field">
          Camera
          <input value={camera} onChange={(e) => setCamera(e.target.value)} />
        </label>
        <label className="field">
          Analysis
          <select value={analysis} onChange={(e) => setAnalysis(e.target.value as "full" | "window")}>
            <option value="full">Full match</option>
            <option value="window">Custom window (development)</option>
          </select>
        </label>
        {analysis === "window" ? (
          <div className="split-fields">
            <label className="field">
              Start (seconds)
              <input value={startTime} onChange={(e) => setStartTime(e.target.value)} />
            </label>
            <label className="field">
              Duration (seconds)
              <input value={duration} onChange={(e) => setDuration(e.target.value)} />
            </label>
          </div>
        ) : (
          <p className="muted">The entire uploaded video will be analyzed. This can take a long time for a full match.</p>
        )}
        {error ? <p className="error">{error}</p> : null}
        <div className="hero-actions">
          <Link className="btn ghost" to="/upload">
            Back
          </Link>
          <button className="btn primary" type="button" disabled={busy} onClick={onStart}>
            {busy ? "Starting…" : "Start Analysis"}
          </button>
        </div>
      </section>
    </div>
  );
}
