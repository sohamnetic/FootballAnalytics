import { motion, useReducedMotion } from "motion/react";

type Path = { x: number[]; y: number[] };

const DURATION = 12;

// Each player loops through a few positions; the ball is passed between
// players at the same keyframe times so it always lands on someone.
const RED: Path[] = [
  { x: [120, 150, 135, 120], y: [190, 170, 215, 190] },
  { x: [210, 245, 230, 210], y: [110, 130, 95, 110] },
  { x: [215, 250, 270, 215], y: [270, 250, 285, 270] },
  { x: [300, 330, 310, 300], y: [175, 205, 160, 175] },
  { x: [360, 395, 380, 360], y: [95, 120, 140, 95] },
];
const BLUE: Path[] = [
  { x: [480, 455, 470, 480], y: [190, 210, 170, 190] },
  { x: [395, 370, 350, 395], y: [250, 230, 270, 250] },
  { x: [420, 440, 405, 420], y: [140, 115, 165, 140] },
  { x: [270, 290, 300, 270], y: [140, 150, 120, 140] },
  { x: [330, 300, 320, 330], y: [300, 280, 262, 300] },
];
const TRACKED = RED[3];
const BALL: Path = {
  x: [RED[0].x[0] + 10, RED[1].x[1] + 10, RED[3].x[2] + 10, RED[0].x[3] + 10],
  y: [RED[0].y[0] + 8, RED[1].y[1] + 8, RED[3].y[2] + 8, RED[0].y[3] + 8],
};

function Player({ path, color, delay, still }: { path: Path; color: string; delay: number; still: boolean }) {
  if (still) return <circle cx={path.x[0]} cy={path.y[0]} r={7} fill={color} stroke="#050907" strokeWidth={2} />;
  return (
    <motion.circle
      r={7}
      fill={color}
      stroke="#050907"
      strokeWidth={2}
      initial={{ cx: path.x[0], cy: path.y[0] }}
      animate={{ cx: path.x, cy: path.y }}
      transition={{ duration: DURATION, repeat: Infinity, ease: "easeInOut", delay }}
    />
  );
}

export function PitchVisual() {
  const still = useReducedMotion() ?? false;
  return (
    <div className="relative">
      <div className="absolute -inset-8 -z-10 rounded-[3rem] bg-pitch-400/10 blur-3xl" aria-hidden="true" />
      <div className="glass overflow-hidden rounded-3xl p-2.5">
        <svg viewBox="0 0 600 380" className="block w-full" role="img" aria-label="Animated illustration of players being tracked on a pitch">
          <defs>
            <linearGradient id="turf" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0" stopColor="#0f3a28" />
              <stop offset="1" stopColor="#0a2a1d" />
            </linearGradient>
            <radialGradient id="flood" cx="0.5" cy="0" r="0.9">
              <stop offset="0" stopColor="#3ee0a3" stopOpacity="0.22" />
              <stop offset="1" stopColor="#3ee0a3" stopOpacity="0" />
            </radialGradient>
          </defs>
          <rect width="600" height="380" rx="18" fill="url(#turf)" />
          {Array.from({ length: 8 }, (_, i) => (
            <rect key={i} x={i * 75} width="37.5" height="380" fill="#ffffff" opacity="0.025" />
          ))}
          <rect width="600" height="380" rx="18" fill="url(#flood)" />
          <g fill="none" stroke="#ffffff" strokeOpacity="0.28" strokeWidth="2">
            <rect x="24" y="24" width="552" height="332" rx="6" />
            <line x1="300" y1="24" x2="300" y2="356" />
            <circle cx="300" cy="190" r="46" />
            <rect x="24" y="120" width="70" height="140" />
            <rect x="506" y="120" width="70" height="140" />
            <rect x="14" y="160" width="10" height="60" />
            <rect x="576" y="160" width="10" height="60" />
          </g>
          <circle cx="300" cy="190" r="3" fill="#ffffff" opacity="0.4" />

          {RED.map((p, i) => (
            <Player key={`r${i}`} path={p} color="#ff7a66" delay={0} still={still} />
          ))}
          {BLUE.map((p, i) => (
            <Player key={`b${i}`} path={p} color="#5cc8ff" delay={0} still={still} />
          ))}
          <circle cx="552" cy="190" r="7" fill="#e4c56a" stroke="#050907" strokeWidth={2} />

          {/* tracking box that follows one player */}
          <motion.g
            initial={{ x: TRACKED.x[0], y: TRACKED.y[0] }}
            animate={still ? undefined : { x: TRACKED.x, y: TRACKED.y }}
            transition={{ duration: DURATION, repeat: Infinity, ease: "easeInOut" }}
          >
            <rect x="-16" y="-20" width="32" height="40" rx="5" fill="none" stroke="#3ee0a3" strokeWidth="1.8" />
            <rect x="-16" y="-38" width="64" height="15" rx="4" fill="#3ee0a3" />
            <text x="-11" y="-27" fontSize="10" fontWeight="600" fill="#050907" fontFamily="Geist Mono Variable, monospace">
              #10 · 97%
            </text>
          </motion.g>

          {/* ball */}
          {still ? (
            <circle cx={BALL.x[0]} cy={BALL.y[0]} r={4.5} fill="#ffffff" />
          ) : (
            <motion.circle
              r={4.5}
              fill="#ffffff"
              initial={{ cx: BALL.x[0], cy: BALL.y[0] }}
              animate={{ cx: BALL.x, cy: BALL.y }}
              transition={{ duration: DURATION, repeat: Infinity, ease: "easeInOut" }}
              style={{ filter: "drop-shadow(0 0 6px rgba(255,255,255,0.8))" }}
            />
          )}
        </svg>
      </div>

      <motion.div
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.6, duration: 0.6 }}
        className="glass absolute -bottom-6 left-3 w-52 rounded-2xl bg-ink-900/80 p-4 sm:-left-8"
      >
        <p className="text-[11px] font-medium tracking-[0.16em] text-zinc-400 uppercase">Possession</p>
        <div className="mt-2 flex items-baseline justify-between font-mono text-sm tabular">
          <span className="text-team-a">59%</span>
          <span className="text-team-b">41%</span>
        </div>
        <div className="mt-2 flex h-1.5 overflow-hidden rounded-full bg-white/5">
          <motion.span
            className="bg-team-a"
            initial={{ width: "50%" }}
            animate={{ width: "59%" }}
            transition={{ delay: 1, duration: 1.2, ease: "easeOut" }}
          />
          <span className="flex-1 bg-team-b" />
        </div>
      </motion.div>

      <motion.div
        initial={{ opacity: 0, y: -16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.9, duration: 0.6 }}
        className="glass absolute -top-5 -right-3 flex items-center gap-2 rounded-full bg-ink-900/80 px-3.5 py-2 text-[12px] text-zinc-300 sm:-right-6"
      >
        <span className="size-2 animate-pulse-soft rounded-full bg-pitch-400" />
        Tracking players &amp; ball
      </motion.div>
    </div>
  );
}
