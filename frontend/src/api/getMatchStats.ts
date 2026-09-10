import type { MatchStats } from "../types/matchStats";
import { apiFetch, readError } from "./client";

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

export async function uploadMatchVideo(file: File): Promise<{
  match_id: string;
  filename: string;
  status: string;
  bytes: number;
}> {
  const body = new FormData();
  body.append("file", file);
  const response = await apiFetch("/api/matches/upload", { method: "POST", body });
  if (!response.ok) {
    throw new Error(await readError(response, "Upload failed"));
  }
  return response.json();
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
