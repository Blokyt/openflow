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
    <div className="bg-bg-card border border-border rounded-2xl py-12 px-8 text-center">
      <div className="inline-flex items-center justify-center w-14 h-14 bg-accent-sand/10 rounded-2xl mb-4">
        <Icon size={26} className="text-accent-sand" strokeWidth={1.5} />
      </div>
      <h3 className="text-lg font-bold text-white mb-2">{title}</h3>
      <p className="text-sm text-text-secondary mb-4 max-w-md mx-auto leading-relaxed">{description}</p>
      {examples && examples.length > 0 && (
        <ul className="text-xs text-[#8a8a8a] mb-6 space-y-1 inline-block text-left">
          {examples.map((ex, i) => (
            <li key={i} className="before:content-['•'] before:text-accent-sand before:mr-2">{ex}</li>
          ))}
        </ul>
      )}
      {ctaLabel && onCta && (
        <div>
          <button
            onClick={onCta}
            className="px-5 py-2.5 text-sm font-semibold text-black bg-accent-sand rounded-full hover:bg-accent-sand transition-colors"
          >
            {ctaLabel}
          </button>
        </div>
      )}
    </div>
  );
}
