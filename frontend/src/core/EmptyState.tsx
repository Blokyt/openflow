import { LucideIcon } from "lucide-react";

interface EmptyStateProps {
  icon: LucideIcon;
  title: string;
  description: string;
  examples?: string[];
  ctaLabel?: string;
  onCta?: () => void;
}

export default function EmptyState({
  icon: Icon, title, description, examples, ctaLabel, onCta,
}: EmptyStateProps) {
  return (
    <div className="bg-[#111] border border-[#222] rounded-2xl py-12 px-8 text-center">
      <div className="inline-flex items-center justify-center w-14 h-14 bg-[#F2C48D]/10 rounded-2xl mb-4">
        <Icon size={26} className="text-[#F2C48D]" strokeWidth={1.5} />
      </div>
      <h3 className="text-lg font-bold text-white mb-2">{title}</h3>
      <p className="text-sm text-[#B0B0B0] mb-4 max-w-md mx-auto leading-relaxed">{description}</p>
      {examples && examples.length > 0 && (
        <ul className="text-xs text-[#666] mb-6 space-y-1 inline-block text-left">
          {examples.map((ex, i) => (
            <li key={i} className="before:content-['•'] before:text-[#F2C48D] before:mr-2">{ex}</li>
          ))}
        </ul>
      )}
      {ctaLabel && onCta && (
        <div>
          <button
            onClick={onCta}
            className="px-5 py-2.5 text-sm font-semibold text-black bg-[#F2C48D] rounded-full hover:bg-[#e8b87a] transition-colors"
          >
            {ctaLabel}
          </button>
        </div>
      )}
    </div>
  );
}
