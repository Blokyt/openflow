import { useEffect, useState } from "react";
import { api } from "../api";
import { DashboardSummary } from "../types";
import { TrendingUp, TrendingDown, Wallet, Hash } from "lucide-react";

const eurFormatter = new Intl.NumberFormat("fr-FR", { style: "currency", currency: "EUR" });

function SummaryCard({
  label,
  value,
  icon: Icon,
  colorClass,
}: {
  label: string;
  value: string;
  icon: React.ElementType;
  colorClass: string;
}) {
  return (
    <div className={`rounded-xl p-5 shadow-sm flex items-center gap-4 ${colorClass}`}>
      <div className="p-3 rounded-full bg-white bg-opacity-30">
        <Icon size={22} />
      </div>
      <div>
        <p className="text-sm font-medium opacity-80">{label}</p>
        <p className="text-2xl font-bold">{value}</p>
      </div>
    </div>
  );
}

export default function Dashboard() {
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .getSummary()
      .then(setSummary)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-indigo-600" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-8">
        <div className="bg-red-50 border border-red-200 text-red-700 rounded-lg p-4">{error}</div>
      </div>
    );
  }

  if (!summary) return null;

  const balanceColor =
    summary.balance >= 0 ? "bg-green-500 text-white" : "bg-red-500 text-white";

  return (
    <div className="p-8">
      <h1 className="text-2xl font-bold text-gray-900 mb-6">Tableau de bord</h1>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <SummaryCard
          label="Solde actuel"
          value={eurFormatter.format(summary.balance)}
          icon={Wallet}
          colorClass={balanceColor}
        />
        <SummaryCard
          label="Recettes"
          value={eurFormatter.format(summary.total_income)}
          icon={TrendingUp}
          colorClass="bg-emerald-500 text-white"
        />
        <SummaryCard
          label="Dépenses"
          value={eurFormatter.format(summary.total_expenses)}
          icon={TrendingDown}
          colorClass="bg-orange-500 text-white"
        />
        <SummaryCard
          label="Transactions"
          value={String(summary.transaction_count)}
          icon={Hash}
          colorClass="bg-indigo-500 text-white"
        />
      </div>
      {summary.reference_date && summary.reference_amount !== undefined && (
        <p className="mt-6 text-sm text-gray-500">
          Solde de référence au{" "}
          <span className="font-medium">{summary.reference_date}</span> :{" "}
          <span className="font-medium">{eurFormatter.format(summary.reference_amount)}</span>
        </p>
      )}
    </div>
  );
}
