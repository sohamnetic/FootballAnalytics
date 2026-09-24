import { BrandMark } from "./BrandMark";

export function SiteFooter() {
  return (
    <footer className="mt-24 border-t border-white/[0.06]">
      <div className="mx-auto flex max-w-7xl flex-col items-center justify-between gap-4 px-4 py-8 text-[13px] text-zinc-500 sm:flex-row sm:px-6 lg:px-8">
        <BrandMark />
        <p>See the match behind the footage.</p>
        <p>&copy; {new Date().getFullYear()} TactiVision</p>
      </div>
    </footer>
  );
}
