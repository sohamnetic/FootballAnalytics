import { ArrowLeft, Camera, Clapperboard, Film, Play, Scissors } from "lucide-react";
import { motion } from "motion/react";
import { useEffect, useState, type ReactNode } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { getMatch, startAnalysis } from "../api/getMatchStats";
import { FlowSteps } from "../components/layout/FlowSteps";
import { PageHeading, PageShell } from "../components/layout/PageShell";
import { Alert } from "../components/ui/Alert";
import { Button } from "../components/ui/Button";
import { Card, CardBody, CardHeader } from "../components/ui/Card";
import { Field } from "../components/ui/Field";
import { cn } from "../lib/cn";

type Mode = "full" | "window";

export function SetupPage() {
  const { matchId } = useParams();
  const navigate = useNavigate();
  const [filename, setFilename] = useState("");
  const [teamA, setTeamA] = useState("Team A");
  const [teamB, setTeamB] = useState("Team B");
  const [camera, setCamera] = useState("Camera 001");
  const [analysis, setAnalysis] = useState<Mode>("full");
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
        team_a: teamA.trim() || "Team A",
        team_b: teamB.trim() || "Team B",
        camera,
        analysis,
        start_time_s: analysis === "window" ? Number(startTime) : 0,
        duration_s: analysis === "window" ? Number(duration) : null,
      });
      navigate(`/matches/${matchId}/processing`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not start analysis");
      setBusy(false);
    }
  }

  return (
    <PageShell className="max-w-3xl">
      <FlowSteps current={1} />
      <PageHeading eyebrow="Match setup" title="Who's playing?" description="Name both sides so the dashboard reads like your match." />

      {filename ? (
        <div className="mb-6 flex items-center gap-3 rounded-xl border border-white/[0.06] bg-white/[0.02] px-4 py-3 text-sm">
          <Film className="size-4 text-zinc-500" />
          <span className="truncate text-zinc-300">{filename}</span>
        </div>
      ) : null}

      <div className="grid gap-4 sm:grid-cols-2">
        <TeamCard side="a" label="Home side" value={teamA} onChange={setTeamA} />
        <TeamCard side="b" label="Away side" value={teamB} onChange={setTeamB} />
      </div>

      <Card className="mt-4">
        <CardHeader icon={<Clapperboard />} title="What should we analyze?" description="A short window is handy for trying things out." />
        <CardBody className="space-y-5">
          <div className="grid gap-3 sm:grid-cols-2" role="radiogroup" aria-label="Analysis mode">
            <ModeOption
              selected={analysis === "full"}
              onSelect={() => setAnalysis("full")}
              icon={<Play />}
              title="Full match"
              body="Every minute of the video. Takes longer."
            />
            <ModeOption
              selected={analysis === "window"}
              onSelect={() => setAnalysis("window")}
              icon={<Scissors />}
              title="Custom window"
              body="Just a slice, e.g. 40 seconds. Ready in minutes."
            />
          </div>
          {analysis === "window" ? (
            <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} className="grid gap-4 sm:grid-cols-2">
              <Field label="Start at (seconds)" type="number" min={0} value={startTime} onChange={(e) => setStartTime(e.target.value)} />
              <Field label="Length (seconds)" type="number" min={1} value={duration} onChange={(e) => setDuration(e.target.value)} />
            </motion.div>
          ) : null}
          <Field label="Camera" icon={<Camera />} value={camera} onChange={(e) => setCamera(e.target.value)} hint="Just a label, useful if you film from several spots." />
        </CardBody>
      </Card>

      {error ? <Alert tone="error" className="mt-4">{error}</Alert> : null}

      <div className="mt-6 flex items-center justify-between">
        <Button asChild variant="ghost">
          <Link to="/matches">
            <ArrowLeft /> Back
          </Link>
        </Button>
        <Button size="lg" loading={busy} onClick={onStart}>
          {busy ? "Starting" : "Start analysis"}
        </Button>
      </div>
    </PageShell>
  );
}

function TeamCard({ side, label, value, onChange }: { side: "a" | "b"; label: string; value: string; onChange: (v: string) => void }) {
  return (
    <Card className="relative overflow-hidden p-5">
      <div aria-hidden="true" className={cn("absolute inset-x-0 top-0 h-1", side === "a" ? "bg-team-a" : "bg-team-b")} />
      <div aria-hidden="true" className={cn("absolute -top-16 -right-16 size-40 rounded-full blur-3xl", side === "a" ? "bg-team-a/15" : "bg-team-b/15")} />
      <div className="relative flex items-center gap-2 text-[12px] font-medium tracking-[0.14em] text-zinc-400 uppercase">
        <span className={cn("size-2 rounded-full", side === "a" ? "bg-team-a" : "bg-team-b")} />
        {label}
      </div>
      <input
        aria-label={`${label} name`}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="relative mt-3 w-full border-b border-white/10 bg-transparent pb-2 text-2xl font-semibold tracking-tight text-white transition-colors outline-none focus:border-pitch-400"
      />
    </Card>
  );
}

function ModeOption({ selected, onSelect, icon, title, body }: { selected: boolean; onSelect: () => void; icon: ReactNode; title: string; body: string }) {
  return (
    <button
      type="button"
      role="radio"
      aria-checked={selected}
      onClick={onSelect}
      className={cn(
        "flex cursor-pointer items-start gap-3 rounded-xl border p-4 text-left transition-all duration-200",
        selected ? "border-pitch-400/60 bg-pitch-400/[0.07] ring-4 ring-pitch-400/10" : "border-white/[0.08] bg-white/[0.02] hover:border-white/15",
      )}
    >
      <span className={cn("mt-0.5 grid size-8 shrink-0 place-items-center rounded-lg [&_svg]:size-4", selected ? "bg-pitch-400 text-ink-950" : "bg-white/[0.06] text-zinc-400")}>
        {icon}
      </span>
      <span>
        <span className="block text-sm font-semibold text-white">{title}</span>
        <span className="mt-0.5 block text-[13px] leading-snug text-zinc-400">{body}</span>
      </span>
    </button>
  );
}
