import { ArrowRight, Activity, Fingerprint, ScanEye, ShieldCheck, Upload, Cpu, LayoutDashboard } from "lucide-react";
import { motion } from "motion/react";
import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { PageShell } from "../components/layout/PageShell";
import { PitchVisual } from "../components/marketing/PitchVisual";
import { Badge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";

const reveal = {
  initial: { opacity: 0, y: 24 },
  whileInView: { opacity: 1, y: 0 },
  viewport: { once: true, margin: "-80px" },
  transition: { duration: 0.6, ease: [0.22, 1, 0.36, 1] as const },
};

const FEATURES = [
  {
    icon: <ScanEye />,
    title: "Tracks every player",
    body: "Players and the ball are followed frame by frame, even as the camera pans across the pitch.",
  },
  {
    icon: <Fingerprint />,
    title: "Knows who's who",
    body: "Appearance matching and jersey-number reading stitch each player back into one identity.",
  },
  {
    icon: <Activity />,
    title: "Reads the game",
    body: "Possession, completed passes, interceptions and shots, worked out from where the ball and players are.",
  },
  {
    icon: <ShieldCheck />,
    title: "Honest numbers",
    body: "Unknown stays unknown. Every dashboard shows what the footage can and can't support.",
  },
];

const STEPS = [
  { icon: <Upload />, title: "Upload", body: "Drop in a match recording. MP4, MOV, AVI or MKV." },
  { icon: <Cpu />, title: "Analyze", body: "Name the teams and let TactiVision run detection, tracking and events." },
  { icon: <LayoutDashboard />, title: "Explore", body: "Open the dashboard: score, possession, team comparison and every player." },
];

export function HomePage() {
  const { user } = useAuth();
  const primary = user ? { to: "/upload", label: "Analyze a match" } : { to: "/signup", label: "Get started free" };
  const secondary = user ? { to: "/matches", label: "My matches" } : { to: "/login", label: "Sign in" };

  return (
    <PageShell>
      <section className="grid items-center gap-16 pt-14 pb-20 lg:grid-cols-[1.05fr_1fr] lg:pt-24">
        <div>
          <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5 }}>
            <Badge tone="pitch" dot>
              Indoor football match analysis
            </Badge>
          </motion.div>
          <motion.h1
            initial={{ opacity: 0, y: 18 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.7, delay: 0.08, ease: [0.22, 1, 0.36, 1] }}
            className="mt-6 text-5xl leading-[1.02] font-semibold tracking-[-0.035em] text-white sm:text-6xl lg:text-7xl"
          >
            See the match
            <br />
            <span className="text-gradient">behind the footage.</span>
          </motion.h1>
          <motion.p
            initial={{ opacity: 0, y: 18 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.7, delay: 0.16, ease: [0.22, 1, 0.36, 1] }}
            className="mt-6 max-w-xl text-lg leading-relaxed text-zinc-400"
          >
            Upload an indoor football video. TactiVision follows every player and the ball, then turns it into
            possession, passing and shooting stats you can actually read.
          </motion.p>
          <motion.div
            initial={{ opacity: 0, y: 18 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.7, delay: 0.24, ease: [0.22, 1, 0.36, 1] }}
            className="mt-9 flex flex-wrap gap-3"
          >
            <Button asChild size="lg">
              <Link to={primary.to}>
                {primary.label} <ArrowRight />
              </Link>
            </Button>
            <Button asChild size="lg" variant="secondary">
              <Link to={secondary.to}>{secondary.label}</Link>
            </Button>
          </motion.div>
          <motion.ul
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.8, delay: 0.5 }}
            className="mt-10 flex flex-wrap gap-x-6 gap-y-2 text-[13px] text-zinc-500"
          >
            {["Player tracking", "Jersey recognition", "Possession & events"].map((t) => (
              <li key={t} className="flex items-center gap-2">
                <span className="size-1 rounded-full bg-pitch-400" />
                {t}
              </li>
            ))}
          </motion.ul>
        </div>

        <motion.div
          initial={{ opacity: 0, scale: 0.96, y: 20 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          transition={{ duration: 0.9, delay: 0.15, ease: [0.22, 1, 0.36, 1] }}
        >
          <PitchVisual />
        </motion.div>
      </section>

      <section className="py-20">
        <motion.div {...reveal} className="max-w-2xl">
          <p className="text-[12px] font-medium tracking-[0.18em] text-pitch-400 uppercase">What you get</p>
          <h2 className="mt-3 text-3xl font-semibold tracking-tight text-white sm:text-4xl">
            From raw footage to a match you understand.
          </h2>
        </motion.div>
        <div className="mt-12 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {FEATURES.map((f, i) => (
            <motion.article
              key={f.title}
              {...reveal}
              transition={{ ...reveal.transition, delay: i * 0.08 }}
              className="glass group rounded-2xl p-6 transition-colors hover:border-pitch-400/25 hover:bg-white/[0.05]"
            >
              <div className="grid size-11 place-items-center rounded-xl bg-pitch-400/10 text-pitch-300 ring-1 ring-pitch-400/20 transition-transform duration-300 group-hover:scale-110 [&_svg]:size-5">
                {f.icon}
              </div>
              <h3 className="mt-5 text-[17px] font-semibold tracking-tight text-white">{f.title}</h3>
              <p className="mt-2 text-sm leading-relaxed text-zinc-400">{f.body}</p>
            </motion.article>
          ))}
        </div>
      </section>

      <section className="py-20">
        <motion.div {...reveal} className="text-center">
          <p className="text-[12px] font-medium tracking-[0.18em] text-pitch-400 uppercase">How it works</p>
          <h2 className="mt-3 text-3xl font-semibold tracking-tight text-white sm:text-4xl">Three steps to your dashboard.</h2>
        </motion.div>
        <div className="relative mt-14 grid gap-6 md:grid-cols-3">
          <div
            aria-hidden="true"
            className="absolute top-7 right-[16%] left-[16%] hidden h-px bg-linear-to-r from-transparent via-pitch-400/40 to-transparent md:block"
          />
          {STEPS.map((s, i) => (
            <Step key={s.title} n={i + 1} icon={s.icon} title={s.title} body={s.body} delay={i * 0.12} />
          ))}
        </div>
      </section>

      <motion.section {...reveal} className="py-10">
        <div className="relative overflow-hidden rounded-3xl border border-pitch-400/20 bg-linear-to-br from-pitch-600/25 via-ink-900 to-ink-900 px-6 py-14 text-center sm:px-12">
          <div aria-hidden="true" className="absolute -top-24 left-1/2 size-72 -translate-x-1/2 rounded-full bg-pitch-400/20 blur-3xl" />
          <h2 className="relative text-3xl font-semibold tracking-tight text-white sm:text-4xl">Your next match, in numbers.</h2>
          <p className="relative mx-auto mt-3 max-w-lg text-zinc-400">
            Upload a recording and get a full match dashboard. Short clips are ready in minutes.
          </p>
          <div className="relative mt-8 flex justify-center">
            <Button asChild size="lg">
              <Link to={primary.to}>
                {primary.label} <ArrowRight />
              </Link>
            </Button>
          </div>
        </div>
      </motion.section>
    </PageShell>
  );
}

function Step({ n, icon, title, body, delay }: { n: number; icon: ReactNode; title: string; body: string; delay: number }) {
  return (
    <motion.div {...reveal} transition={{ ...reveal.transition, delay }} className="relative text-center">
      <div className="relative mx-auto grid size-14 place-items-center rounded-2xl border border-white/10 bg-ink-850 text-pitch-300 shadow-glow [&_svg]:size-6">
        {icon}
        <span className="absolute -top-2 -right-2 grid size-6 place-items-center rounded-full bg-gold-400 font-mono text-[11px] font-semibold text-ink-950">
          {n}
        </span>
      </div>
      <h3 className="mt-5 text-lg font-semibold text-white">{title}</h3>
      <p className="mx-auto mt-2 max-w-xs text-sm leading-relaxed text-zinc-400">{body}</p>
    </motion.div>
  );
}
