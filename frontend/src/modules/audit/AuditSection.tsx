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

export default function AuditSection() {
  const [entries, setEntries] = useState<AuditEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    fetch("/api/audit/?limit=200")
      .then((r) => {
        if (!r.ok) throw new Error(r.statusText);
        return r.json();
      })
      .then(setEntries)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  const shown = expanded ? entries : entries.slice(0, 20);

  return (
    <section className="mb-8">
      <h2 className="text-base font-semibold text-white mb-3 flex items-center gap-2">
        <ShieldCheck size={16} className="text-[#F2C48D]" />
        Journal d'audit
      </h2>
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
