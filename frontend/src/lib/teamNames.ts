import { createContext, useContext } from "react";

export const TeamNamesContext = createContext({ team_a: "Team A", team_b: "Team B" });

export function useTeamNames() {
  return useContext(TeamNamesContext);
}

export function teamLabel(teamId: string, names?: { team_a?: string; team_b?: string }): string {
  const n = names ?? { team_a: "Team A", team_b: "Team B" };
  if (teamId === "team_a") return n.team_a || "Team A";
  if (teamId === "team_b") return n.team_b || "Team B";
  return teamId;
}
