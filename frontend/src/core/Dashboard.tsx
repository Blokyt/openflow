import { useEffect, useState } from "react";
import { api } from "../api";
import { DashboardSummary } from "../types";
import { TrendingUp, TrendingDown, Wallet, Hash } from "lucide-react";

const eurFormatter = new Intl.NumberFormat("fr-FR", { style: "currency", currency: "EUR" });

function SummaryCard({
  label,
  value,
  icon: Icon,
  valueColor,
}: {
  label: string;
  value: string;
  icon: React.ElementType;
  valueColor: string;
}) {
  return (
    <div className="bg-[#111] border border-[#222] rounded-2xl p-6 flex items-center gap-4">
      <div className="p-3 rounded-xl bg-[#1a1a1a] border border-[#222]">
        <Icon size={20} strokeWidth={1.5} className="text-[#B0B0B0]" />
      </div>
      <div>
        <p className="text-xs font-medium text-[#666] uppercase tracking-wider mb-1">{label}</p>
        <p className={`text-xl font-bold ${valueColor}`}>{value}</p>
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
        <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-[#F2C48D]" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-8">
        <div className="bg-[#1a0a0a] border border-[#FF5252]/30 text-[#FF5252] rounded-2xl p-4">{error}</div>
      </div>
    );
  }

  if (!summary) return null;

  const balancePositive = summary.balance >= 0;

  return (
    <div className="p-8">
      {/* Header with large balance */}
      <div className="mb-10">
        <p className="text-sm font-medium text-[#666] uppercase tracking-wider mb-2">Solde actuel</p>
        <div className="relative inline-block">
          <div className="absolute -inset-4 bg-[rgba(26,115,232,0.08)] rounded-3xl blur-xl pointer-events-none" />
          <h1
            className={`relative text-5xl font-bold tracking-tight ${
              balancePositive ? "text-white" : "text-[#FF5252]"
            }`}
            style={{ letterSpacing: "-0.02em" }}
          >
            {eurFormatter.format(summary.balance)}
          </h1>
        </div>
        {summary.reference_date && summary.reference_amount !== undefined && (
          <p className="mt-3 text-sm text-[#666]">
            Référence au{" "}
            <span className="text-[#B0B0B0] font-medium">{summary.reference_date}</span>{" "}:{" "}
            <span className="text-[#B0B0B0] font-medium">{eurFormatter.format(summary.reference_amount)}</span>
          </p>
        )}
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        <SummaryCard
          label="Recettes"
          value={eurFormatter.format(summary.total_income)}
          icon={TrendingUp}
          valueColor="text-[#00C853]"
        />
        <SummaryCard
          label="Dépenses"
          value={eurFormatter.format(summary.total_expenses)}
          icon={TrendingDown}
          valueColor="text-[#FF5252]"
        />
        <SummaryCard
          label="Transactions"
          value={String(summary.transaction_count)}
          icon={Hash}
          valueColor="text-white"
        />
      </div>
    </div>
  );
}
