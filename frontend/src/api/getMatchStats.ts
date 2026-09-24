import type { MatchStats } from "../types/matchStats";
import { apiFetch, getToken, readError } from "./client";

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

// XMLHttpRequest rather than fetch: fetch cannot report upload progress, and
// match files can be several GB.
export function uploadMatchVideo(file: File, onProgress?: (fraction: number) => void): Promise<UploadResult> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/api/matches/upload");
    const token = getToken();
    if (token) xhr.setRequestHeader("Authorization", `Bearer ${token}`);
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) onProgress?.(e.loaded / e.total);
    };
    xhr.onload = () => {
      let data: { detail?: unknown } & Partial<UploadResult> = {};
      try {
        data = JSON.parse(xhr.responseText);
      } catch {
        /* non-JSON error body */
      }
      if (xhr.status >= 200 && xhr.status < 300) resolve(data as UploadResult);
      else reject(new Error(typeof data.detail === "string" ? data.detail : "Upload failed"));
    };
    xhr.onerror = () => reject(new Error("Upload failed: the server could not be reached"));
    const body = new FormData();
    body.append("file", file);
    xhr.send(body);
  });
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
