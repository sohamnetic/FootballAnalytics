import { Link } from "react-router-dom";
import { cn } from "../../lib/cn";

export function BrandLogo({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" className={cn("size-8", className)} aria-hidden="true">
      <defs>
        <linearGradient id="tv-g" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#7eecc0" />
          <stop offset="1" stopColor="#1cc488" />
        </linearGradient>
      </defs>
      <rect width="32" height="32" rx="9" fill="#0e1713" />
      <rect x="4.5" y="4.5" width="23" height="23" rx="6" fill="none" stroke="url(#tv-g)" strokeWidth="1.6" />
      <line x1="16" y1="5" x2="16" y2="27" stroke="url(#tv-g)" strokeWidth="1.4" opacity="0.7" />
      <circle cx="16" cy="16" r="4.2" fill="none" stroke="#e4c56a" strokeWidth="1.6" />
      <circle cx="16" cy="16" r="1.4" fill="#e4c56a" />
    </svg>
  );
}

export function BrandMark({ className }: { className?: string }) {
  return (
    <Link
      to="/"
      aria-label="TactiVision home"
      className={cn("group inline-flex items-center gap-2.5 rounded-lg", className)}
    >
      <BrandLogo className="transition-transform duration-300 group-hover:rotate-[-8deg]" />
      <span className="text-[17px] font-semibold tracking-tight text-white">
        Tacti<span className="text-pitch-400">Vision</span>
      </span>
    </Link>
  );
}
