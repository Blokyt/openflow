import { useEffect, useState, useCallback, useRef } from "react";
import { GitCompare, Upload, CheckCircle, XCircle, Link, Unlink, Trash2, AlertCircle, X } from "lucide-react";

const BASE_URL = "/api";
async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(error.detail || response.statusText);
  }
  return response.json();
}

interface BankStatement {
  id: number;
  date: string;
  label: string;
  amount: number;
  matched_transaction_id: number | null;
  status: "unmatched" | "matched" | "ignored";
  imported_at: string;
}

interface Transaction {
  id: number;
  date: string;
  label: string;
  amount: number;
}

const eurFormatter = new Intl.NumberFormat("fr-FR", { style: "currency", currency: "EUR" });

function StatusBadge({ status }: { status: BankStatement["status"] }) {
  if (status === "matched") {
    return (
      <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium bg-[#00C853]/10 text-[#00C853] border border-[#00C853]/20">
        <CheckCircle size={10} /> Rapproché
      </span>
    );
  }
  if (status === "ignored") {
    return (
      <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium bg-[#1a1a1a] text-[#666] border border-[#222]">
        <XCircle size={10} /> Ignoré
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium bg-[#F2C48D]/10 text-[#F2C48D] border border-[#F2C48D]/20">
      <AlertCircle size={10} /> Non rapproché
    </span>
  );
}

function SuggestionsModal({
  statement,
  onMatch,
  onClose,
}: {
  statement: BankStatement;
  onMatch: (txId: number) => void;
  onClose: () => void;
}) {
  const [suggestions, setSuggestions] = useState<Transaction[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    request<Transaction[]>(`/bank_reconciliation/suggestions/${statement.id}`)
      .then(setSuggestions)
      .finally(() => setLoading(false));
  }, [statement.id]);

  return (
    <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 backdrop-blur-sm">
      <div className="bg-[#111] border border-[#222] rounded-2xl shadow-2xl w-full max-w-lg mx-4">
        <div className="flex items-center justify-between px-6 py-5 border-b border-[#1a1a1a]">
          <div>
            <h2 className="text-base font-semibold text-white">Suggestions de rapprochement</h2>
            <p className="text-xs text-[#666] mt-0.5">
              {statement.date} — {statement.label} — {eurFormatter.format(statement.amount)}
            </p>
          </div>
          <button onClick={onClose} className="text-[#666] hover:text-white transition-colors">
            <X size={18} />
          </button>
        </div>
        <div className="p-6">
          {loading ? (
            <div className="flex justify-center py-6">
              <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-[#F2C48D]" />
            </div>
          ) : suggestions.length === 0 ? (
            <p className="text-sm text-[#666] text-center py-6">
              Aucune transaction correspondante trouvée (même montant, ±5 jours).
            </p>
          ) : (
            <div className="space-y-2">
              {suggestions.map((tx) => (
                <div
                  key={tx.id}
                  className="flex items-center justify-between p-4 border border-[#222] rounded-xl hover:border-[#F2C48D]/40 hover:bg-[#1a1a1a] transition-colors"
                >
                  <div>
                    <p className="text-sm font-medium text-white">{tx.label}</p>
                    <p className="text-xs text-[#666]">{tx.date}</p>
                  </div>
                  <div className="flex items-center gap-3">
                    <span className={`text-sm font-semibold ${tx.amount >= 0 ? "text-[#00C853]" : "text-[#FF5252]"}`}>
                      {eurFormatter.format(tx.amount)}
                    </span>
                    <button
                      onClick={() => onMatch(tx.id)}
                      className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-black bg-[#F2C48D] rounded-full hover:bg-[#e8b87a] transition-colors"
                    >
                      <Link size={11} /> Associer
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function ImportPanel({ onImported }: { onImported: () => void }) {
  const [csvText, setCsvText] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  function parseCSV(text: string): { date: string; label: string; amount: number }[] {
    const lines = text.trim().split("\n").filter((l) => l.trim());
    const startIndex =
      lines[0] && lines[0].toLowerCase().startsWith("date") ? 1 : 0;
    return lines.slice(startIndex).map((line) => {
      const cols = line.split(/[,;]/).map((c) => c.trim().replace(/^"|"$/g, ""));
      if (cols.length < 3) throw new Error(`Ligne invalide: ${line}`);
      const amount = parseFloat(cols[2].replace(",", "."));
      if (isNaN(amount)) throw new Error(`Montant invalide: ${cols[2]}`);
      return { date: cols[0], label: cols[1], amount };
    });
  }

  async function handleImport() {
    setError(null);
    setResult(null);
    try {
      const entries = parseCSV(csvText);
      setLoading(true);
      const data = await request<any[]>("/bank_reconciliation/import", {
        method: "POST",
        body: JSON.stringify({ entries }),
      });
      const matched = data.filter((e) => e.status === "matched").length;
      setResult(
        `${data.length} ligne(s) importée(s). ${matched} rapprochement(s) automatique(s).`
      );
      setCsvText("");
      onImported();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (ev) => setCsvText(ev.target?.result as string);
    reader.readAsText(file);
  }

  return (
    <div className="bg-[#111] border border-[#222] rounded-2xl p-6 mb-6">
      <h2 className="text-base font-semibold text-white mb-1 flex items-center gap-2">
        <Upload size={15} strokeWidth={1.5} className="text-[#666]" /> Importer un relevé bancaire (CSV)
      </h2>
      <p className="text-xs text-[#666] mb-4">
        Format attendu: <code className="bg-[#1a1a1a] border border-[#222] px-1.5 py-0.5 rounded text-[#B0B0B0]">date,libelle,montant</code> (séparateur , ou ;)
      </p>

      {error && (
        <div className="mb-3 bg-[#1a0a0a] border border-[#FF5252]/30 text-[#FF5252] rounded-xl p-3 text-sm flex items-center justify-between">
          {error}
          <button onClick={() => setError(null)} className="text-[#FF5252]/70 hover:text-[#FF5252]"><X size={14} /></button>
        </div>
      )}
      {result && (
        <div className="mb-3 bg-[#0a1a0a] border border-[#00C853]/30 text-[#00C853] rounded-xl p-3 text-sm flex items-center justify-between">
          {result}
          <button onClick={() => setResult(null)} className="text-[#00C853]/70 hover:text-[#00C853]"><X size={14} /></button>
        </div>
      )}

      <div className="flex gap-3 mb-3">
        <button
          onClick={() => fileRef.current?.click()}
          className="text-sm text-white border border-[#333] rounded-full px-4 py-2 hover:border-[#444] hover:bg-[#1a1a1a] transition-colors"
        >
          Choisir un fichier…
        </button>
        <input ref={fileRef} type="file" accept=".csv,.txt" className="hidden" onChange={handleFileChange} />
      </div>

      <textarea
        value={csvText}
        onChange={(e) => setCsvText(e.target.value)}
        placeholder={"2026-01-10,Virement recu,1500.00\n2026-01-12,Paiement fournisseur,-320.50"}
        rows={5}
        className="w-full bg-[#0a0a0a] border border-[#222] rounded-xl px-3 py-2.5 text-sm font-mono text-white focus:outline-none focus:border-[#F2C48D] transition-colors resize-y placeholder-[#444]"
      />

      <button
        onClick={handleImport}
        disabled={loading || !csvText.trim()}
        className="mt-3 flex items-center gap-2 px-5 py-2.5 text-sm font-semibold text-black bg-[#F2C48D] rounded-full hover:bg-[#e8b87a] disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
      >
        {loading ? (
          <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-black" />
        ) : (
          <Upload size={14} strokeWidth={1.5} />
        )}
        Importer
      </button>
    </div>
  );
}

export default function BankReconciliation() {
  const [statements, setStatements] = useState<BankStatement[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filterStatus, setFilterStatus] = useState<string>("");
  const [suggestFor, setSuggestFor] = useState<BankStatement | null>(null);
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<number | null>(null);

  const fetchStatements = useCallback(() => {
    setLoading(true);
    const query = filterStatus ? `?status=${filterStatus}` : "";
    request<BankStatement[]>(`/bank_reconciliation/${query}`)
      .then(setStatements)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [filterStatus]);

  useEffect(() => {
    fetchStatements();
  }, [fetchStatements]);

  async function handleMatch(statementId: number, transactionId: number) {
    try {
      await request("/bank_reconciliation/match", {
        method: "POST",
        body: JSON.stringify({ statement_id: statementId, transaction_id: transactionId }),
      });
      setSuggestFor(null);
      fetchStatements();
    } catch (e: any) {
      setError(e.message);
    }
  }

  async function handleUnmatch(id: number) {
    try {
      await request(`/bank_reconciliation/unmatch/${id}`, { method: "POST" });
      fetchStatements();
    } catch (e: any) {
      setError(e.message);
    }
  }

  async function handleDelete(id: number) {
    setDeletingId(id);
    try {
      await request(`/bank_reconciliation/${id}`, { method: "DELETE" });
      setConfirmDelete(null);
      fetchStatements();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setDeletingId(null);
    }
  }

  const totalUnmatched = statements.filter((s) => s.status === "unmatched").length;
  const totalMatched = statements.filter((s) => s.status === "matched").length;

  return (
    <div className="p-8">
      <div className="flex items-center justify-between mb-8">
        <div className="flex items-center gap-3">
          <GitCompare size={20} strokeWidth={1.5} className="text-[#666]" />
          <h1 className="text-3xl font-bold text-white" style={{ letterSpacing: "-0.02em" }}>
            Rapprochement bancaire
          </h1>
        </div>
        <div className="flex items-center gap-3 text-sm">
          <span className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-[#F2C48D]/10 border border-[#F2C48D]/20 rounded-full text-[#F2C48D] font-medium">
            <AlertCircle size={12} /> {totalUnmatched} non rapprochés
          </span>
          <span className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-[#00C853]/10 border border-[#00C853]/20 rounded-full text-[#00C853] font-medium">
            <CheckCircle size={12} /> {totalMatched} rapprochés
          </span>
        </div>
      </div>

      {error && (
        <div className="mb-4 bg-[#1a0a0a] border border-[#FF5252]/30 text-[#FF5252] rounded-2xl p-4 text-sm flex items-center justify-between">
          {error}
          <button onClick={() => setError(null)} className="text-[#FF5252]/70 hover:text-[#FF5252]"><X size={16} /></button>
        </div>
      )}

      <ImportPanel onImported={fetchStatements} />

      {/* Filters */}
      <div className="mb-5 flex items-center gap-2 flex-wrap">
        <label className="text-sm text-[#666] font-medium mr-1">Filtrer :</label>
        {(["", "unmatched", "matched", "ignored"] as const).map((s) => (
          <button
            key={s}
            onClick={() => setFilterStatus(s)}
            className={`px-4 py-2 text-sm rounded-full border transition-colors font-medium ${
              filterStatus === s
                ? "bg-[#F2C48D] text-black border-[#F2C48D]"
                : "bg-transparent text-[#666] border-[#222] hover:border-[#333] hover:text-white"
            }`}
          >
            {s === "" ? "Tous" : s === "unmatched" ? "Non rapprochés" : s === "matched" ? "Rapprochés" : "Ignorés"}
          </button>
        ))}
      </div>

      {/* Table */}
      <div className="bg-[#111] border border-[#222] rounded-2xl overflow-hidden">
        {loading ? (
          <div className="flex items-center justify-center py-12">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-[#F2C48D]" />
          </div>
        ) : statements.length === 0 ? (
          <div className="text-center py-12 text-[#666] text-sm">
            Aucun relevé bancaire importé.
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[#1a1a1a]">
                <th className="px-5 py-3.5 text-left text-xs font-medium text-[#666] uppercase tracking-wider">Date</th>
                <th className="px-5 py-3.5 text-left text-xs font-medium text-[#666] uppercase tracking-wider">Libellé</th>
                <th className="px-5 py-3.5 text-right text-xs font-medium text-[#666] uppercase tracking-wider">Montant</th>
                <th className="px-5 py-3.5 text-center text-xs font-medium text-[#666] uppercase tracking-wider">Statut</th>
                <th className="px-5 py-3.5 text-right text-xs font-medium text-[#666] uppercase tracking-wider">Actions</th>
              </tr>
            </thead>
            <tbody>
              {statements.map((stmt, idx) => (
                <tr key={stmt.id} className={`hover:bg-[#1a1a1a] transition-colors ${idx > 0 ? "border-t border-[#1a1a1a]" : ""}`}>
                  <td className="px-5 py-3.5 text-[#B0B0B0] whitespace-nowrap">{stmt.date}</td>
                  <td className="px-5 py-3.5 font-medium text-white">{stmt.label}</td>
                  <td className={`px-5 py-3.5 text-right font-semibold whitespace-nowrap ${stmt.amount >= 0 ? "text-[#00C853]" : "text-[#FF5252]"}`}>
                    {eurFormatter.format(stmt.amount)}
                  </td>
                  <td className="px-5 py-3.5 text-center">
                    <StatusBadge status={stmt.status} />
                  </td>
                  <td className="px-5 py-3.5 text-right">
                    {confirmDelete === stmt.id ? (
                      <span className="inline-flex items-center gap-2">
                        <span className="text-xs text-[#666]">Supprimer ?</span>
                        <button
                          onClick={() => handleDelete(stmt.id)}
                          disabled={deletingId === stmt.id}
                          className="text-xs font-medium text-[#FF5252] hover:text-red-400"
                        >
                          Oui
                        </button>
                        <button
                          onClick={() => setConfirmDelete(null)}
                          className="text-xs font-medium text-[#666] hover:text-white"
                        >
                          Non
                        </button>
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1">
                        {stmt.status === "unmatched" && (
                          <button
                            onClick={() => setSuggestFor(stmt)}
                            className="p-1.5 text-[#666] hover:text-white rounded-lg hover:bg-[#222] transition-colors"
                            title="Rapprocher manuellement"
                          >
                            <Link size={14} strokeWidth={1.5} />
                          </button>
                        )}
                        {stmt.status === "matched" && (
                          <button
                            onClick={() => handleUnmatch(stmt.id)}
                            className="p-1.5 text-[#666] hover:text-[#F2C48D] rounded-lg hover:bg-[#222] transition-colors"
                            title="Annuler le rapprochement"
                          >
                            <Unlink size={14} strokeWidth={1.5} />
                          </button>
                        )}
                        <button
                          onClick={() => setConfirmDelete(stmt.id)}
                          className="p-1.5 text-[#666] hover:text-[#FF5252] rounded-lg hover:bg-[#222] transition-colors"
                          title="Supprimer"
                        >
                          <Trash2 size={14} strokeWidth={1.5} />
                        </button>
                      </span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {suggestFor && (
        <SuggestionsModal
          statement={suggestFor}
          onMatch={(txId) => handleMatch(suggestFor.id, txId)}
          onClose={() => setSuggestFor(null)}
        />
      )}
    </div>
  );
}
