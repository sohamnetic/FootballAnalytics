import { ArrowRight, Film, Lightbulb, UploadCloud, X } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { useEffect, useMemo, useRef, useState, type DragEvent } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { uploadMatchVideo } from "../api/getMatchStats";
import { FlowSteps } from "../components/layout/FlowSteps";
import { PageHeading, PageShell } from "../components/layout/PageShell";
import { Alert } from "../components/ui/Alert";
import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";
import { cn } from "../lib/cn";

const ACCEPT = ".mp4,.mov,.avi,.mkv,video/mp4,video/quicktime,video/x-msvideo,video/x-matroska";
const EXTENSIONS = [".mp4", ".mov", ".avi", ".mkv"];

function formatBytes(bytes: number) {
  if (bytes >= 1024 ** 3) return `${(bytes / 1024 ** 3).toFixed(2)} GB`;
  return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
}

function formatDuration(seconds: number) {
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  return `${m}:${String(s).padStart(2, "0")}`;
}

export function UploadPage() {
  const navigate = useNavigate();
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [duration, setDuration] = useState<number | null>(null);
  const [dragging, setDragging] = useState(false);
  const [progress, setProgress] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const preview = useMemo(() => (file ? URL.createObjectURL(file) : null), [file]);
  useEffect(() => () => {
    if (preview) URL.revokeObjectURL(preview);
  }, [preview]);

  function choose(next: File | null | undefined) {
    setError(null);
    setDuration(null);
    if (!next) return;
    const ok = EXTENSIONS.some((ext) => next.name.toLowerCase().endsWith(ext));
    if (!ok) {
      setError("That file type isn't supported. Use MP4, MOV, AVI or MKV.");
      return;
    }
    setFile(next);
  }

  function onDrop(e: DragEvent) {
    e.preventDefault();
    setDragging(false);
    choose(e.dataTransfer.files?.[0]);
  }

  async function onSubmit() {
    if (!file) return;
    setError(null);
    setProgress(0);
    try {
      const result = await uploadMatchVideo(file, setProgress);
      toast.success("Upload complete", { description: "Now tell us who's playing." });
      navigate(`/matches/${result.match_id}/setup`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
      setProgress(null);
    }
  }

  const uploading = progress !== null;

  return (
    <PageShell className="max-w-3xl">
      <FlowSteps current={0} />
      <PageHeading
        eyebrow="New analysis"
        title="Upload match footage"
        description="Drop in a recording of the game. You'll name the teams on the next step."
      />

      <AnimatePresence mode="wait" initial={false}>
        {!file ? (
          <motion.div key="drop" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
            <button
              type="button"
              onClick={() => inputRef.current?.click()}
              onDragOver={(e) => {
                e.preventDefault();
                setDragging(true);
              }}
              onDragLeave={() => setDragging(false)}
              onDrop={onDrop}
              className={cn(
                "group relative flex w-full cursor-pointer flex-col items-center justify-center overflow-hidden rounded-3xl border-2 border-dashed px-6 py-20 text-center transition-all duration-300",
                dragging
                  ? "scale-[1.01] border-pitch-400 bg-pitch-400/[0.07]"
                  : "border-white/10 bg-white/[0.02] hover:border-pitch-400/40 hover:bg-white/[0.04]",
              )}
            >
              <div aria-hidden="true" className="absolute top-0 left-1/2 size-64 -translate-x-1/2 -translate-y-1/2 rounded-full bg-pitch-400/10 blur-3xl" />
              <motion.div
                animate={dragging ? { y: -6, scale: 1.08 } : { y: 0, scale: 1 }}
                className="relative grid size-16 place-items-center rounded-2xl bg-pitch-400/10 text-pitch-300 ring-1 ring-pitch-400/25 [&_svg]:size-7"
              >
                <UploadCloud />
              </motion.div>
              <p className="relative mt-6 text-lg font-semibold text-white">
                {dragging ? "Drop it here" : "Drag your match video here"}
              </p>
              <p className="relative mt-1.5 text-sm text-zinc-400">
                or <span className="font-medium text-pitch-300 group-hover:text-pitch-200">browse your files</span>
              </p>
              <p className="relative mt-5 text-[12px] text-zinc-500">MP4, MOV, AVI or MKV · up to 8 GB</p>
            </button>
          </motion.div>
        ) : (
          <motion.div key="file" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>
            <Card className="overflow-hidden">
              {preview ? (
                <video
                  src={preview}
                  controls
                  muted
                  playsInline
                  onLoadedMetadata={(e) => setDuration(e.currentTarget.duration)}
                  className="aspect-video w-full bg-black"
                />
              ) : null}
              <div className="flex items-center gap-4 p-5">
                <div className="grid size-11 shrink-0 place-items-center rounded-xl bg-white/[0.05] text-zinc-300 [&_svg]:size-5">
                  <Film />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="truncate font-medium text-white">{file.name}</p>
                  <p className="mt-0.5 font-mono text-[12px] text-zinc-400 tabular">
                    {formatBytes(file.size)}
                    {duration && Number.isFinite(duration) ? ` · ${formatDuration(duration)}` : ""}
                  </p>
                </div>
                {!uploading ? (
                  <Button variant="ghost" size="icon" aria-label="Remove file" onClick={() => setFile(null)}>
                    <X />
                  </Button>
                ) : null}
              </div>
              {uploading ? (
                <div className="px-5 pb-5">
                  <div className="flex justify-between text-[12px] text-zinc-400">
                    <span>{progress < 1 ? "Uploading…" : "Finishing up…"}</span>
                    <span className="font-mono tabular">{Math.round(progress * 100)}%</span>
                  </div>
                  <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-white/[0.06]">
                    <motion.div
                      className="h-full rounded-full bg-linear-to-r from-pitch-500 to-pitch-300"
                      animate={{ width: `${Math.max(progress * 100, 2)}%` }}
                      transition={{ ease: "easeOut" }}
                    />
                  </div>
                </div>
              ) : null}
            </Card>
          </motion.div>
        )}
      </AnimatePresence>

      <input
        ref={inputRef}
        type="file"
        accept={ACCEPT}
        className="sr-only"
        tabIndex={-1}
        onChange={(e) => {
          choose(e.target.files?.[0]);
          e.target.value = "";
        }}
      />

      {error ? <Alert tone="error" className="mt-4">{error}</Alert> : null}

      <div className="mt-6 flex justify-end">
        <Button size="lg" disabled={!file} loading={uploading} onClick={onSubmit}>
          {uploading ? "Uploading" : "Continue"} {uploading ? null : <ArrowRight />}
        </Button>
      </div>

      <div className="mt-10 flex gap-3 rounded-2xl border border-white/[0.06] bg-white/[0.02] p-5 text-sm text-zinc-400">
        <Lightbulb className="mt-0.5 size-4 shrink-0 text-gold-400" />
        <p>
          <span className="font-medium text-zinc-200">For the best results:</span> use the highest resolution you have
          (it helps read jersey numbers) and keep as much of the pitch in view as possible.
        </p>
      </div>
    </PageShell>
  );
}
