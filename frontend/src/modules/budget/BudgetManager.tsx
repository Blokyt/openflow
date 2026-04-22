import { useState } from "react";
import { useFiscalYear } from "../../core/FiscalYearContext";
import OverviewTab from "./tabs/OverviewTab";
import AllocationTab from "./tabs/AllocationTab";
import FiscalYearsTab from "./tabs/FiscalYearsTab";

type TabId = "overview" | "allocation" | "years";

const TABS: { id: TabId; label: string }[] = [
  { id: "overview", label: "Vue d'ensemble" },
  { id: "allocation", label: "Allocation" },
  { id: "years", label: "Exercices" },
];

export default function BudgetManager() {
  const { years, selectedYear, setSelectedYearId, reload } = useFiscalYear();
  const [tab, setTab] = useState<TabId>("overview");

  return (
    <div className="p-8 space-y-6">
      <div className="flex items-end justify-between">
        <div>
          <h1 className="text-3xl font-bold text-white" style={{ letterSpacing: "-0.02em" }}>
            Budget
          </h1>
          <p className="text-sm text-[#999] mt-1">
            Allocations, suivi du réalisé, comparaison à l'exercice précédent.
          </p>
        </div>
        {years.length > 0 && (
          <select
            value={selectedYear?.id ?? ""}
            onChange={(e) => setSelectedYearId(parseInt(e.target.value, 10))}
            className="bg-[#111] border border-[#222] rounded-xl px-3 py-2.5 text-sm text-white"
          >
            {years.map((y) => (
              <option key={y.id} value={y.id}>
                {y.name}{y.is_current === 1 ? " ●" : ""}
              </option>
            ))}
          </select>
        )}
      </div>

      <div className="flex gap-1 border-b border-[#222]">
        {TABS.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors ${
              tab === t.id
                ? "border-[#F2C48D] text-white"
                : "border-transparent text-[#666] hover:text-white"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === "overview" && <OverviewTab year={selectedYear} />}
      {tab === "allocation" && <AllocationTab year={selectedYear} onChange={reload} />}
      {tab === "years" && <FiscalYearsTab />}
    </div>
  );
}
