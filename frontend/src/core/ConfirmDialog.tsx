import { ReactNode, useEffect } from "react";

interface ConfirmDialogProps {
  open: boolean;
  title: string;
  message?: ReactNode;
  confirmLabel?: string;
  cancelLabel?: string;
  danger?: boolean;
  busy?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

/** Boîte de confirmation cohérente avec le thème sombre (remplace window.confirm). */
export default function ConfirmDialog({
  open,
  title,
  message,
  confirmLabel = "Confirmer",
  cancelLabel = "Annuler",
  danger = false,
  busy = false,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onCancel();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onCancel]);

  if (!open) return null;
  return (
    <div
      className="fixed inset-0 bg-black/60 flex items-center justify-center z-[60] p-4"
      onClick={onCancel}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="confirm-dialog-title"
        className="w-full max-w-sm bg-bg-card border border-border rounded-2xl p-6 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <h3 id="confirm-dialog-title" className="text-base font-semibold text-white mb-2">{title}</h3>
        {message && <div className="text-sm text-text-secondary mb-5">{message}</div>}
        <div className="flex justify-end gap-3">
          <button
            type="button"
            autoFocus
            onClick={onCancel}
            className="px-4 py-2 text-sm font-semibold text-white border border-border-hover rounded-full hover:border-[#444] hover:bg-[#1a1a1a] transition-colors"
          >
            {cancelLabel}
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={busy}
            className={`px-4 py-2 text-sm font-semibold rounded-full disabled:opacity-50 transition-colors ${
              danger
                ? "text-white bg-alert hover:bg-[#e04848]"
                : "text-black bg-accent-sand hover:bg-accent-sand"
            }`}
          >
            {busy ? "..." : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
