import { createContext, useContext, useState, ReactNode } from "react";
import { Check, X } from "lucide-react";

type ToastType = "success" | "error";

interface Toast {
  id: number;
  message: string;
  type: ToastType;
}

interface ToastContextValue {
  showToast: (message: string, type: ToastType) => void;
  success: (message: string) => void;
  error: (message: string) => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

let nextId = 0;

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const showToast = (message: string, type: ToastType) => {
    const id = nextId++;
    setToasts((prev) => [...prev, { id, message, type }]);
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, 4000);
  };

  const success = (message: string) => showToast(message, "success");
  const error = (message: string) => showToast(message, "error");

  return (
    <ToastContext.Provider value={{ showToast, success, error }}>
      {children}
      <div className="fixed bottom-6 right-6 z-50 flex flex-col gap-2 pointer-events-none">
        {toasts.map((t) => (
          <div
            key={t.id}
            className="pointer-events-auto flex items-center gap-3 px-4 py-3 rounded-xl shadow-lg border text-sm font-medium animate-in slide-in-from-bottom-5 fade-in duration-300"
            style={{
              backgroundColor: "#111",
              borderColor: t.type === "success" ? "rgba(0,200,83,0.3)" : "rgba(255,82,82,0.3)",
              color: "#fff",
            }}
          >
            {t.type === "success" ? (
              <Check size={16} className="text-success" />
            ) : (
              <X size={16} className="text-alert" />
            )}
            {t.message}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be used within ToastProvider");
  return ctx;
}
