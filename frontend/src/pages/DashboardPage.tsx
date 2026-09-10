import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { getMatchStats } from "../api/getMatchStats";
import { DataQuality } from "../components/DataQuality";
import { DataQualityBanner } from "../components/DataQualityBanner";
import { EventSummary } from "../components/EventSummary";
import { EventTimeline } from "../components/EventTimeline";
import { MatchHeader } from "../components/MatchHeader";
import { PlayerTable } from "../components/PlayerTable";
import { ProductNav } from "../components/ProductNav";
import { Scoreboard } from "../components/Scoreboard";
import { TeamComparison } from "../components/TeamComparison";
import { TeamNamesContext } from "../lib/teamNames";
import type { MatchStats } from "../types/matchStats";

export function DashboardPage() {
  const { matchId } = useParams();
  const [stats, setStats] = useState<MatchStats | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!matchId) return;
    getMatchStats(matchId).then(setStats).catch((err: unknown) => {
      setError(err instanceof Error ? err.message : "Failed to load match stats");
    });
  }, [matchId]);

  if (error) {
    return (
      <div className="app">
        <ProductNav />
        <div className="status error">{error}</div>
        <p className="status">
          <Link to="/matches">Back to matches</Link>
        </p>
      </div>
    );
  }
  if (!stats) {
    return <div className="status">Loading match stats…</div>;
  }

  const names = {
    team_a: stats.match.team_a_name || "Team A",
    team_b: stats.match.team_b_name || "Team B",
  };

  return (
    <TeamNamesContext.Provider value={names}>
      <div className="app">
        <ProductNav />
        <MatchHeader stats={stats} />
        <div className="section">
          <DataQualityBanner message="Player identities are currently tracking-based and may be fragmented. Player statistics are MVP estimates." />
        </div>
        <div className="section">
          <Scoreboard stats={stats} />
        </div>
        <TeamComparison teamA={stats.teams.team_a} teamB={stats.teams.team_b} />
        <PlayerTable players={stats.players} />
        <EventSummary summary={stats.event_summary} />
        <EventTimeline events={stats.events} />
        <DataQuality stats={stats} />
      </div>
    </TeamNamesContext.Provider>
  );
}
