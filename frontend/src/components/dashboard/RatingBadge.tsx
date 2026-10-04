import { cn } from "../../lib/cn";

// same bands as SofaScore: 8+ great, 7-8 good, 6-7 average, below 6 poor
export function ratingTone(rating: number) {
  if (rating >= 8) return "bg-emerald-400 text-ink-950";
  if (rating >= 7) return "bg-lime-300 text-ink-950";
  if (rating >= 6) return "bg-amber-300 text-ink-950";
  return "bg-rose-400 text-ink-950";
}

export function RatingBadge({
  rating,
  low = false,
  size = "sm",
  className,
}: {
  rating?: number | null;
  low?: boolean;
  size?: "sm" | "lg";
  className?: string;
}) {
  const big = size === "lg";
  if (rating === null || rating === undefined) {
    return (
      <span
        className={cn(
          "inline-grid place-items-center rounded-md bg-white/[0.06] font-mono font-semibold text-zinc-500 tabular",
          big ? "h-12 w-16 text-xl" : "h-6 w-10 text-[12px]",
          className,
        )}
      >
        –
      </span>
    );
  }
  return (
    <span
      title={low ? "Seen for less than 2 minutes, so this rating is rough" : undefined}
      className={cn(
        "inline-grid place-items-center rounded-md font-mono font-semibold tabular",
        big ? "h-12 w-16 text-xl" : "h-6 w-10 text-[12px]",
        ratingTone(rating),
        low && "opacity-45",
        className,
      )}
    >
      {rating.toFixed(1)}
    </span>
  );
}
