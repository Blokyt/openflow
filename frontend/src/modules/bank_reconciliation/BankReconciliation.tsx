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
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-700">
        <CheckCircle size={11} /> Rapproché
      </span>
    );
  }
  if (status === "ignored") {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-500">
        <XCircle size={11} /> Ignoré
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-yellow-100 text-yellow-700">
      <AlertCircle size={11} /> Non rapproché
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
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
      <div className="bg-white rounded-xl shadow-xl w-full max-w-lg mx-4">
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-200">
          <div>
            <h2 className="text-base font-semibold text-gray-900">Suggestions de rapprochement</h2>
            <p className="text-xs text-gray-500 mt-0.5">
              {statement.date} — {statement.label} — {eurFormatter.format(statement.amount)}
            </p>
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600">
            <X size={18} />
          </button>
        </div>
        <div className="p-5">
          {loading ? (
            <div className="flex justify-center py-6">
              <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-indigo-600" />
            </div>
          ) : suggestions.length === 0 ? (
            <p className="text-sm text-gray-500 text-center py-6">
              Aucune transaction correspondante trouvée (même montant, ±5 jours).
            </p>
          ) : (
            <div className="space-y-2">
              {suggestions.map((tx) => (
                <div
                  key={tx.id}
                  className="flex items-center justify-between p-3 border border-gray-200 rounded-lg hover:border-indigo-300 hover:bg-indigo-50 transition-colors"
                >
                  <div>
                    <p className="text-sm font-medium text-gray-900">{tx.label}</p>
                    <p className="text-xs text-gray-500">{tx.date}</p>
                  </div>
                  <div className="flex items-center gap-3">
                    <span
                      className={`text-sm font-semibold ${
                        tx.amount >= 0 ? "text-green-600" : "text-red-600"
                      }`}
                    >
                      {eurFormatter.format(tx.amount)}
                    </span>
                    <button
                      onClick={() => onMatch(tx.id)}
                      className="flex items-center gap-1 px-3 py-1.5 text-xs font-medium text-white bg-indigo-600 rounded-md hover:bg-indigo-700"
                    >
                      <Link size={12} /> Associer
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
    // Skip header line if first column looks like "date" or "Date"
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
    <div className="bg-white border border-gray-200 rounded-xl p-5 shadow-sm mb-6">
      <h2 className="text-base font-semibold text-gray-800 mb-3 flex items-center gap-2">
        <Upload size={16} /> Importer un relevé bancaire (CSV)
      </h2>
      <p className="text-xs text-gray-500 mb-3">
        Format attendu: <code className="bg-gray-100 px-1 rounded">date,libelle,montant</code> (séparateur , ou ;)
      </p>

      {error && (
        <div className="mb-3 bg-red-50 border border-red-200 text-red-700 rounded-lg p-3 text-sm flex items-center justify-between">
          {error}
          <button onClick={() => setError(null)}><X size={14} /></button>
        </div>
      )}
      {result && (
        <div className="mb-3 bg-green-50 border border-green-200 text-green-700 rounded-lg p-3 text-sm flex items-center justify-between">
          {result}
          <button onClick={() => setResult(null)}><X size={14} /></button>
        </div>
      )}

      <div className="flex gap-3 mb-3">
        <button
          onClick={() => fileRef.current?.click()}
          className="text-sm text-indigo-600 border border-indigo-300 rounded-lg px-3 py-2 hover:bg-indigo-50"
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
        className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-indigo-500 resize-y"
      />

      <button
        onClick={handleImport}
        disabled={loading || !csvText.trim()}
        className="mt-3 flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-indigo-600 rounded-lg hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed"
      >
        {loading ? (
          <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white" />
        ) : (
          <Upload size={15} />
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
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <GitCompare size={22} className="text-indigo-600" />
          <h1 className="text-2xl font-bold text-gray-900">Rapprochement bancaire</h1>
        </div>
        <div className="flex items-center gap-4 text-sm text-gray-600">
          <span className="inline-flex items-center gap-1.5 px-3 py-1 bg-yellow-50 border border-yellow-200 rounded-full text-yellow-700 font-medium">
            <AlertCircle size={13} /> {totalUnmatched} non rapprochés
          </span>
          <span className="inline-flex items-center gap-1.5 px-3 py-1 bg-green-50 border border-green-200 rounded-full text-green-700 font-medium">
            <CheckCircle size={13} /> {totalMatched} rapprochés
          </span>
        </div>
      </div>

      {error && (
        <div className="mb-4 bg-red-50 border border-red-200 text-red-700 rounded-lg p-3 text-sm flex items-center justify-between">
          {error}
          <button onClick={() => setError(null)}><X size={16} /></button>
        </div>
      )}

      <ImportPanel onImported={fetchStatements} />

      {/* Filters */}
      <div className="mb-4 flex items-center gap-3">
        <label className="text-sm text-gray-600 font-medium">Filtrer :</label>
        {(["", "unmatched", "matched", "ignored"] as const).map((s) => (
          <button
            key={s}
            onClick={() => setFilterStatus(s)}
            className={`px-3 py-1.5 text-sm rounded-lg border transition-colors ${
              filterStatus === s
                ? "bg-indigo-600 text-white border-indigo-600"
                : "bg-white text-gray-600 border-gray-300 hover:border-indigo-400"
            }`}
          >
            {s === "" ? "Tous" : s === "unmatched" ? "Non rapprochés" : s === "matched" ? "Rapprochés" : "Ignorés"}
          </button>
        ))}
      </div>

      {/* Table */}
      <div className="bg-white border border-gray-200 rounded-xl shadow-sm overflow-hidden">
        {loading ? (
          <div className="flex items-center justify-center py-12">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-600" />
          </div>
        ) : statements.length === 0 ? (
          <div className="text-center py-12 text-gray-500 text-sm">
            Aucun relevé bancaire importé.
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th className="px-4 py-3 text-left font-medium text-gray-600">Date</th>
                <th className="px-4 py-3 text-left font-medium text-gray-600">Libellé</th>
                <th className="px-4 py-3 text-right font-medium text-gray-600">Montant</th>
                <th className="px-4 py-3 text-center font-medium text-gray-600">Statut</th>
                <th className="px-4 py-3 text-right font-medium text-gray-600">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {statements.map((stmt) => (
                <tr key={stmt.id} className="hover:bg-gray-50 transition-colors">
                  <td className="px-4 py-3 text-gray-600 whitespace-nowrap">{stmt.date}</td>
                  <td className="px-4 py-3 font-medium text-gray-900">{stmt.label}</td>
                  <td
                    className={`px-4 py-3 text-right font-semibold whitespace-nowrap ${
                      stmt.amount >= 0 ? "text-green-600" : "text-red-600"
                    }`}
                  >
                    {eurFormatter.format(stmt.amount)}
                  </td>
                  <td className="px-4 py-3 text-center">
                    <StatusBadge status={stmt.status} />
                  </td>
                  <td className="px-4 py-3 text-right">
                    {confirmDelete === stmt.id ? (
                      <span className="inline-flex items-center gap-2">
                        <span className="text-xs text-gray-500">Supprimer ?</span>
                        <button
                          onClick={() => handleDelete(stmt.id)}
                          disabled={deletingId === stmt.id}
                          className="text-xs font-medium text-red-600 hover:text-red-800"
                        >
                          Oui
                        </button>
                        <button
                          onClick={() => setConfirmDelete(null)}
                          className="text-xs font-medium text-gray-500 hover:text-gray-700"
                        >
                          Non
                        </button>
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-2">
                        {stmt.status === "unmatched" && (
                          <button
                            onClick={() => setSuggestFor(stmt)}
                            className="p-1 text-gray-400 hover:text-indigo-600 rounded"
                            title="Rapprocher manuellement"
                          >
                            <Link size={15} />
                          </button>
                        )}
                        {stmt.status === "matched" && (
                          <button
                            onClick={() => handleUnmatch(stmt.id)}
                            className="p-1 text-gray-400 hover:text-yellow-600 rounded"
                            title="Annuler le rapprochement"
                          >
                            <Unlink size={15} />
                          </button>
                        )}
                        <button
                          onClick={() => setConfirmDelete(stmt.id)}
                          className="p-1 text-gray-400 hover:text-red-600 rounded"
                          title="Supprimer"
                        >
                          <Trash2 size={15} />
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
