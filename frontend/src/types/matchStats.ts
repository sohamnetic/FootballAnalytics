export type TeamId = "team_a" | "team_b";

export interface MatchInfo {
  video: string;
  start_time_s: number | null;
  duration_s: number | null;
  fps: number;
  clip_duration_used_s?: number;
  team_a_name?: string;
  team_b_name?: string;
  camera?: string;
  match_id?: string;
}

export interface TeamStats {
  possession_percentage: number | null;
  possession_seconds?: number | null;
  goals: number;
  shots: number;
  shots_on_target: number;
  completed_passes: number;
  pass_accuracy: number | null;
  interceptions: number;
  ball_recoveries: number;
}

export interface PlayerStats {
  stable_id: number;
  team_id: TeamId | string;
  goals: number;
  shots: number;
  shots_on_target: number;
  shot_accuracy: number | null;
  shot_conversion_rate: number | null;
  successful_passes: number;
  pass_accuracy: number | null;
  interceptions: number;
  ball_recoveries: number;
  ball_possession_time_seconds: number;
}

export interface EventSummary {
  possession_intervals: number;
  possession_transitions?: number;
  completed_passes: number;
  interceptions: number;
  recoveries: number;
  shots: number;
  shots_on_target: number;
  goals: number;
}

export interface DataQuality {
  stable_ids: number;
  identity_audit_stable_ids?: number | null;
  valid_team_players?: number;
  team_assignment_counts?: Record<string, number>;
  estimated_visible_players: string;
  identity_fragmentation: boolean;
  team_assignment_uncertainty: boolean;
  goal_geometry_manual: boolean;
  pass_attempts_available: boolean;
  possession_confirmed_seconds?: number;
  possession_unknown_or_unassigned_seconds?: number;
  possession_state_frames?: Record<string, number>;
}

export interface TimelineEvent {
  type: "SHOT" | "PASS" | "RECOVERY" | "INTERCEPTION" | "GOAL";
  time_s?: number | null;
  team_id?: string | null;
  stable_id?: number | null;
}

export interface MatchStats {
  match: MatchInfo;
  generated_at?: string;
  pipeline_version?: string;
  identity_quality: string;
  data_quality: DataQuality;
  event_summary: EventSummary;
  teams: {
    team_a: TeamStats;
    team_b: TeamStats;
  };
  players: PlayerStats[];
  known_limitations?: string[];
  inconsistencies?: string[];
  events?: TimelineEvent[];
}
