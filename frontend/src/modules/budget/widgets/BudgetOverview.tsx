import { useEffect, useState } from "react";
import { useFiscalYear } from "../../../core/FiscalYearContext";
import { useEntity } from "../../../core/EntityContext";
import { api } from "../../../api";
import { formatEuros, budgetColor } from "../../../utils/format";
import { Link } from "react-router-dom";
import { ArrowRight } from "lucide-react";

/** Cherche le nœud d'entité `id` dans l'arbre budgétaire (groups). */
function findGroupNode(nodes: any[], id: number): any | null {
  for (const n of nodes) {
    if (n.entity_id === id) return n;
    const found = findGroupNode(n.children ?? [], id);
    if (found) return found;
  }
  return null;
}

/** Aplati un sous-arbre budgétaire en liste (pour les dépassements). */
function flattenGroup(node: any): any[] {
  return [node, ...(node.children ?? []).flatMap(flattenGroup)];
}

export default function BudgetOverview() {
  const { selectedYear } = useFiscalYear();
  const { selectedEntityId, selectedEntity } = useEntity();
  const [view, setView] = useState<any | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!selectedYear) { setView(null); return; }
    let cancelled = false;
    setView(null);
    setError(null);
    api.getBudgetView(selectedYear.id)
      .then((d) => { if (!cancelled) setView(d); })
      // Sans état d'erreur distinct, un échec réseau laissait le widget
      // bloqué sur "Chargement…" (indiscernable d'un vrai chargement).
      .catch((e: any) => { if (!cancelled) setError(e?.message || "Erreur lors du chargement du budget."); });
    return () => { cancelled = true; };
  }, [selectedYear?.id]);

  if (!selectedYear) {
    return (
      <div className="bg-[#111] border border-[#222] rounded-2xl p-6">
        <p className="text-xs font-medium text-[#8a8a8a] uppercase tracking-wider mb-3">Budget</p>
        <p className="text-sm text-[#8a8a8a]">
          <Link to="/budget" className="text-[#F2C48D] hover:underline">Crée un exercice</Link> pour activer le suivi.
        </p>
      </div>
    );
  }
  if (error) {
    return (
      <div className="bg-[#111] border border-[#222] rounded-2xl p-6">
        <p className="text-xs font-medium text-[#8a8a8a] uppercase tracking-wider mb-3">Budget</p>
        <p className="text-sm text-[#FF5252]">{error}</p>
      </div>
    );
  }
  if (!view) {
    return (
      <div className="bg-[#111] border border-[#222] rounded-2xl p-6">
        <p className="text-xs font-medium text-[#8a8a8a] uppercase tracking-wider mb-3">Budget</p>
        <div className="h-2 bg-[#1a1a1a] rounded-full overflow-hidden mb-3 animate-pulse" />
        <p className="text-sm text-[#8a8a8a]">Chargement…</p>
      </div>
    );
  }

  // Périmètre : si une entité est sélectionnée globalement, le widget se limite
  // à son sous-arbre (mêmes chiffres que la page Budget filtrée). Sinon, total global.
  const scopedNode = selectedEntityId ? findGroupNode(view.groups ?? [], selectedEntityId) : null;
  const scopeEntities: any[] = scopedNode ? flattenGroup(scopedNode) : view.entities;

  // Suivi de consommation = dépenses réalisées vs budget dépenses alloué
  // (et non le net recettes - dépenses, qui faussait le taux et les « dépassements »).
  const allocated: number = scopedNode ? scopedNode.allocated_expense : view.totals.allocated_expense;
  const realized: number = scopedNode ? scopedNode.realized_expense : view.totals.realized_expense;
  const pct = allocated > 0 ? (realized / allocated) * 100 : 0;
  const barColor = budgetColor(pct);

  const overspending = scopeEntities
    .filter((e: any) => e.allocated_expense > 0 && e.realized_expense / e.allocated_expense >= 0.95)
    .slice(0, 3);

  const title = selectedEntity && scopedNode
    ? `Budget · ${selectedYear.name} · ${selectedEntity.name}`
    : `Budget · ${selectedYear.name}`;

  return (
    <div className="bg-[#111] border border-[#222] rounded-2xl p-6">
      <div className="flex items-center justify-between mb-3 gap-2">
        <p className="text-xs font-medium text-[#8a8a8a] uppercase tracking-wider truncate min-w-0">{title}</p>
        <Link to="/budget" className="text-xs text-[#F2C48D] hover:underline inline-flex items-center gap-0.5 flex-shrink-0">
          Détail <ArrowRight size={11} />
        </Link>
      </div>
      {selectedEntityId && !scopedNode && (
        <p className="text-xs text-[#8a8a8a] mb-2">
          Aucune ligne budgétaire pour cette entité : chiffres globaux affichés.
        </p>
      )}
      {allocated === 0 ? (
        <p className="text-sm text-[#8a8a8a] mb-3">
          {formatEuros(realized)} dépensés, aucun budget alloué sur ce périmètre.{" "}
          <Link to="/budget" className="text-[#F2C48D] hover:underline">Budgéter</Link>
        </p>
      ) : (
        <>
          <p className="text-sm text-white mb-2">
            {formatEuros(realized)} consommés / {formatEuros(allocated)} alloués
          </p>
          <div className="h-2 bg-[#1a1a1a] rounded-full overflow-hidden mb-3">
            <div className="h-full rounded-full" style={{ width: `${Math.min(pct, 100)}%`, backgroundColor: barColor }} />
          </div>
          {allocated - realized < 0 ? (
            <p className="text-xs text-[#FF5252] mb-3">Dépassement {formatEuros(realized - allocated)}</p>
          ) : (
            <p className="text-xs text-[#8a8a8a] mb-3">Reste {formatEuros(allocated - realized)}</p>
          )}
        </>
      )}
      {overspending.length > 0 && (
        <div className="mt-2 pt-3 border-t border-[#1a1a1a]">
          <p className="text-xs text-[#8a8a8a] uppercase tracking-wider mb-1.5">Top dépassements</p>
          <div className="space-y-1">
            {overspending.map((e: any) => (
              <div key={e.entity_id} className="flex items-center justify-between text-xs gap-2">
                <span className="text-white truncate min-w-0">{e.entity_name}</span>
                <span className="text-[#FF5252] font-medium flex-shrink-0">
                  {((e.realized_expense / e.allocated_expense) * 100).toFixed(0)} %
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
