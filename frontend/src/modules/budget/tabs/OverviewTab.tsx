import { useEffect, useState } from "react";
import { api } from "../../../api";
import { FiscalYear } from "../../../core/FiscalYearContext";
import { ChevronDown, ChevronRight } from "lucide-react";

const eur = new Intl.NumberFormat("fr-FR", { style: "currency", currency: "EUR" });

interface Props { year: FiscalYear | null }

export default function OverviewTab({ year }: Props) {
  const [data, setData] = useState<any | null>(null);
  const [loading, setLoading] = useState(false);
  const [expanded, setExpanded] = useState<Set<number>>(new Set());

  useEffect(() => {
    if (!year) return;
    setLoading(true);
    api.getBudgetView(year.id).then(setData).finally(() => setLoading(false));
  }, [year?.id]);

  if (!year) return <p className="text-sm text-[#666]">Crée un exercice pour voir le suivi.</p>;
  if (loading) return <p className="text-sm text-[#666]">Chargement…</p>;
  if (!data) return null;

  const hasNMinus1 = data.previous_fiscal_year_id !== null;

  function toggle(id: number) {
    setExpanded((prev) => {
      const n = new Set(prev);
      if (n.has(id)) n.delete(id); else n.add(id);
      return n;
    });
  }

  function color(pct: number): string {
    if (pct < 70) return "#00C853";
    if (pct < 95) return "#F2C48D";
    return "#FF5252";
  }

  return (
    <div className="bg-[#111] border border-[#222] rounded-2xl overflow-hidden">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-[#1a1a1a] text-[#666]">
            <th className="px-4 py-3 text-left text-xs font-medium uppercase"></th>
            <th className="px-4 py-3 text-left text-xs font-medium uppercase">Entité</th>
            <th className="px-4 py-3 text-right text-xs font-medium uppercase">Ouverture</th>
            <th className="px-4 py-3 text-right text-xs font-medium uppercase">Alloué</th>
            <th className="px-4 py-3 text-right text-xs font-medium uppercase">Réalisé</th>
            <th className="px-4 py-3 text-right text-xs font-medium uppercase">% consommé</th>
            {hasNMinus1 && <th className="px-4 py-3 text-right text-xs font-medium uppercase">N-1</th>}
            {hasNMinus1 && <th className="px-4 py-3 text-right text-xs font-medium uppercase">Variation</th>}
          </tr>
        </thead>
        <tbody>
          {data.entities.map((ent: any, idx: number) => {
            const pct = ent.allocated_total > 0
              ? Math.abs(ent.realized_total) / ent.allocated_total * 100
              : 0;
            return (
              <>
                <tr key={ent.entity_id} className={idx > 0 ? "border-t border-[#1a1a1a]" : ""}>
                  <td className="px-4 py-3">
                    {ent.categories.length > 0 && (
                      <button onClick={() => toggle(ent.entity_id)} className="text-[#666] hover:text-white">
                        {expanded.has(ent.entity_id) ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                      </button>
                    )}
                  </td>
                  <td className="px-4 py-3 text-white font-medium">{ent.entity_name}</td>
                  <td className="px-4 py-3 text-right text-[#B0B0B0]">{eur.format(ent.opening_balance)}</td>
                  <td className="px-4 py-3 text-right text-[#B0B0B0]">{eur.format(ent.allocated_total)}</td>
                  <td className={`px-4 py-3 text-right font-semibold ${ent.realized_total >= 0 ? "text-[#00C853]" : "text-[#FF5252]"}`}>
                    {eur.format(ent.realized_total)}
                  </td>
                  <td className="px-4 py-3 text-right" style={{ color: color(pct) }}>
                    {ent.allocated_total > 0 ? `${pct.toFixed(1)} %` : "—"}
                  </td>
                  {hasNMinus1 && (
                    <td className="px-4 py-3 text-right text-[#B0B0B0]">{eur.format(ent.realized_n_minus_1)}</td>
                  )}
                  {hasNMinus1 && (
                    <td className="px-4 py-3 text-right text-xs">
                      {ent.variation_pct !== null ? (
                        <span className={ent.variation_pct < 0 ? "text-[#00C853]" : "text-[#FF5252]"}>
                          {ent.variation_pct > 0 ? "+" : ""}{ent.variation_pct} %
                        </span>
                      ) : "—"}
                    </td>
                  )}
                </tr>
                {expanded.has(ent.entity_id) && ent.categories.map((c: any) => (
                  <tr key={`${ent.entity_id}-${c.allocation_id}`} className="bg-[#0a0a0a] text-xs">
                    <td className="px-4 py-2"></td>
                    <td className="px-8 py-2 text-[#B0B0B0]">↳ {c.category_name}</td>
                    <td className="px-4 py-2 text-right text-[#555]">—</td>
                    <td className="px-4 py-2 text-right text-[#B0B0B0]">{eur.format(c.allocated)}</td>
                    <td className="px-4 py-2 text-right">{eur.format(c.realized)}</td>
                    <td className="px-4 py-2 text-right" style={{ color: color(c.percent_consumed) }}>
                      {c.percent_consumed.toFixed(1)} %
                    </td>
                    {hasNMinus1 && <td className="px-4 py-2 text-right text-[#B0B0B0]">{eur.format(c.realized_n_minus_1)}</td>}
                    {hasNMinus1 && <td className="px-4 py-2 text-right">—</td>}
                  </tr>
                ))}
              </>
            );
          })}
        </tbody>
        <tfoot>
          <tr className="border-t-2 border-[#222] bg-[#0a0a0a]">
            <td></td>
            <td className="px-4 py-3 text-white font-semibold">Total</td>
            <td></td>
            <td className="px-4 py-3 text-right text-white font-semibold">{eur.format(data.totals.allocated)}</td>
            <td className="px-4 py-3 text-right text-white font-semibold">{eur.format(data.totals.realized)}</td>
            <td colSpan={hasNMinus1 ? 3 : 1}></td>
          </tr>
        </tfoot>
      </table>
    </div>
  );
}
