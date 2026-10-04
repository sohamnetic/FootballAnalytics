import { ChevronRight, Trophy } from "lucide-react";
import { formatClock, playerLabel } from "../../lib/format";
import { usePlayerNames } from "../../lib/playerNames";
import { teamLabel, useTeamNames } from "../../lib/teamNames";
import type { PlayerStats } from "../../types/matchStats";
import { Button } from "../ui/Button";
import { Card, CardBody, CardHeader } from "../ui/Card";
import { RatingBadge } from "./RatingBadge";

const SINGULAR: Record<string, string> = {
  goal: "goal",
  shot_on_target: "shot on target",
  shot_off_target: "other shot",
  pass: "pass",
  pass_received: "pass received",
  interception: "interception",
  recovery: "recovery",
  save: "save",
};

export function PlayerOfMatch({ player, onSelect }: { player: PlayerStats; onSelect: (p: PlayerStats) => void }) {
  const teams = useTeamNames();
  const { names } = usePlayerNames();
  const top = (player.rating_breakdown ?? []).filter((b) => b.points > 0 && b.key !== "on_ball").slice(0, 3);

  return (
    <Card>
      <CardHeader
        icon={<Trophy />}
        title="Player of the match"
        description="Highest rating among players we saw for at least 2 minutes."
      />
      <CardBody className="flex flex-wrap items-center gap-4">
        <RatingBadge rating={player.rating} size="lg" />
        <div className="min-w-0 flex-1">
          <p className="truncate text-lg font-semibold text-white">{playerLabel(player.stable_id, names)}</p>
          <p className="text-[13px] text-zinc-400">
            {teamLabel(player.team_id, teams)} · seen for {formatClock(player.visible_seconds)}
          </p>
          {top.length ? (
            <p className="mt-1.5 text-[12px] text-zinc-500">
              {top.map((b) => `${b.count} ${b.count === 1 ? (SINGULAR[b.key] ?? b.label.toLowerCase()) : b.label.toLowerCase()}`).join(" · ")}
            </p>
          ) : null}
        </div>
        <Button variant="secondary" size="sm" onClick={() => onSelect(player)}>
          Details <ChevronRight />
        </Button>
      </CardBody>
    </Card>
  );
}
