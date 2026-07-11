import { useState } from "react";
import { useFiscalYear, FiscalYear } from "../../../core/FiscalYearContext";
import { useAuth } from "../../../core/AuthContext";
import { api } from "../../../api";
import FiscalYearWizard from "../FiscalYearWizard";
import { Plus, Trash2, Pencil } from "lucide-react";
import { formatDate } from "../../../utils/format";

interface EditForm {
  name: string;
  start_date: string;
  president_name: string;
  tresorier_name: string;
}

export default function FiscalYearsTab() {
  const { isAdmin } = useAuth();
  const { years, reload } = useFiscalYear();
  const [showWizard, setShowWizard] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState<number | null>(null);
  const [closingId, setClosingId] = useState<number | null>(null);
  const [closeDate, setCloseDate] = useState(new Date().toISOString().slice(0, 10));
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editForm, setEditForm] = useState<EditForm>({ name: "", start_date: "", president_name: "", tresorier_name: "" });
  const [editSubmitting, setEditSubmitting] = useState(false);
  const [editError, setEditError] = useState<string | null>(null);

  const hasOpenMandate = years.some((y) => y.end_date === null);
  const previousYearId = years.length > 0 ? years[0].id : null;

  async function doClose(y: FiscalYear) {
    setSubmitting(true);
    setError(null);
    try {
      await api.closeFiscalYear(y.id, closeDate);
      setClosingId(null);
      await reload();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setSubmitting(false);
    }
  }

  async function doDelete(id: number) {
    setError(null);
    try {
      await api.deleteFiscalYear(id);
      setConfirmDelete(null);
      await reload();
    } catch (e: any) {
      setError(e.message);
    }
  }

  function startEdit(y: FiscalYear) {
    setEditingId(y.id);
    setEditError(null);
    setEditForm({
      name: y.name,
      start_date: y.start_date,
      president_name: y.president_name || "",
      tresorier_name: y.tresorier_name || "",
    });
  }

  async function doSaveEdit(id: number) {
    if (!editForm.name.trim() || !editForm.start_date) {
      setEditError("Le nom et la date de début sont obligatoires.");
      return;
    }
    setEditSubmitting(true);
    setEditError(null);
    try {
      await api.updateFiscalYear(id, {
        name: editForm.name.trim(),
        start_date: editForm.start_date,
        president_name: editForm.president_name.trim(),
        tresorier_name: editForm.tresorier_name.trim(),
      });
      setEditingId(null);
      await reload();
    } catch (e: any) {
      setEditError(e.message);
    } finally {
      setEditSubmitting(false);
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-[#B0B0B0]">
          {years.length} exercice(s).
          {hasOpenMandate
            ? " Un exercice est en cours : clos-le avant d'en ouvrir un nouveau."
            : " Aucun exercice ouvert."}
        </p>
        {isAdmin && (
          <button
            onClick={() => setShowWizard(true)}
            disabled={hasOpenMandate}
            className="flex items-center gap-2 px-5 py-2.5 text-sm font-semibold text-black bg-[#F2C48D] rounded-full hover:bg-[#e8b87a] disabled:opacity-40 disabled:cursor-not-allowed"
          >
            <Plus size={14} /> Nouvel exercice
          </button>
        )}
      </div>

      {error && (
        <div className="bg-[#1a0a0a] border border-[#FF5252]/30 text-[#FF5252] rounded-xl p-3 text-sm">
          {error}
        </div>
      )}

      <div className="bg-[#111] border border-[#222] rounded-2xl overflow-hidden">
        {years.length === 0 ? (
          <div className="py-8 text-center text-sm text-[#666]">
            Aucun exercice. Crée le premier pour activer le suivi budgétaire.
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[#1a1a1a]">
                <th className="px-4 py-3 text-left text-xs font-medium text-[#666] uppercase">Nom</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-[#666] uppercase">Début</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-[#666] uppercase">Fin</th>
                <th className="px-4 py-3 text-right text-xs font-medium text-[#666] uppercase">Actions</th>
              </tr>
            </thead>
            <tbody>
              {years.map((y, idx) => (
                editingId === y.id ? (
                  <tr key={y.id} className={idx > 0 ? "border-t border-[#1a1a1a]" : ""}>
                    <td colSpan={4} className="px-4 py-3">
                      <div className="flex flex-wrap items-end gap-3">
                        <div>
                          <label className="block text-xs text-[#666] mb-1">Nom</label>
                          <input
                            value={editForm.name}
                            onChange={(e) => setEditForm({ ...editForm, name: e.target.value })}
                            className="bg-[#0a0a0a] border border-[#333] rounded-lg px-2 py-1.5 text-sm text-white"
                          />
                        </div>
                        <div>
                          <label className="block text-xs text-[#666] mb-1">Début</label>
                          <input
                            type="date"
                            value={editForm.start_date}
                            onChange={(e) => setEditForm({ ...editForm, start_date: e.target.value })}
                            className="bg-[#0a0a0a] border border-[#333] rounded-lg px-2 py-1.5 text-sm text-white [color-scheme:dark]"
                          />
                        </div>
                        <div>
                          <label className="block text-xs text-[#666] mb-1">Président</label>
                          <input
                            value={editForm.president_name}
                            onChange={(e) => setEditForm({ ...editForm, president_name: e.target.value })}
                            className="bg-[#0a0a0a] border border-[#333] rounded-lg px-2 py-1.5 text-sm text-white"
                          />
                        </div>
                        <div>
                          <label className="block text-xs text-[#666] mb-1">Trésorier</label>
                          <input
                            value={editForm.tresorier_name}
                            onChange={(e) => setEditForm({ ...editForm, tresorier_name: e.target.value })}
                            className="bg-[#0a0a0a] border border-[#333] rounded-lg px-2 py-1.5 text-sm text-white"
                          />
                        </div>
                        <div className="flex items-center gap-2 text-sm">
                          <button
                            onClick={() => doSaveEdit(y.id)}
                            disabled={editSubmitting}
                            className="text-[#F2C48D] font-semibold disabled:opacity-50"
                          >
                            Enregistrer
                          </button>
                          <button onClick={() => setEditingId(null)} className="text-[#666] hover:text-white">
                            Annuler
                          </button>
                        </div>
                      </div>
                      {editError && <p className="mt-2 text-xs text-[#FF5252]">{editError}</p>}
                    </td>
                  </tr>
                ) : (
                <tr key={y.id} className={idx > 0 ? "border-t border-[#1a1a1a]" : ""}>
                  <td className="px-4 py-3 text-white font-medium">
                    {y.name}
                    {y.end_date === null && (
                      <span className="ml-2 text-xs text-[#F2C48D] border border-[#F2C48D]/30 bg-[#F2C48D]/5 px-2 py-0.5 rounded-full">
                        en cours
                      </span>
                    )}
                    {(y.president_name || y.tresorier_name) && (
                      <div className="text-xs text-[#666] font-normal mt-0.5">
                        {y.president_name && <>Prés. {y.president_name}</>}
                        {y.president_name && y.tresorier_name && " · "}
                        {y.tresorier_name && <>Trés. {y.tresorier_name}</>}
                      </div>
                    )}
                  </td>
                  <td className="px-4 py-3 text-[#B0B0B0]">{formatDate(y.start_date)}</td>
                  <td className="px-4 py-3 text-[#B0B0B0]">{formatDate(y.end_date)}</td>
                  <td className="px-4 py-3 text-right">
                    {isAdmin && closingId !== y.id && confirmDelete !== y.id && (
                      <button
                        onClick={() => startEdit(y)}
                        className="text-xs text-[#B0B0B0] hover:text-white mr-3 border border-[#333] px-2.5 py-1 rounded-full inline-flex items-center gap-1"
                      >
                        <Pencil size={12} /> Modifier
                      </button>
                    )}
                    {isAdmin && y.end_date === null && closingId !== y.id && (
                      <button
                        onClick={() => { setClosingId(y.id); setCloseDate(new Date().toISOString().slice(0, 10)); }}
                        className="text-xs text-[#B0B0B0] hover:text-white mr-3 border border-[#333] px-2.5 py-1 rounded-full"
                      >
                        Clore
                      </button>
                    )}
                    {isAdmin && closingId === y.id && (
                      <span className="inline-flex items-center gap-2 text-xs">
                        <input
                          type="date"
                          value={closeDate}
                          onChange={(e) => setCloseDate(e.target.value)}
                          className="bg-[#0a0a0a] border border-[#333] rounded-lg px-2 py-1 text-white [color-scheme:dark]"
                        />
                        <button
                          onClick={() => doClose(y)}
                          disabled={submitting}
                          className="text-[#F2C48D] font-semibold disabled:opacity-50"
                        >
                          Confirmer
                        </button>
                        <button onClick={() => setClosingId(null)} className="text-[#666]">
                          Annuler
                        </button>
                      </span>
                    )}
                    {isAdmin && (
                      confirmDelete === y.id ? (
                        <span className="inline-flex items-center gap-2 text-xs">
                          <span className="text-[#666]">Supprimer ?</span>
                          <button onClick={() => doDelete(y.id)} className="text-[#FF5252] font-semibold">Oui</button>
                          <button onClick={() => setConfirmDelete(null)} className="text-[#666]">Non</button>
                        </span>
                      ) : (
                        closingId !== y.id && (
                          <button
                            onClick={() => setConfirmDelete(y.id)}
                            className="p-1.5 text-[#666] hover:text-[#FF5252]"
                            title="Supprimer"
                          >
                            <Trash2 size={14} strokeWidth={1.5} />
                          </button>
                        )
                      )
                    )}
                  </td>
                </tr>
                )
              ))}
            </tbody>
          </table>
        )}
      </div>

      {showWizard && (
        <FiscalYearWizard
          previousYearId={previousYearId}
          onClose={() => setShowWizard(false)}
          onCreated={reload}
        />
      )}
    </div>
  );
}
