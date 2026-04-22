import { useEffect, useState } from "react";

const eurFormatter = new Intl.NumberFormat("fr-FR", { style: "currency", currency: "EUR" });

interface BudgetStatus {
  id: number;
  label: string;
  category_id: number | null;
  period_start: string;
  period_end: string;
  budgeted: number;
  spent: number;
  remaining: number;
}

export default function BudgetProgress() {
  const [items, setItems] = useState<BudgetStatus[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch("/api/budget/status")
      .then((r) => {
        if (!r.ok) throw new Error(r.statusText);
        return r.json();
      })
      .then(setItems)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-8">
        <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-[#F2C48D]" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-4 text-sm text-[#FF5252] bg-[#1a0a0a] border border-[#FF5252]/30 rounded-lg">{error}</div>
    );
  }

  if (items.length === 0) {
    return (
      <div className="p-4 text-sm text-[#888] text-center">
        Aucune enveloppe budgétaire.
      </div>
    );
  }

  return (
    <div className="p-4 space-y-4">
      <h3 className="text-sm font-semibold text-white">Suivi budgétaire</h3>
      {items.map((item) => {
        const spentAbs = Math.abs(item.spent);
        const pct = item.budgeted > 0 ? Math.min(100, (spentAbs / item.budgeted) * 100) : 0;
        const isOver = spentAbs > item.budgeted;
        return (
          <div key={item.id}>
            <div className="flex justify-between text-xs text-[#666] mb-1">
              <span className="font-medium text-[#B0B0B0] truncate max-w-[60%]">
                {item.label || `Budget #${item.id}`}
              </span>
              <span className="text-[#B0B0B0]">
                {eurFormatter.format(spentAbs)} / {eurFormatter.format(item.budgeted)}
              </span>
            </div>
            <div className="h-2 bg-[#1a1a1a] rounded-full overflow-hidden">
              <div
                className="h-full rounded-full transition-all"
                style={{ width: `${pct}%`, backgroundColor: isOver ? "#FF5252" : "#F2C48D" }}
              />
            </div>
            {isOver ? (
              <p className="text-xs text-[#FF5252] mt-1">
                Dépassement : +{eurFormatter.format(spentAbs - item.budgeted)}
              </p>
            ) : (
              <p className="text-xs mt-0.5 text-right text-[#888]">
                Restant : {eurFormatter.format(item.remaining)}
              </p>
            )}
          </div>
        );
      })}
    </div>
  );
}
