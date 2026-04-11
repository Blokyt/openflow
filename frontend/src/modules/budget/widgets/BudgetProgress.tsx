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
        <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-indigo-600" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-4 text-sm text-red-600 bg-red-50 rounded-lg">{error}</div>
    );
  }

  if (items.length === 0) {
    return (
      <div className="p-4 text-sm text-gray-500 text-center">
        Aucune enveloppe budgetaire.
      </div>
    );
  }

  return (
    <div className="p-4 space-y-4">
      <h3 className="text-sm font-semibold text-gray-700">Suivi budgetaire</h3>
      {items.map((item) => {
        const pct = item.budgeted > 0 ? Math.min(100, (Math.abs(item.spent) / item.budgeted) * 100) : 0;
        const isOver = Math.abs(item.spent) > item.budgeted;
        return (
          <div key={item.id}>
            <div className="flex justify-between text-xs text-gray-600 mb-1">
              <span className="font-medium truncate max-w-[60%]">
                {item.label || `Budget #${item.id}`}
              </span>
              <span>
                {eurFormatter.format(Math.abs(item.spent))} / {eurFormatter.format(item.budgeted)}
              </span>
            </div>
            <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
              <div
                className={`h-full rounded-full transition-all ${isOver ? "bg-red-500" : "bg-indigo-500"}`}
                style={{ width: `${pct}%` }}
              />
            </div>
            <p className={`text-xs mt-0.5 text-right ${isOver ? "text-red-500" : "text-gray-400"}`}>
              {isOver
                ? `Depassement de ${eurFormatter.format(Math.abs(item.spent) - item.budgeted)}`
                : `Restant : ${eurFormatter.format(item.remaining)}`}
            </p>
          </div>
        );
      })}
    </div>
  );
}
