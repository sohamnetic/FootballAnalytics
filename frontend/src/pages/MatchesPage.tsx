import { DropdownMenu } from "radix-ui";
import { ArrowUpRight, Clock, MoreHorizontal, Plus, Search, Settings2, Trash2, Trophy } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { deleteMatch, listMatches, type MatchRecord } from "../api/getMatchStats";
import { PageHeading, PageShell } from "../components/layout/PageShell";
import { Alert } from "../components/ui/Alert";
import { Badge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { ConfirmDialog } from "../components/ui/ConfirmDialog";

const rtf = new Intl.RelativeTimeFormat(undefined, { numeric: "auto" });

function relativeTime(iso?: string) {
  if (!iso) return "";
  const diff = (new Date(iso).getTime() - Date.now()) / 1000;
  const units: [Intl.RelativeTimeFormatUnit, number][] = [
    ["year", 31536000],
    ["month", 2592000],
    ["week", 604800],
    ["day", 86400],
    ["hour", 3600],
    ["minute", 60],
  ];
  for (const [unit, secs] of units) {
    if (Math.abs(diff) >= secs) return rtf.format(Math.round(diff / secs), unit);
  }
  return "just now";
}

function StatusBadge({ status }: { status?: string }) {
  if (status === "completed") return <Badge tone="pitch" dot>Analyzed</Badge>;
  if (status === "processing") return <Badge tone="gold" dot pulse>Analyzing</Badge>;
  if (status === "queued") return <Badge tone="gold" dot pulse>Queued</Badge>;
  if (status === "failed") return <Badge tone="danger" dot>Failed</Badge>;
  return <Badge tone="neutral" dot>Needs setup</Badge>;
}

export function MatchesPage() {
  const [rows, setRows] = useState<MatchRecord[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [pending, setPending] = useState<MatchRecord | null>(null);
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    listMatches()
      .then((data) => setRows(data.matches || []))
      .catch((err: unknown) => {
        setRows([]);
        setError(err instanceof Error ? err.message : "Failed to load matches");
      });
  }, []);

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    const sorted = [...(rows ?? [])].sort(
      (a, b) => new Date(b.completed_at || b.created_at || 0).getTime() - new Date(a.completed_at || a.created_at || 0).getTime(),
    );
    if (!q) return sorted;
    return sorted.filter((r) => [r.team_a, r.team_b, r.filename].some((v) => v?.toLowerCase().includes(q)));
  }, [rows, query]);

  async function confirmDelete() {
    if (!pending) return;
    setDeleting(true);
    try {
      await deleteMatch(pending.match_id);
      setRows((current) => (current ?? []).filter((r) => r.match_id !== pending.match_id));
      toast.success("Match deleted");
      setPending(null);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Could not delete match");
    } finally {
      setDeleting(false);
    }
  }

  return (
    <PageShell>
      <PageHeading
        eyebrow="Your library"
        title="Matches"
        description={rows && rows.length ? `${rows.length} match${rows.length === 1 ? "" : "es"} uploaded` : undefined}
        actions={
          <Button asChild>
            <Link to="/upload">
              <Plus /> New analysis
            </Link>
          </Button>
        }
      />

      {error ? <Alert tone="error" className="mb-6">{error}</Alert> : null}

      {rows && rows.length > 0 ? (
        <div className="relative mb-6 max-w-sm">
          <Search className="pointer-events-none absolute top-1/2 left-3.5 size-4 -translate-y-1/2 text-zinc-500" />
          <input
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search teams or files"
            aria-label="Search matches"
            className="h-10 w-full rounded-xl border border-white/[0.08] bg-white/[0.03] pr-3 pl-10 text-sm text-white outline-none placeholder:text-zinc-500 focus:border-pitch-400/50 focus:ring-4 focus:ring-pitch-400/10"
          />
        </div>
      ) : null}

      {rows === null ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 3 }, (_, i) => (
            <div key={i} className="glass space-y-4 rounded-2xl p-5">
              <div className="skeleton h-5 w-24" />
              <div className="skeleton h-8 w-3/4" />
              <div className="skeleton h-4 w-1/2" />
            </div>
          ))}
        </div>
      ) : rows.length === 0 && !error ? (
        <EmptyState />
      ) : visible.length === 0 ? (
        <p className="py-12 text-center text-sm text-zinc-500">No matches match “{query}”.</p>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <AnimatePresence initial={false}>
            {visible.map((row, i) => (
              <motion.div
                key={row.match_id}
                layout
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0, transition: { delay: Math.min(i * 0.04, 0.3) } }}
                exit={{ opacity: 0, scale: 0.96 }}
              >
                <MatchCard row={row} onDelete={() => setPending(row)} />
              </motion.div>
            ))}
          </AnimatePresence>
        </div>
      )}

      <ConfirmDialog
        open={pending !== null}
        onOpenChange={(open) => !open && setPending(null)}
        title="Delete this match?"
        description={
          <>
            {pending?.team_a || "Team A"} vs {pending?.team_b || "Team B"} and all of its analysis will be removed. This
            can't be undone.
          </>
        }
        confirmLabel="Delete match"
        onConfirm={confirmDelete}
        busy={deleting}
      />
    </PageShell>
  );
}

