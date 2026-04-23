import { useEffect, useState } from "react";
import { ShieldCheck } from "lucide-react";

interface AuditEntry {
  id: number;
  timestamp: string;
  user_id: number | null;
  action: string;
  table_name: string;
  record_id: number | null;
  before_value: string | null;
  after_value: string | null;
}

const TABLE_OPTIONS = [
  { value: "", label: "Toutes les tables" },
  { value: "transactions", label: "transactions" },
  { value: "reimbursements", label: "reimbursements" },
  { value: "categories", label: "categories" },
  { value: "entities", label: "entities" },
  { value: "entity_balance_refs", label: "entity_balance_refs" },
  { value: "fiscal_years", label: "fiscal_years" },
  { value: "budget_allocations", label: "budget_allocations" },
  { value: "fiscal_year_opening_balances", label: "fiscal_year_opening_balances" },
  { value: "users", label: "users" },
  { value: "sessions", label: "sessions (login)" },
];

export default function AuditSection() {
  const [entries, setEntries] = useState<AuditEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState(false);
  const [selectedTable, setSelectedTable] = useState("");

  useEffect(() => {
    setLoading(true);
    setError(null);
    const params = new URLSearchParams({ limit: "200" });
    if (selectedTable) params.set("table_name", selectedTable);
    fetch(`/api/audit/?${params.toString()}`)
      .then((r) => {
        if (!r.ok) throw new Error(r.statusText);
        return r.json();
      })
      .then((data) => { setEntries(data); setExpanded(false); })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [selectedTable]);

  const shown = expanded ? entries : entries.slice(0, 20);

  return (
    <section className="mb-8">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-base font-semibold text-white flex items-center gap-2">
          <ShieldCheck size={16} className="text-[#F2C48D]" />
          Journal d'audit
        </h2>
        <select
          value={selectedTable}
          onChange={(e) => setSelectedTable(e.target.value)}
          style={{
            background: "#111",
            border: "1px solid #333",
            color: "#B0B0B0",
            borderRadius: "6px",
            padding: "4px 8px",
            fontSize: "12px",
            outline: "none",
            accentColor: "#F2C48D",
          }}
        >
          {TABLE_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
      </div>
      <div className="bg-[#111] border border-[#222] rounded-2xl overflow-hidden">
        {loading ? (
          <div className="py-8 text-center text-sm text-[#666]">Chargement…</div>
        ) : error ? (
          <div className="p-4 text-sm text-[#FF5252]">{error}</div>
        ) : entries.length === 0 ? (
          <div className="py-8 text-center text-sm text-[#666]">Aucun événement enregistré.</div>
        ) : (
          <>
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-[#1a1a1a]">
                  <th className="px-4 py-2.5 text-left text-[10px] font-medium text-[#666] uppercase tracking-wider">Date</th>
                  <th className="px-4 py-2.5 text-left text-[10px] font-medium text-[#666] uppercase tracking-wider">Action</th>
                  <th className="px-4 py-2.5 text-left text-[10px] font-medium text-[#666] uppercase tracking-wider">Table</th>
                  <th className="px-4 py-2.5 text-right text-[10px] font-medium text-[#666] uppercase tracking-wider">ID</th>
                </tr>
              </thead>
              <tbody>
                {shown.map((e, idx) => (
                  <tr key={e.id} className={idx > 0 ? "border-t border-[#1a1a1a]" : ""}>
                    <td className="px-4 py-2 text-[#B0B0B0] whitespace-nowrap">
                      {new Date(e.timestamp).toLocaleString("fr-FR")}
                    </td>
                    <td className="px-4 py-2">
                      <span className="inline-block px-1.5 py-0.5 rounded bg-[#222] text-[#B0B0B0] text-[10px] font-mono">
                        {e.action}
                      </span>
                    </td>
                    <td className="px-4 py-2 text-[#B0B0B0]">{e.table_name}</td>
                    <td className="px-4 py-2 text-right text-[#666]">
                      {e.record_id !== null ? `#${e.record_id}` : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {entries.length > 20 && (
              <div className="border-t border-[#1a1a1a] p-3 text-center">
                <button
                  onClick={() => setExpanded(!expanded)}
                  className="text-xs text-[#F2C48D] hover:underline"
                >
                  {expanded ? "Réduire" : `Afficher les ${entries.length} entrées`}
                </button>
              </div>
            )}
          </>
        )}
      </div>
    </section>
  );
}
