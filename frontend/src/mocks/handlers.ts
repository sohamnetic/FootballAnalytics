// Fake API for demo mode (npm run dev:mock), so the site works without the
// Python backend. The stats are from a real run.
import { delay, http, HttpResponse } from "msw";
import stats from "./matchStats.json";

type Row = {
  match_id: string;
  filename: string;
  status: string;
  team_a: string;
  team_b: string;
  camera: string;
  analysis?: string;
  start_time_s?: number | null;
  duration_s?: number | null;
  created_at: string;
  completed_at?: string;
  goals_a?: number;
  goals_b?: number;
  started?: number;
};

const USER = { id: "demo", email: "demo@tactivision.local", name: "Demo Coach" };
const ago = (h: number) => new Date(Date.now() - h * 3_600_000).toISOString();
const ANALYSIS_MS = 30_000;

const rows: Row[] = [
  {
    match_id: "demo-0001", filename: "sunday_league_final.mp4", status: "completed",
    team_a: "Red Lions", team_b: "Mint FC", camera: "Camera 001",
    created_at: ago(30), completed_at: ago(29),
  },
  {
    match_id: "demo-0002", filename: "cup_semi.mp4", status: "processing",
    team_a: "Northside", team_b: "Harbour Town", camera: "Camera 001",
    created_at: ago(0.1), started: Date.now(),
  },
  {
    match_id: "demo-0003", filename: "training_scrimmage.mov", status: "uploaded",
    team_a: "Team A", team_b: "Team B", camera: "Camera 001", created_at: ago(72),
  },
  {
    match_id: "demo-0004", filename: "friday_night.mkv", status: "failed",
    team_a: "Eastfield", team_b: "Riverside", camera: "Camera 002", created_at: ago(200),
  },
];

const STAGES: [number, string][] = [
  [5, "Preparing video"], [12, "Detecting players"], [20, "Tracking players"], [40, "Detecting ball"],
  [55, "Calculating possession"], [65, "Assigning teams"], [72, "Analyzing passes"], [80, "Analyzing turnovers"],
  [90, "Analyzing shots"], [98, "Generating statistics"],
];

function advance(row: Row) {
  if ((row.status === "processing" || row.status === "queued") && row.started) {
    const pct = Math.min(100, ((Date.now() - row.started) / ANALYSIS_MS) * 100);
    if (pct >= 100) {
      row.status = "completed";
      row.completed_at = new Date().toISOString();
    } else {
      row.status = "processing";
    }
    return pct;
  }
  return row.status === "completed" ? 100 : 0;
}

const find = (id: string | readonly string[] | undefined) => rows.find((r) => r.match_id === id);
const signedIn = (request: Request) => (request.headers.get("Authorization") ?? "").startsWith("Bearer ");
const unauthorized = () => HttpResponse.json({ detail: "Please sign in" }, { status: 401 });

export const handlers = [
  http.get("/api/auth/me", ({ request }) => (signedIn(request) ? HttpResponse.json({ user: USER }) : unauthorized())),
  http.post("/api/auth/login", async () => {
    await delay(600);
    return HttpResponse.json({ user: USER, token: "demo-token" });
  }),
  http.post("/api/auth/signup", async () => {
    await delay(600);
    return HttpResponse.json({ user: USER, token: "demo-token" });
  }),

  http.get("/api/matches", async ({ request }) => {
    if (!signedIn(request)) return unauthorized();
    await delay(500);
    rows.forEach(advance);
    return HttpResponse.json({ matches: rows });
  }),

  http.post("/api/matches/upload", async () => {
    await delay(1200);
    const row: Row = {
      match_id: `demo-${String(rows.length + 1).padStart(4, "0")}-${Date.now()}`,
      filename: "new_upload.mp4", status: "uploaded", team_a: "Team A", team_b: "Team B",
      camera: "Camera 001", created_at: new Date().toISOString(),
    };
    rows.unshift(row);
    return HttpResponse.json({ match_id: row.match_id, filename: row.filename, status: row.status, bytes: 0 });
  }),

  http.get("/api/matches/:id", ({ params }) => {
    const row = find(params.id);
    return row ? HttpResponse.json(row) : HttpResponse.json({ detail: "Match not found" }, { status: 404 });
  }),

  http.delete("/api/matches/:id", async ({ params }) => {
    await delay(500);
    const i = rows.findIndex((r) => r.match_id === params.id);
    if (i >= 0) rows.splice(i, 1);
    return HttpResponse.json({ ok: true });
  }),

  http.post("/api/matches/:id/analyze", async ({ params, request }) => {
    const row = find(params.id);
    if (!row) return HttpResponse.json({ detail: "Match not found" }, { status: 404 });
    const body = (await request.json()) as Partial<Row> & { analysis?: string };
    Object.assign(row, {
      team_a: body.team_a, team_b: body.team_b, camera: body.camera, analysis: body.analysis,
      start_time_s: body.start_time_s, duration_s: body.duration_s,
      status: "queued", started: Date.now(),
    });
    return HttpResponse.json({ match_id: row.match_id, status: row.status });
  }),

  http.get("/api/matches/:id/status", ({ params }) => {
    const row = find(params.id);
    if (!row) return HttpResponse.json({ detail: "Match not found" }, { status: 404 });
    const progress = Math.round(advance(row));
    const stage = [...STAGES].reverse().find(([at]) => progress >= at)?.[1] ?? "Queued";
    return HttpResponse.json({
      match_id: row.match_id,
      status: row.status,
      progress,
      stage: row.status === "completed" ? "Completed" : stage,
      message: row.status === "failed" ? "The video could not be decoded." : "",
    });
  }),

  http.get("/api/matches/:id/stats", async ({ params }) => {
    const row = find(params.id);
    if (!row || row.status !== "completed") return HttpResponse.json({ detail: "Not ready" }, { status: 409 });
    await delay(700);
    return HttpResponse.json({
      ...stats,
      match: { ...stats.match, team_a_name: row.team_a, team_b_name: row.team_b, match_id: row.match_id, video: row.filename },
    });
  }),

  http.get("/api/matches/:id/media", () => HttpResponse.json({ source_video: false, analysis_video: false })),
];
