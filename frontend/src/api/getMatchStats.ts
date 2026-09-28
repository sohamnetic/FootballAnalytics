import type { MatchStats } from "../types/matchStats";
import { apiFetch, apiUrl, readError } from "./client";

export interface MatchRecord {
  match_id: string;
  filename?: string;
  status?: string;
  team_a?: string;
  team_b?: string;
  camera?: string;
  created_at?: string;
  completed_at?: string;
  duration_s?: number | null;
  goals_a?: number;
  goals_b?: number;
  progress?: number;
  stage?: string;
  message?: string;
  analysis?: string;
  start_time_s?: number | null;
}

export async function getMatchStats(matchId: string): Promise<MatchStats> {
  const response = await apiFetch(`/api/matches/${matchId}/stats`);
  if (!response.ok) {
    throw new Error(`Failed to load match stats (${response.status})`);
  }
  return response.json() as Promise<MatchStats>;
}

export interface UploadResult {
  match_id: string;
  filename: string;
  status: string;
  bytes: number;
}

interface UploadPlan {
  match_id: string;
  upload_id: string;
  part_size: number;
  urls: string[];
}

const PARALLEL_PARTS = 3;
const PART_TRIES = 4;

// One part straight to storage. XHR because fetch can't report upload progress.
function putPart(url: string, blob: Blob, onBytes: (sent: number) => void): Promise<string> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("PUT", apiUrl(url));
    xhr.upload.onprogress = (e) => onBytes(e.loaded);
    xhr.onload = () => {
      const etag = xhr.getResponseHeader("ETag");
      if (xhr.status >= 200 && xhr.status < 300 && etag) resolve(etag);
      else reject(new Error(etag ? `Upload failed (${xhr.status})` : "Upload blocked: storage didn't return an ETag"));
    };
    xhr.onerror = () => reject(new Error("Upload failed: network error"));
    xhr.send(blob);
  });
}

// The video goes to storage in parts (a few in parallel, each retried), so a
// dropped connection only costs one part and the API never handles the bytes.
export async function uploadMatchVideo(
  file: File,
  onProgress?: (fraction: number) => void,
  durationS?: number | null,
): Promise<UploadResult> {
  const start = await apiFetch("/api/matches/uploads", {
    method: "POST",
    body: JSON.stringify({
      filename: file.name,
      size: file.size,
      duration_s: durationS && Number.isFinite(durationS) ? durationS : null,
    }),
  });
  if (!start.ok) throw new Error(await readError(start, "Could not start the upload"));
  const plan = (await start.json()) as UploadPlan;

  const sent = new Array<number>(plan.urls.length).fill(0);
  const report = () => onProgress?.(Math.min(sent.reduce((a, b) => a + b, 0) / file.size, 1));
  const etags: { number: number; etag: string }[] = [];
  let next = 0;

  async function uploadPart(index: number) {
    const blob = file.slice(index * plan.part_size, (index + 1) * plan.part_size);
    for (let attempt = 1; ; attempt++) {
      try {
        const etag = await putPart(plan.urls[index], blob, (bytes) => {
          sent[index] = bytes;
          report();
        });
        sent[index] = blob.size;
        report();
        etags.push({ number: index + 1, etag });
        return;
      } catch (err) {
        sent[index] = 0;
        report();
        if (attempt >= PART_TRIES) throw err;
        await new Promise((r) => setTimeout(r, 2000 * attempt));
      }
    }
  }

  async function lane() {
    while (next < plan.urls.length) await uploadPart(next++);
  }

  try {
    await Promise.all(Array.from({ length: Math.min(PARALLEL_PARTS, plan.urls.length) }, lane));
  } catch (err) {
    apiFetch(`/api/matches/${plan.match_id}/upload/abort`, { method: "POST" }).catch(() => undefined);
    throw err;
  }

  const done = await apiFetch(`/api/matches/${plan.match_id}/upload/complete`, {
    method: "POST",
    body: JSON.stringify({ upload_id: plan.upload_id, parts: etags }),
  });
  if (!done.ok) throw new Error(await readError(done, "Upload failed"));
  return done.json() as Promise<UploadResult>;
}

export async function startAnalysis(
  matchId: string,
  payload: {
    team_a: string;
    team_b: string;
    camera: string;
    analysis: "full" | "window";
    start_time_s?: number | null;
    duration_s?: number | null;
  },
): Promise<{ match_id: string; status: string }> {
  const response = await apiFetch(`/api/matches/${matchId}/analyze`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error(await readError(response, "Could not start analysis"));
  }
  return response.json();
}

export async function getMatchStatus(matchId: string) {
  const response = await apiFetch(`/api/matches/${matchId}/status`);
  if (!response.ok) {
    throw new Error("Could not load status");
  }
  return response.json() as Promise<{
    match_id: string;
    status: string;
    progress: number;
    stage: string;
    message: string;
    progress_kind?: string;
    log_tail?: string | null;
  }>;
}

export async function listMatches(): Promise<{ matches: MatchRecord[] }> {
  const response = await apiFetch("/api/matches");
  if (!response.ok) {
    throw new Error("Could not load matches");
  }
  return response.json();
}

export async function getMatchMedia(matchId: string): Promise<{
  source_video: boolean;
  analysis_video: boolean;
}> {
  const response = await apiFetch(`/api/matches/${matchId}/media`);
  if (!response.ok) {
    throw new Error("Could not load media info");
  }
  return response.json();
}

export async function getMatch(matchId: string): Promise<MatchRecord> {
  const response = await apiFetch(`/api/matches/${matchId}`);
  if (!response.ok) {
    throw new Error("Match not found");
  }
  return response.json();
}

export async function deleteMatch(matchId: string): Promise<void> {
  const response = await apiFetch(`/api/matches/${matchId}`, { method: "DELETE" });
  if (!response.ok) {
    throw new Error(await readError(response, "Could not delete match"));
  }
}
