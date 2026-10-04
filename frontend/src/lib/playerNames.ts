import { createContext, useContext } from "react";

export type PlayerNames = Record<string, string>;

export const PlayerNamesContext = createContext<{
  names: PlayerNames;
  // null when names can't be changed (e.g. demo data)
  save: ((stableId: number, name: string) => Promise<void>) | null;
}>({ names: {}, save: null });

// show names with playerLabel() from lib/format
export function usePlayerNames() {
  return useContext(PlayerNamesContext);
}
