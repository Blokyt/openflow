import { useState } from "react";
import { useFiscalYear, FiscalYear } from "../../../core/FiscalYearContext";
import { api } from "../../../api";
import FiscalYearWizard from "../FiscalYearWizard";
import { Plus, Trash2, CheckCircle } from "lucide-react";

export default function FiscalYearsTab() {
  const { years, reload } = useFiscalYear();
  const [showWizard, setShowWizard] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState<number | null>(null);
  const previousYearId = years.length > 0 ? years[0].id : null;

  async function setActive(y: FiscalYear) {
    await api.updateFiscalYear(y.id, { is_current: true });
    await reload();
  }

  async function doDelete(id: number) {
    await api.deleteFiscalYear(id);
    setConfirmDelete(null);
    await reload();
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-[#B0B0B0]">
          {years.length} exercice(s). Un seul peut être actif à la fois.
        </p>
        <button
          onClick={() => setShowWizard(true)}
          className="flex items-center gap-2 px-5 py-2.5 text-sm font-semibold text-black bg-[#F2C48D] rounded-full hover:bg-[#e8b87a]"
        >
          <Plus size={14} /> Nouvel exercice
        </button>
      </div>

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
                <tr key={y.id} className={idx > 0 ? "border-t border-[#1a1a1a]" : ""}>
                  <td className="px-4 py-3 text-white font-medium">
                    {y.name}
                    {y.is_current === 1 && (
                      <span className="ml-2 text-xs text-[#F2C48D] inline-flex items-center gap-1">
                        <CheckCircle size={11} /> actif
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-[#B0B0B0]">{y.start_date}</td>
                  <td className="px-4 py-3 text-[#B0B0B0]">{y.end_date}</td>
                  <td className="px-4 py-3 text-right">
                    {y.is_current !== 1 && (
                      <button
                        onClick={() => setActive(y)}
                        className="text-xs text-[#F2C48D] hover:underline mr-3"
                      >
                        Définir actif
                      </button>
                    )}
                    {confirmDelete === y.id ? (
                      <span className="inline-flex items-center gap-2 text-xs">
                        <span className="text-[#666]">Supprimer ?</span>
                        <button onClick={() => doDelete(y.id)} className="text-[#FF5252] font-semibold">Oui</button>
                        <button onClick={() => setConfirmDelete(null)} className="text-[#666]">Non</button>
                      </span>
                    ) : (
                      <button
                        onClick={() => setConfirmDelete(y.id)}
                        className="p-1.5 text-[#666] hover:text-[#FF5252]"
                        title="Supprimer"
                      >
                        <Trash2 size={14} strokeWidth={1.5} />
                      </button>
                    )}
                  </td>
                </tr>
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
