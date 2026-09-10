import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { getMatch, getMatchStatus, startAnalysis } from "../api/getMatchStats";
import { ProductNav } from "../components/ProductNav";

export function ProcessingPage() {
  const { matchId } = useParams();
  const navigate = useNavigate();
  const [progress, setProgress] = useState(0);
  const [stage, setStage] = useState("Queued");
  const [status, setStatus] = useState("queued");
  const [message, setMessage] = useState("Analyzing match footage...");
  const [kind, setKind] = useState("stage-based");

  useEffect(() => {
    if (!matchId) return;
    let stop = false;
    async function tick() {
      try {
        const row = await getMatchStatus(matchId!);
        if (stop) return;
        setProgress(row.progress ?? 0);
        setStage(row.stage || row.status);
        setStatus(row.status);
        setMessage(row.message || "");
        setKind(row.progress_kind || "stage-based");
        if (row.status === "completed") {
          navigate(`/matches/${matchId}`);
        }
      } catch {
        if (!stop) setStatus("failed");
      }
    }
    tick();
    const id = window.setInterval(tick, 1500);
    return () => {
      stop = true;
      window.clearInterval(id);
    };
  }, [matchId, navigate]);

  async function retry() {
    if (!matchId) return;
    const row = await getMatch(matchId);
    await startAnalysis(matchId, {
      team_a: row.team_a || "Team A",
      team_b: row.team_b || "Team B",
      camera: row.camera || "Camera 001",
      analysis: row.analysis === "window" ? "window" : "full",
      start_time_s: row.start_time_s,
      duration_s: row.duration_s,
    });
    setStatus("queued");
  }

  if (status === "failed") {
    return (
      <div className="app">
        <ProductNav />
        <section className="panel form-panel">
          <div className="kicker">Analysis failed</div>
          <h1>We couldn't complete analysis for this match.</h1>
          <p className="muted">{message}</p>
          <div className="hero-actions">
            <button className="btn primary" type="button" onClick={retry}>
              Try Again
            </button>
            <Link className="btn ghost" to="/upload">
              Upload Another Video
            </Link>
          </div>
        </section>
      </div>
    );
  }

  return (
    <div className="app">
      <ProductNav />
      <section className="panel form-panel">
        <div className="kicker">Live pipeline</div>
        <h1>Analyzing match</h1>
        <div className="progress-track" aria-valuenow={progress} aria-valuemin={0} aria-valuemax={100}>
          <i style={{ width: `${Math.max(progress, 3)}%` }} />
        </div>
        <div className="progress-meta">
          <strong>{progress}%</strong>
          <span>Stage-based progress</span>
        </div>
        <p>
          Current stage: <strong>{stage}</strong>
        </p>
        <p className="muted">{message} ({kind})</p>
      </section>
    </div>
  );
}
