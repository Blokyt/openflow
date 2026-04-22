import { useEffect, useState, useCallback } from "react";
import { api } from "../../api";
import { Transaction, Category } from "../../types";
import { useEntity } from "../../core/EntityContext";
import TransactionForm from "./TransactionForm";
import AttachmentsSection from "./AttachmentsSection";
import AnnotationsSection from "./AnnotationsSection";
import { Plus, Pencil, Trash2, X, Search, ArrowRight, Eye, Download, FileJson, Hourglass, Check } from "lucide-react";

const eurFormatter = new Intl.NumberFormat("fr-FR", { style: "currency", currency: "EUR" });

export default function TransactionList() {
  const { selectedEntityId, selectedEntity } = useEntity();
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [categoryFilter, setCategoryFilter] = useState<string>("");
  const [reimbFilter, setReimbFilter] = useState<string>("");
  const [categories, setCategories] = useState<Category[]>([]);
  const [sortBy, setSortBy] = useState<"date" | "amount" | "label">("date");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");
  const [undoTx, setUndoTx] = useState<Transaction | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [editingTx, setEditingTx] = useState<Transaction | null>(null);
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<number | null>(null);
  const [detailTx, setDetailTx] = useState<Transaction | null>(null);
  const [activeModuleIds, setActiveModuleIds] = useState<Set<string>>(new Set());

  useEffect(() => {
    api.getModules()
      .then((mods: any[]) => setActiveModuleIds(new Set(mods.map((m) => m.id))))
      .catch(() => {});
    api.getCategories().then(setCategories).catch(() => {});
  }, []);

  const hasAttachments = activeModuleIds.has("attachments");
  const hasAnnotations = activeModuleIds.has("annotations");
  const hasExport = activeModuleIds.has("export");

  function buildExportQuery(): string {
    const p = new URLSearchParams();
    if (search) p.set("search", search);
    if (dateFrom) p.set("date_from", dateFrom);
    if (dateTo) p.set("date_to", dateTo);
    if (categoryFilter) p.set("category_id", categoryFilter);
    if (reimbFilter) p.set("reimb_status", reimbFilter);
    if (selectedEntityId) {
      p.set("entity_id", String(selectedEntityId));
      p.set("include_children", "true");
    }
    const q = p.toString();
    return q ? `?${q}` : "";
  }

  const fetchTransactions = useCallback(() => {
    setLoading(true);
    const params: Record<string, string> = {};
    if (search) params.search = search;
    if (dateFrom) params.date_from = dateFrom;
    if (dateTo) params.date_to = dateTo;
    if (categoryFilter) params.category_id = categoryFilter;
    if (reimbFilter) params.reimb_status = reimbFilter;
    if (selectedEntityId) {
      params.entity_id = String(selectedEntityId);
      params.include_children = "true";
    }
    api
      .getTransactions(Object.keys(params).length ? params : undefined)
      .then(setTransactions)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [search, dateFrom, dateTo, categoryFilter, reimbFilter, selectedEntityId]);

  useEffect(() => {
    fetchTransactions();
  }, [fetchTransactions]);

  async function handleCreate(tx: Omit<Transaction, "id">) {
    await api.createTransaction(tx);
    setShowForm(false);
    fetchTransactions();
  }

  async function handleUpdate(tx: Omit<Transaction, "id">) {
    if (!editingTx) return;
    await api.updateTransaction(editingTx.id, tx);
    setEditingTx(null);
    fetchTransactions();
  }

  async function handleDelete(id: number) {
    const target = transactions.find((t) => t.id === id) ?? null;
    setDeletingId(id);
    try {
      await api.deleteTransaction(id);
      setConfirmDelete(null);
      if (target) {
        setUndoTx(target);
        setTimeout(() => {
          setUndoTx((current) => (current && current.id === target.id ? null : current));
        }, 6000);
      }
      fetchTransactions();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setDeletingId(null);
    }
  }

  async function handleUndoDelete() {
    if (!undoTx) return;
    try {
      await api.createTransaction({
        date: undoTx.date,
        label: undoTx.label,
        amount: undoTx.amount,
        description: undoTx.description,
        category_id: undoTx.category_id,
        from_entity_id: undoTx.from_entity_id,
        to_entity_id: undoTx.to_entity_id,
      });
      setUndoTx(null);
      fetchTransactions();
    } catch (e: any) {
      setError(e.message);
    }
  }

  function toggleSort(col: "date" | "amount" | "label") {
    if (sortBy === col) setSortDir(sortDir === "asc" ? "desc" : "asc");
    else {
      setSortBy(col);
      setSortDir(col === "date" ? "desc" : "asc");
    }
  }

  const sortedTransactions = [...transactions].sort((a: any, b: any) => {
    const sign = sortDir === "asc" ? 1 : -1;
    if (sortBy === "amount") return (a.amount - b.amount) * sign;
    if (sortBy === "label") return String(a.label).localeCompare(String(b.label)) * sign;
    return String(a.date).localeCompare(String(b.date)) * sign || (a.id - b.id) * sign;
  });

  return (
    <div className="p-8">
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-3xl font-bold text-white" style={{ letterSpacing: "-0.02em" }}>
            Transactions
          </h1>
          {selectedEntity && (
            <p className="text-sm text-[#999] mt-1">
              Filtrées pour <span className="text-[#F2C48D] font-medium">{selectedEntity.name}</span> et sous-entités
            </p>
          )}
        </div>
        <div className="flex items-center gap-2">
          {hasExport && (
            <>
              <a
                href={`/api/export/transactions/csv${buildExportQuery()}`}
                className="flex items-center gap-2 px-4 py-2.5 text-sm font-medium text-[#B0B0B0] border border-[#333] rounded-full hover:border-[#F2C48D] hover:text-[#F2C48D] transition-colors"
                title="Télécharger CSV"
              >
                <Download size={14} /> CSV
              </a>
              <a
                href={`/api/export/transactions/json${buildExportQuery()}`}
                className="flex items-center gap-2 px-4 py-2.5 text-sm font-medium text-[#B0B0B0] border border-[#333] rounded-full hover:border-[#F2C48D] hover:text-[#F2C48D] transition-colors"
                title="Télécharger JSON"
              >
                <FileJson size={14} /> JSON
              </a>
            </>
          )}
          <button
            onClick={() => { setShowForm(true); setEditingTx(null); }}
            className="flex items-center gap-2 px-5 py-2.5 text-sm font-semibold text-black bg-[#F2C48D] rounded-full hover:bg-[#e8b87a] transition-colors"
          >
            <Plus size={15} /> Ajouter
          </button>
        </div>
      </div>

      {error && (
        <div className="mb-4 bg-[#1a0a0a] border border-[#FF5252]/30 text-[#FF5252] rounded-2xl p-4 text-sm flex items-center justify-between">
          {error}
          <button onClick={() => setError(null)} className="text-[#FF5252]/70 hover:text-[#FF5252]">
            <X size={16} />
          </button>
        </div>
      )}

      {/* Form panel */}
      {(showForm || editingTx) && (
        <div className="mb-6 bg-[#111] border border-[#222] rounded-2xl p-6">
          <h2 className="text-base font-semibold text-white mb-5">
            {editingTx ? "Modifier la transaction" : "Nouvelle transaction"}
          </h2>
          <TransactionForm
            initial={editingTx ?? undefined}
            onSave={editingTx ? handleUpdate : handleCreate}
            onCancel={() => { setShowForm(false); setEditingTx(null); }}
          />
        </div>
      )}

      {/* Filters */}
      <div className="mb-5 flex flex-wrap gap-3">
        <div className="flex items-center gap-2 flex-1 min-w-48 bg-[#111] border border-[#222] rounded-xl px-3 py-2.5 focus-within:border-[#F2C48D] transition-colors">
          <Search size={15} className="text-[#666]" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Rechercher..."
            className="flex-1 text-sm bg-transparent focus:outline-none text-white placeholder-[#666]"
          />
        </div>
        <div className="flex items-center gap-2">
          <label className="text-sm text-[#666]">Du</label>
          <input
            type="date"
            value={dateFrom}
            onChange={(e) => setDateFrom(e.target.value)}
            className="bg-[#111] border border-[#222] rounded-xl px-3 py-2.5 text-sm text-white focus:outline-none focus:border-[#F2C48D] transition-colors [color-scheme:dark]"
          />
        </div>
        <div className="flex items-center gap-2">
          <label className="text-sm text-[#666]">Au</label>
          <input
            type="date"
            value={dateTo}
            onChange={(e) => setDateTo(e.target.value)}
            className="bg-[#111] border border-[#222] rounded-xl px-3 py-2.5 text-sm text-white focus:outline-none focus:border-[#F2C48D] transition-colors [color-scheme:dark]"
          />
        </div>
        <select
          value={categoryFilter}
          onChange={(e) => setCategoryFilter(e.target.value)}
          className="bg-[#111] border border-[#222] rounded-xl px-3 py-2.5 text-sm text-white focus:outline-none focus:border-[#F2C48D] transition-colors"
          title="Filtrer par catégorie"
        >
          <option value="">Toutes catégories</option>
          {categories.map((c) => (
            <option key={c.id} value={c.id}>{c.name}</option>
          ))}
        </select>
        <select
          value={reimbFilter}
          onChange={(e) => setReimbFilter(e.target.value)}
          className="bg-[#111] border border-[#222] rounded-xl px-3 py-2.5 text-sm text-white focus:outline-none focus:border-[#F2C48D] transition-colors"
        >
          <option value="">Tous remboursements</option>
          <option value="pending">En attente</option>
          <option value="reimbursed">Remboursés</option>
          <option value="none">Sans rembo</option>
        </select>
        {(search || dateFrom || dateTo || categoryFilter || reimbFilter) && (
          <button
            onClick={() => { setSearch(""); setDateFrom(""); setDateTo(""); setCategoryFilter(""); setReimbFilter(""); }}
            className="text-sm text-[#666] hover:text-white flex items-center gap-1 transition-colors"
          >
            <X size={14} /> Effacer
          </button>
        )}
      </div>

      {/* Table */}
      <div className="bg-[#111] border border-[#222] rounded-2xl overflow-hidden">
        {loading ? (
          <div className="flex items-center justify-center py-12">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-[#F2C48D]" />
          </div>
        ) : transactions.length === 0 ? (
          <div className="text-center py-12 text-[#666] text-sm">
            Aucune transaction trouvée.
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[#1a1a1a]">
                <th className="px-3 py-3.5 text-left text-xs font-medium text-[#666] uppercase tracking-wider w-12">#</th>
                <th
                  onClick={() => toggleSort("date")}
                  className="px-4 py-3.5 text-left text-xs font-medium text-[#666] uppercase tracking-wider cursor-pointer select-none hover:text-white"
                >
                  Date {sortBy === "date" ? (sortDir === "asc" ? "↑" : "↓") : ""}
                </th>
                <th
                  onClick={() => toggleSort("label")}
                  className="px-4 py-3.5 text-left text-xs font-medium text-[#666] uppercase tracking-wider cursor-pointer select-none hover:text-white"
                >
                  Libellé {sortBy === "label" ? (sortDir === "asc" ? "↑" : "↓") : ""}
                </th>
                <th className="px-4 py-3.5 text-left text-xs font-medium text-[#666] uppercase tracking-wider">Flux</th>
                <th className="px-4 py-3.5 text-left text-xs font-medium text-[#666] uppercase tracking-wider">Catégorie</th>
                <th className="px-4 py-3.5 text-left text-xs font-medium text-[#666] uppercase tracking-wider">Rembo</th>
                <th
                  onClick={() => toggleSort("amount")}
                  className="px-4 py-3.5 text-right text-xs font-medium text-[#666] uppercase tracking-wider cursor-pointer select-none hover:text-white"
                >
                  Montant {sortBy === "amount" ? (sortDir === "asc" ? "↑" : "↓") : ""}
                </th>
                <th className="px-4 py-3.5 text-right text-xs font-medium text-[#666] uppercase tracking-wider">Actions</th>
              </tr>
            </thead>
            <tbody>
              {sortedTransactions.map((tx: any, idx) => (
                <tr
                  key={tx.id}
                  className={`hover:bg-[#1a1a1a] transition-colors ${idx > 0 ? "border-t border-[#1a1a1a]" : ""}`}
                >
                  <td className="px-3 py-3.5 text-[#555] text-xs font-mono">#{tx.id}</td>
                  <td className="px-4 py-3.5 text-[#B0B0B0] whitespace-nowrap">{tx.date}</td>
                  <td className="px-4 py-3.5 font-medium text-white">
                    <div className="flex items-center gap-2">
                      <span>{tx.label}</span>
                    </div>
                    {tx.description && (
                      <p className="text-xs text-[#666] font-normal mt-0.5 truncate max-w-xs">{tx.description}</p>
                    )}
                  </td>
                  <td className="px-4 py-3.5">
                    <div className="flex items-center gap-1.5 text-xs">
                      <span
                        className="px-2 py-0.5 rounded-full truncate max-w-[100px]"
                        style={{
                          backgroundColor: (tx.from_entity_color || "#6B7280") + "20",
                          color: tx.from_entity_color || "#999",
                        }}
                        title={tx.from_entity_name}
                      >
                        {tx.from_entity_name || "—"}
                      </span>
                      <ArrowRight size={12} className="text-[#555] shrink-0" />
                      <span
                        className="px-2 py-0.5 rounded-full truncate max-w-[100px]"
                        style={{
                          backgroundColor: (tx.to_entity_color || "#6B7280") + "20",
                          color: tx.to_entity_color || "#999",
                        }}
                        title={tx.to_entity_name}
                      >
                        {tx.to_entity_name || "—"}
                      </span>
                    </div>
                  </td>
                  <td className="px-4 py-3.5">
                    {tx.category_name ? (
                      <span
                        className="text-xs px-2 py-0.5 rounded-full"
                        style={{
                          backgroundColor: (tx.category_color || "#6B7280") + "20",
                          color: tx.category_color || "#999",
                        }}
                      >
                        {tx.category_name}
                      </span>
                    ) : (
                      <span className="text-[#444]">—</span>
                    )}
                  </td>
                  <td className="px-4 py-3.5">
                    {tx.reimb_person_name ? (
                      <span
                        className={`inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full border ${
                          tx.reimb_status === "reimbursed"
                            ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/30"
                            : "bg-amber-500/10 text-amber-400 border-amber-500/30"
                        }`}
                        title={`Avance de ${tx.reimb_person_name}${tx.reimb_status === "reimbursed" ? " (remboursé)" : " (en attente)"}`}
                      >
                        {tx.reimb_status === "reimbursed" ? <Check size={12} /> : <Hourglass size={12} />}
                        {tx.reimb_person_name}
                      </span>
                    ) : (
                      <span className="text-xs text-[#444]">—</span>
                    )}
                  </td>
                  <td
                    className={`px-4 py-3.5 text-right font-semibold whitespace-nowrap ${
                      tx.amount >= 0 ? "text-[#00C853]" : "text-[#FF5252]"
                    }`}
                  >
                    {eurFormatter.format(tx.amount)}
                  </td>
                  <td className="px-4 py-3.5 text-right">
                    {confirmDelete === tx.id ? (
                      <span className="inline-flex items-center gap-2">
                        <span className="text-xs text-[#666]">Supprimer ?</span>
                        <button
                          onClick={() => handleDelete(tx.id)}
                          disabled={deletingId === tx.id}
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
                        {(hasAttachments || hasAnnotations) && (
                          <button
                            onClick={() => setDetailTx(tx)}
                            className="p-1.5 text-[#666] hover:text-[#F2C48D] rounded-lg hover:bg-[#222] transition-colors"
                            title="Détails (notes, pièces jointes)"
                          >
                            <Eye size={14} strokeWidth={1.5} />
                          </button>
                        )}
                        <button
                          onClick={() => { setEditingTx(tx); setShowForm(false); }}
                          className="p-1.5 text-[#666] hover:text-white rounded-lg hover:bg-[#222] transition-colors"
                          title="Modifier"
                        >
                          <Pencil size={14} strokeWidth={1.5} />
                        </button>
                        <button
                          onClick={() => setConfirmDelete(tx.id)}
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

      {undoTx && (
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 flex items-center gap-4 bg-[#111] border border-[#333] rounded-full px-5 py-3 shadow-xl">
          <span className="text-sm text-white">Transaction supprimée</span>
          <button
            onClick={handleUndoDelete}
            className="text-sm font-semibold text-[#F2C48D] hover:underline"
          >
            Annuler
          </button>
          <button
            onClick={() => setUndoTx(null)}
            className="text-[#666] hover:text-white"
            aria-label="Fermer"
          >
            <X size={14} />
          </button>
        </div>
      )}

      {detailTx && (
        <div className="fixed inset-0 bg-black/60 flex justify-end z-50" onClick={() => setDetailTx(null)}>
          <div
            className="w-full max-w-md bg-[#0a0a0a] border-l border-[#222] h-full overflow-y-auto p-6"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-start justify-between mb-6">
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className="text-xs font-mono text-[#555] bg-[#1a1a1a] px-1.5 py-0.5 rounded">#{detailTx.id}</span>
                  <h2 className="text-xl font-bold text-white break-words">{detailTx.label}</h2>
                </div>
                <div className="text-sm text-[#666] mt-1">{detailTx.date}</div>
                <div
                  className={`mt-3 text-2xl font-bold ${
                    detailTx.amount >= 0 ? "text-[#00C853]" : "text-[#FF5252]"
                  }`}
                >
                  {eurFormatter.format(detailTx.amount)}
                </div>
                {(detailTx as any).reimb_person_name && (
                  <div className={`mt-2 inline-flex items-center gap-1.5 text-xs px-2 py-1 rounded-lg border ${
                    (detailTx as any).reimb_status === "reimbursed"
                      ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/30"
                      : "bg-amber-500/10 text-amber-400 border-amber-500/30"
                  }`}>
                    ↩ Avance de {(detailTx as any).reimb_person_name}
                    {(detailTx as any).reimb_status === "reimbursed" ? " — remboursé" : " — en attente"}
                  </div>
                )}
              </div>
              <button
                onClick={() => setDetailTx(null)}
                className="text-[#666] hover:text-white p-1 flex-shrink-0"
              >
                <X size={18} />
              </button>
            </div>

            {(detailTx as any).description && (
              <div className="mb-4 bg-[#111] border border-[#222] rounded-xl p-3 text-sm text-[#B0B0B0]">
                {(detailTx as any).description}
              </div>
            )}

            <div className="space-y-4">
              {hasAttachments && <AttachmentsSection txId={detailTx.id} />}
              {hasAnnotations && <AnnotationsSection txId={detailTx.id} />}
              {!hasAttachments && !hasAnnotations && (
                <div className="text-sm text-[#666]">
                  Active les modules « Pièces jointes » et « Annotations » dans Paramètres
                  pour enrichir le détail des transactions.
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