function MatchCard({ row, onDelete }: { row: MatchRecord; onDelete: () => void }) {
  const status = row.status;
  const busy = status === "processing" || status === "queued";
  const target =
    status === "completed" ? `/matches/${row.match_id}` : busy ? `/matches/${row.match_id}/processing` : `/matches/${row.match_id}/setup`;
  const when = row.completed_at || row.created_at;

  return (
    <article className="glass group relative flex h-full flex-col rounded-2xl p-5 transition-all duration-300 hover:-translate-y-0.5 hover:border-white/15 hover:bg-white/[0.05]">
      <div className="flex items-center justify-between">
        <StatusBadge status={status} />
        <DropdownMenu.Root>
          <DropdownMenu.Trigger asChild>
            <Button variant="ghost" size="icon" aria-label="Match actions" className="relative z-10 -mr-2 size-8">
              <MoreHorizontal />
            </Button>
          </DropdownMenu.Trigger>
          <DropdownMenu.Portal>
            <DropdownMenu.Content align="end" sideOffset={6} className="glass z-50 min-w-44 rounded-xl bg-ink-900/95 p-1.5 text-sm">
              {status !== "completed" && !busy ? (
                <DropdownMenu.Item asChild>
                  <Link
                    to={`/matches/${row.match_id}/setup`}
                    className="flex items-center gap-2 rounded-lg px-2.5 py-2 text-zinc-300 outline-none data-[highlighted]:bg-white/[0.07] [&_svg]:size-4"
                  >
                    <Settings2 /> Set up analysis
                  </Link>
                </DropdownMenu.Item>
              ) : null}
              <DropdownMenu.Item
                disabled={busy}
                onSelect={onDelete}
                className="flex cursor-pointer items-center gap-2 rounded-lg px-2.5 py-2 text-rose-300 outline-none data-[disabled]:cursor-not-allowed data-[disabled]:opacity-40 data-[highlighted]:bg-rose-500/10 [&_svg]:size-4"
              >
                <Trash2 /> {busy ? "Can't delete while analyzing" : "Delete"}
              </DropdownMenu.Item>
            </DropdownMenu.Content>
          </DropdownMenu.Portal>
        </DropdownMenu.Root>
      </div>

      <Link to={target} className="mt-5 block flex-1 after:absolute after:inset-0 after:rounded-2xl">
        <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-3">
          <p className="truncate font-semibold text-white">{row.team_a || "Team A"}</p>
          <p className="font-mono text-2xl font-semibold text-white tabular">
            {row.goals_a ?? "–"}
            <span className="mx-1.5 text-zinc-600">:</span>
            {row.goals_b ?? "–"}
          </p>
          <p className="truncate text-right font-semibold text-white">{row.team_b || "Team B"}</p>
        </div>
        <div className="mt-2 grid grid-cols-2 gap-3">
          <span className="h-0.5 rounded-full bg-team-a/60" />
          <span className="h-0.5 rounded-full bg-team-b/60" />
        </div>
      </Link>

      <div className="mt-5 flex items-center justify-between border-t border-white/[0.06] pt-4 text-[12px] text-zinc-500">
        <span className="flex min-w-0 items-center gap-1.5">
          <Clock className="size-3.5 shrink-0" />
          <span className="truncate">{relativeTime(when)}</span>
        </span>
        <span className="flex items-center gap-1 text-zinc-400 transition-colors group-hover:text-pitch-300">
          {status === "completed" ? "Open dashboard" : busy ? "View progress" : status === "failed" ? "Retry" : "Continue setup"}
          <ArrowUpRight className="size-3.5" />
        </span>
      </div>
    </article>
  );
}

function EmptyState() {
  return (
    <div className="glass mx-auto max-w-lg rounded-3xl px-8 py-14 text-center">
      <div className="mx-auto grid size-16 place-items-center rounded-2xl bg-gold-400/10 text-gold-300 ring-1 ring-gold-400/25 [&_svg]:size-7">
        <Trophy />
      </div>
      <h2 className="mt-6 text-xl font-semibold text-white">No matches yet</h2>
      <p className="mt-2 text-sm leading-relaxed text-zinc-400">
        Upload your first recording and TactiVision will build a full match dashboard from it.
      </p>
      <Button asChild className="mt-8">
        <Link to="/upload">
          <Plus /> Analyze your first match
        </Link>
      </Button>
    </div>
  );
}
