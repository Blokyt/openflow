import { ReactNode } from "react";

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
  if (!open) return null;
  return (
    <div
      className="fixed inset-0 bg-black/60 flex items-center justify-center z-[60] p-4"
      onClick={onCancel}
    >
      <div
        className="w-full max-w-sm bg-[#111] border border-[#222] rounded-2xl p-6 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <h3 className="text-base font-semibold text-white mb-2">{title}</h3>
        {message && <div className="text-sm text-[#B0B0B0] mb-5">{message}</div>}
        <div className="flex justify-end gap-3">
          <button
            type="button"
            onClick={onCancel}
            className="px-4 py-2 text-sm font-semibold text-white border border-[#333] rounded-full hover:border-[#444] hover:bg-[#1a1a1a] transition-colors"
          >
            {cancelLabel}
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={busy}
            className={`px-4 py-2 text-sm font-semibold rounded-full disabled:opacity-50 transition-colors ${
              danger
                ? "text-white bg-[#FF5252] hover:bg-[#e04848]"
                : "text-black bg-[#F2C48D] hover:bg-[#e8b87a]"
            }`}
          >
            {busy ? "..." : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
