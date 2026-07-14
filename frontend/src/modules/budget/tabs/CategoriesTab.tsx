import { useEffect, useState } from "react";
import { api } from "../../../api";
import { FiscalYear } from "../../../core/FiscalYearContext";
import { useEntity } from "../../../core/EntityContext";
import { formatEuros, budgetColor } from "../../../utils/format";

interface Props { year: FiscalYear | null }

export default function CategoriesTab({ year }: Props) {
  const { selectedEntityId, selectedEntity } = useEntity();
  const [data, setData] = useState<any | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!year) return;
    let cancelled = false;
    setLoading(true);
    setData(null);
    setError(null);
    // Même périmètre que le reste de l'app : le focus entité limite la vue
    // au sous-arbre (réalisé frontière + allocations du sous-arbre).
    api.getBudgetCategoryView(year.id, selectedEntityId ?? undefined)
      .then((d) => { if (!cancelled) setData(d); })
      .catch((e: any) => { if (!cancelled) setError(e?.message || "Erreur lors du chargement du suivi par catégorie."); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [year?.id, selectedEntityId]);

  if (!year) return <p className="text-sm text-[#8a8a8a]">Crée un exercice pour voir le suivi.</p>;
  if (loading) return <p className="text-sm text-[#8a8a8a]">Chargement…</p>;
  if (error) return <p className="text-sm text-alert">{error}</p>;
  if (!data) return null;

  const hasNMinus1 = data.categories.some((c: any) => c.realized_n_minus_1 !== 0);

  return (
    <div>
      {selectedEntity && (
        <p className="mb-3 text-xs text-[#8a8a8a]">
          Filtré pour <span className="text-accent-sand font-medium">{selectedEntity.name}</span> et sous-entités.
        </p>
      )}
    <div className="bg-bg-card border border-border rounded-2xl overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-[#1a1a1a] text-[#8a8a8a]">
            <th className="px-4 py-3 text-left text-xs font-medium uppercase">Catégorie</th>
            <th className="px-4 py-3 text-right text-xs font-medium uppercase">Alloué</th>
            <th className="px-4 py-3 text-right text-xs font-medium uppercase">Réalisé</th>
            <th className="px-4 py-3 text-right text-xs font-medium uppercase">% consommé</th>
            {hasNMinus1 && (
              <th className="px-4 py-3 text-right text-xs font-medium uppercase">N-1</th>
            )}
          </tr>
        </thead>
        <tbody>
          {data.categories.map((c: any, idx: number) => {
            const pct = c.percent_consumed;
            return (
              <tr key={c.category_id ?? "uncategorized"} className={idx > 0 ? "border-t border-[#1a1a1a]" : ""}>
                <td className="px-4 py-3 text-white font-medium">{c.category_name}</td>
                <td className="px-4 py-3 text-right text-text-secondary">
                  {c.allocated > 0 ? formatEuros(c.allocated) : "—"}
                </td>
                <td className={`px-4 py-3 text-right font-semibold ${c.allocated > 0 && c.realized > c.allocated ? "text-alert" : "text-white"}`}>
                  {formatEuros(c.realized)}
                </td>
                <td className="px-4 py-3">
                  {c.allocated > 0 ? (
                    <div className="flex items-center gap-3 justify-end">
                      <span className="font-medium" style={{ color: budgetColor(pct) }}>
                        {pct.toFixed(1)} %
                      </span>
                      <div className="w-24 h-1.5 bg-[#1a1a1a] rounded-full overflow-hidden">
                        <div
                          className="h-full rounded-full transition-all duration-500"
                          style={{
                            width: `${Math.min(pct, 100)}%`,
                            backgroundColor: budgetColor(pct),
                          }}
                        />
                      </div>
                    </div>
                  ) : (
                    <span className="text-[#8a8a8a] block text-right">—</span>
                  )}
                </td>
                {hasNMinus1 && (
                  <td className="px-4 py-3 text-right text-text-secondary">
                    {c.realized_n_minus_1 !== 0 ? formatEuros(c.realized_n_minus_1) : "—"}
                  </td>
                )}
              </tr>
            );
          })}
        </tbody>
        <tfoot>
          <tr className="border-t-2 border-border bg-[#0a0a0a]">
            <td className="px-4 py-3 text-white font-semibold">Total</td>
            <td className="px-4 py-3 text-right text-white font-semibold">
              {data.totals.allocated > 0 ? formatEuros(data.totals.allocated) : "—"}
            </td>
            <td className="px-4 py-3 text-right text-white font-semibold">
              {formatEuros(data.totals.realized)}
            </td>
            <td colSpan={hasNMinus1 ? 2 : 1}></td>
          </tr>
        </tfoot>
      </table>
    </div>
    </div>
  );
}
