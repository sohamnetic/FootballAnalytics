import { Dialog } from "radix-ui";
import { Check, Pencil, Shield, X } from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";
import { toast } from "sonner";
import { cn } from "../../lib/cn";
import { formatClock, playerLabel } from "../../lib/format";
import { usePlayerNames } from "../../lib/playerNames";
import { teamLabel, useTeamNames } from "../../lib/teamNames";
import type { PlayerStats } from "../../types/matchStats";
import { Button } from "../ui/Button";
import { RatingBadge } from "./RatingBadge";

export function PlayerPanel({ player, onClose }: { player: PlayerStats | null; onClose: () => void }) {
  return (
    <Dialog.Root open={player !== null} onOpenChange={(open) => !open && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm" />
        {/* a bottom sheet on phones, a centred dialog from md up */}
        <Dialog.Content className="glass fixed inset-x-0 bottom-0 z-50 max-h-[88dvh] overflow-y-auto rounded-t-3xl bg-ink-900/95 px-5 pt-3 pb-[calc(1.5rem+env(safe-area-inset-bottom))] md:inset-x-auto md:top-1/2 md:bottom-auto md:left-1/2 md:max-h-[calc(100vh-2rem)] md:w-[calc(100vw-2rem)] md:max-w-lg md:-translate-x-1/2 md:-translate-y-1/2 md:rounded-2xl md:p-6">
          <div className="mx-auto mb-4 h-1 w-10 rounded-full bg-white/15 md:hidden" />
          {player ? <PlayerDetails player={player} /> : null}
          <Dialog.Close asChild>
            <Button variant="ghost" size="icon" aria-label="Close" className="absolute top-5 right-4 md:top-4">
              <X />
            </Button>
          </Dialog.Close>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

function PlayerDetails({ player: p }: { player: PlayerStats }) {
  const teams = useTeamNames();
  const { names } = usePlayerNames();
  const low = p.rating_confidence === "low";
  // lines that didn't move the rating (e.g. 0.4 s on the ball) are just noise
  const breakdown = (p.rating_breakdown ?? []).filter((b) => Math.abs(b.points) >= 0.01);
  const biggest = Math.max(...breakdown.map((b) => Math.abs(b.points)), 0.01);

  const facts: [string, string | number | null | undefined][] = [
    ["Seen for", formatClock(p.visible_seconds)],
    ["On the ball", `${p.ball_possession_time_seconds.toFixed(1)}s`],
    ["Passes", p.successful_passes],
    ["Passes received", p.passes_received],
    ["Interceptions", p.interceptions],
    ["Recoveries", p.ball_recoveries],
    ["Ball lost", p.ball_losses],
    ["Shots", p.shots],
    ...(p.is_goalkeeper ? ([["Saves", p.saves]] as [string, number | undefined][]) : []),
  ];

  return (
    <div>
      <div className="flex items-center gap-4 pr-10">
        <RatingBadge rating={p.rating} low={low} size="lg" />
        <div className="min-w-0">
          <Dialog.Title className="truncate text-xl font-semibold tracking-tight text-white">
            {playerLabel(p.stable_id, names)}
          </Dialog.Title>
          <Dialog.Description className="mt-0.5 flex flex-wrap items-center gap-x-2 text-[13px] text-zinc-400">
            <span>{teamLabel(p.team_id, teams)}</span>
            <span className="text-zinc-600">·</span>
            <span className="font-mono">ID {p.stable_id}</span>
            {p.is_goalkeeper ? (
              <span className="inline-flex items-center gap-1 rounded-md bg-white/[0.06] px-1.5 py-0.5 text-[11px] text-zinc-300">
                <Shield className="size-3" /> Goalkeeper
              </span>
            ) : null}
          </Dialog.Description>
        </div>
      </div>

      <NameEditor stableId={p.stable_id} />

      {p.rating === undefined ? (
        <p className="mt-6 text-sm text-zinc-400">
          This match was analysed before ratings existed. Analyse it again to see this player's rating.
        </p>
      ) : (
        <div className="mt-6">
          <h3 className="text-[13px] font-medium text-zinc-300">Why this rating</h3>
          <p className="mt-0.5 text-[12px] text-zinc-500">
            Everyone starts at 6.0. Goals, shots and saves count the same however long the match is; other actions
            count more the less time we saw the player.
          </p>
          {low ? (
            <p className="mt-3 rounded-lg bg-amber-300/10 px-3 py-2 text-[12px] text-amber-200">
              We only saw this player for {formatClock(p.visible_seconds)}, so this rating is rough.
            </p>
          ) : null}
          {breakdown.length ? (
            <ul className="mt-3 space-y-2">
              {breakdown.map((b) => (
                <li key={b.key} className="grid grid-cols-[1fr_auto] items-center gap-x-3 gap-y-1 text-[13px]">
                  <span className="text-zinc-300">
                    {b.label} <span className="font-mono text-zinc-500">×{b.key === "on_ball" ? `${b.count}s` : b.count}</span>
                  </span>
                  <span className={cn("font-mono tabular", b.points >= 0 ? "text-emerald-300" : "text-rose-300")}>
                    {b.points >= 0 ? "+" : ""}
                    {b.points.toFixed(2)}
                  </span>
                  <div className="col-span-2 h-1.5 overflow-hidden rounded-full bg-white/[0.05]">
                    <div
                      className={cn("h-full rounded-full", b.points >= 0 ? "bg-emerald-400/80" : "bg-rose-400/80")}
                      style={{ width: `${(Math.abs(b.points) / biggest) * 100}%` }}
                    />
                  </div>
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-3 text-[13px] text-zinc-500">No actions detected for this player, so the rating stays at 6.0.</p>
          )}
        </div>
      )}

      <dl className="mt-6 grid grid-cols-3 gap-2">
        {facts.map(([label, value]) => (
          <div key={label} className="rounded-xl bg-white/[0.03] p-2.5">
            <dt className="text-[11px] text-zinc-500">{label}</dt>
            <dd className="mt-0.5 font-mono text-sm text-white tabular">{value ?? "–"}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

function NameEditor({ stableId }: { stableId: number }) {
  const { names, save } = usePlayerNames();
  const current = names[String(stableId)] ?? "";
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(current);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setValue(current);
    setEditing(false);
  }, [stableId, current]);

  if (!save) return null;

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!save) return;
    setBusy(true);
    try {
      await save(stableId, value.trim());
      setEditing(false);
      toast.success(value.trim() ? "Name saved" : "Name removed");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Could not save the name");
    } finally {
      setBusy(false);
    }
  }

  if (!editing) {
    return (
      <button
        type="button"
        onClick={() => setEditing(true)}
        className="mt-3 inline-flex cursor-pointer items-center gap-1.5 text-[13px] text-pitch-300 hover:text-pitch-200"
      >
        <Pencil className="size-3.5" /> {current ? "Rename player" : "Add a name"}
      </button>
    );
  }

  return (
    <form onSubmit={submit} className="mt-3 flex gap-2">
      <input
        autoFocus
        value={value}
        maxLength={40}
        onChange={(e) => setValue(e.target.value)}
        placeholder="Player name"
        aria-label="Player name"
        className="h-9 min-w-0 flex-1 rounded-lg border border-white/[0.08] bg-ink-900/70 px-3 text-base text-white outline-none md:text-sm placeholder:text-zinc-500 focus:border-pitch-400/60"
      />
      <Button type="submit" size="sm" loading={busy} className="h-9">
        <Check /> Save
      </Button>
      <Button type="button" size="sm" variant="ghost" className="h-9" onClick={() => setEditing(false)}>
        Cancel
      </Button>
    </form>
  );
}
