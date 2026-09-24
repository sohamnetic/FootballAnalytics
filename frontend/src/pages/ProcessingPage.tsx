import { Check, CircleAlert, RotateCcw, Upload } from "lucide-react";
import { motion } from "motion/react";
import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { getMatch, getMatchStatus, startAnalysis } from "../api/getMatchStats";
import { FlowSteps } from "../components/layout/FlowSteps";
import { PageShell } from "../components/layout/PageShell";
import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";
import { Spinner } from "../components/ui/Spinner";
import { cn } from "../lib/cn";

// Mirrors STAGE_PROGRESS in app/jobs.py: progress at which each stage starts.
const STAGES: [string, number][] = [
  ["Preparing video", 5],
  ["Detecting & tracking players", 12],
  ["Detecting the ball", 40],
  ["Calculating possession", 55],
  ["Assigning teams", 65],
  ["Passes & turnovers", 72],
  ["Shots", 90],
  ["Building your dashboard", 98],
];

function formatElapsed(ms: number) {
  const s = Math.floor(ms / 1000);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

export function ProcessingPage() {
  const { matchId } = useParams();
  const navigate = useNavigate();
  const [progress, setProgress] = useState(0);
  const [status, setStatus] = useState("queued");
  const [message, setMessage] = useState("");
  const [retrying, setRetrying] = useState(false);
  const started = useRef(Date.now());
  const [now, setNow] = useState(Date.now());

  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, []);

  useEffect(() => {
    if (!matchId) return;
    let stop = false;
    async function tick() {
      try {
        const row = await getMatchStatus(matchId!);
        if (stop) return;
        setProgress(row.progress ?? 0);
        setStatus(row.status);
        setMessage(row.message || "");
        if (row.status === "completed") navigate(`/matches/${matchId}`);
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
    setRetrying(true);
    try {
      const row = await getMatch(matchId);
      await startAnalysis(matchId, {
        team_a: row.team_a || "Team A",
        team_b: row.team_b || "Team B",
        camera: row.camera || "Camera 001",
        analysis: row.analysis === "window" ? "window" : "full",
        start_time_s: row.start_time_s,
        duration_s: row.duration_s,
      });
      started.current = Date.now();
      setProgress(0);
      setStatus("queued");
    } finally {
      setRetrying(false);
    }
  }

  if (status === "failed") {
    return (
      <PageShell className="max-w-xl">
        <Card className="mt-16 p-8 text-center">
          <div className="mx-auto grid size-14 place-items-center rounded-2xl bg-rose-500/10 text-rose-300 ring-1 ring-rose-400/25 [&_svg]:size-7">
            <CircleAlert />
          </div>
          <h1 className="mt-6 text-2xl font-semibold tracking-tight text-white">We couldn't finish this analysis</h1>
          <p className="mt-2 text-sm leading-relaxed text-zinc-400">{message || "Something went wrong while processing the video."}</p>
          <div className="mt-8 flex flex-wrap justify-center gap-3">
            <Button loading={retrying} onClick={retry}>
              <RotateCcw /> Try again
            </Button>
            <Button asChild variant="secondary">
              <Link to="/upload">
                <Upload /> Upload another video
              </Link>
            </Button>
          </div>
        </Card>
      </PageShell>
    );
  }

  const pct = Math.min(100, Math.max(0, progress));
  const currentIndex = STAGES.reduce((acc, [, at], i) => (pct >= at ? i : acc), -1);
  const R = 52;
  const C = 2 * Math.PI * R;

  return (
    <PageShell className="max-w-3xl">
      <FlowSteps current={2} />
      <div className="grid items-center gap-10 pt-12 md:grid-cols-[auto_1fr]">
        <div className="relative mx-auto size-52">
          <div aria-hidden="true" className="absolute inset-6 rounded-full bg-pitch-400/15 blur-2xl" />
          <svg viewBox="0 0 120 120" className="relative size-full -rotate-90">
            <circle cx="60" cy="60" r={R} fill="none" stroke="rgb(255 255 255 / 0.06)" strokeWidth="8" />
            <motion.circle
              cx="60"
              cy="60"
              r={R}
              fill="none"
              stroke="url(#ring)"
              strokeWidth="8"
              strokeLinecap="round"
              strokeDasharray={C}
              animate={{ strokeDashoffset: C * (1 - Math.max(pct, 2) / 100) }}
              transition={{ duration: 0.8, ease: "easeOut" }}
            />
            <defs>
              <linearGradient id="ring" x1="0" y1="0" x2="1" y2="1">
                <stop offset="0" stopColor="#7eecc0" />
                <stop offset="1" stopColor="#1cc488" />
              </linearGradient>
            </defs>
          </svg>
          <div className="absolute inset-0 grid place-items-center text-center">
            <div>
              <p className="font-mono text-4xl font-semibold text-white tabular">{Math.round(pct)}%</p>
              <p className="mt-1 font-mono text-[12px] text-zinc-500 tabular">{formatElapsed(now - started.current)} elapsed</p>
            </div>
          </div>
        </div>

        <div>
          <p className="text-[12px] font-medium tracking-[0.18em] text-pitch-400 uppercase">
            {status === "queued" ? "Queued" : "Analyzing"}
          </p>
          <h1 className="mt-2 text-3xl font-semibold tracking-tight text-white">Working on your match</h1>
          <p className="mt-2 text-sm leading-relaxed text-zinc-400">
            You can leave this page. Analysis keeps running, and the match will be waiting in{" "}
            <Link to="/matches" className="text-pitch-300 hover:text-pitch-200">
              your matches
            </Link>
            .
          </p>
        </div>
      </div>

      <Card className="mt-10 p-2">
        <ol>
          {STAGES.map(([label], i) => {
            const done = i < currentIndex || pct >= 100;
            const active = i === currentIndex && pct < 100;
            return (
              <li
                key={label}
                className={cn("flex items-center gap-3 rounded-xl px-4 py-3 text-sm transition-colors", active && "bg-pitch-400/[0.06]")}
              >
                <span
                  className={cn(
                    "grid size-6 shrink-0 place-items-center rounded-full [&_svg]:size-3.5",
                    done && "bg-pitch-400 text-ink-950",
                    active && "text-pitch-300",
                    !done && !active && "ring-1 ring-white/10",
                  )}
                >
                  {done ? <Check /> : active ? <Spinner className="size-4" /> : null}
                </span>
                <span className={cn(done ? "text-zinc-300" : active ? "font-medium text-white" : "text-zinc-500")}>{label}</span>
                {active && message ? <span className="ml-auto hidden truncate text-[12px] text-zinc-500 sm:block">{message}</span> : null}
              </li>
            );
          })}
        </ol>
      </Card>
      <p className="mt-4 text-center text-[12px] text-zinc-500">
        Progress moves in steps as each stage finishes. A short window takes minutes; a full match takes much longer.
      </p>
    </PageShell>
  );
}
