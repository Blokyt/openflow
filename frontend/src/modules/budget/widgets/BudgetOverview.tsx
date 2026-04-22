import { useEffect, useState } from "react";
import { useFiscalYear } from "../../../core/FiscalYearContext";
import { api } from "../../../api";
import { Link } from "react-router-dom";
import { ArrowRight } from "lucide-react";

const eur = new Intl.NumberFormat("fr-FR", { style: "currency", currency: "EUR" });

export default function BudgetOverview() {
  const { selectedYear } = useFiscalYear();
  const [view, setView] = useState<any | null>(null);

  useEffect(() => {
    if (!selectedYear) { setView(null); return; }
    api.getBudgetView(selectedYear.id).then(setView).catch(() => setView(null));
  }, [selectedYear?.id]);

  if (!selectedYear) {
    return (
      <div className="bg-[#111] border border-[#222] rounded-2xl p-6">
        <p className="text-xs font-medium text-[#666] uppercase tracking-wider mb-3">Budget</p>
        <p className="text-sm text-[#666]">
          <Link to="/budget" className="text-[#F2C48D] hover:underline">Crée un exercice</Link> pour activer le suivi.
        </p>
      </div>
    );
  }
  if (!view) return null;

  const allocated = view.totals.allocated as number;
  const realized = Math.abs(view.totals.realized as number);
  const pct = allocated > 0 ? (realized / allocated) * 100 : 0;
  const barColor = pct < 70 ? "#00C853" : pct < 95 ? "#F2C48D" : "#FF5252";

  const overspending = view.entities
    .filter((e: any) => e.allocated_total > 0 && Math.abs(e.realized_total) / e.allocated_total >= 0.95)
    .slice(0, 3);

  return (
    <div className="bg-[#111] border border-[#222] rounded-2xl p-6">
      <div className="flex items-center justify-between mb-3">
        <p className="text-xs font-medium text-[#666] uppercase tracking-wider">Budget — {selectedYear.name}</p>
        <Link to="/budget" className="text-xs text-[#F2C48D] hover:underline inline-flex items-center gap-0.5">
          Détail <ArrowRight size={11} />
        </Link>
      </div>
      <p className="text-sm text-white mb-2">
        {eur.format(realized)} consommés / {eur.format(allocated)} alloués
      </p>
      <div className="h-2 bg-[#1a1a1a] rounded-full overflow-hidden mb-3">
        <div className="h-full rounded-full" style={{ width: `${Math.min(pct, 100)}%`, backgroundColor: barColor }} />
      </div>
      <p className="text-xs text-[#666] mb-3">Reste {eur.format(allocated - realized)}</p>
      {overspending.length > 0 && (
        <div className="mt-2 pt-3 border-t border-[#1a1a1a]">
          <p className="text-xs text-[#666] uppercase tracking-wider mb-1.5">Top dépassements</p>
          <div className="space-y-1">
            {overspending.map((e: any) => (
              <div key={e.entity_id} className="flex items-center justify-between text-xs">
                <span className="text-white">{e.entity_name}</span>
                <span className="text-[#FF5252] font-medium">
                  {((Math.abs(e.realized_total) / e.allocated_total) * 100).toFixed(0)} %
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
