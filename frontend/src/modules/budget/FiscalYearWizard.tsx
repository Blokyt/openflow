import { useState } from "react";
import { api } from "../../api";
import { X, ArrowRight } from "lucide-react";

interface WizardProps {
  previousYearId: number | null;
  onClose: () => void;
  onCreated: () => void;
}

export default function FiscalYearWizard({ previousYearId, onClose, onCreated }: WizardProps) {
  const [step, setStep] = useState<1 | 2 | 3>(1);
  const today = new Date();
  const defaultStart = `${today.getFullYear()}-09-01`;
  const defaultEnd = `${today.getFullYear() + 1}-08-31`;

  const [name, setName] = useState(`${today.getFullYear()}-${today.getFullYear() + 1}`);
  const [startDate, setStartDate] = useState(defaultStart);
  const [endDate, setEndDate] = useState(defaultEnd);
  const [isCurrent, setIsCurrent] = useState(true);

  const [suggestions, setSuggestions] = useState<any[]>([]);
  const [openings, setOpenings] = useState<Record<number, { amount: string; source: string }>>({});
  const [createdFyId, setCreatedFyId] = useState<number | null>(null);

  const [copyAllocations, setCopyAllocations] = useState(previousYearId !== null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function goToStep2() {
    setError(null);
    setSubmitting(true);
    try {
      const fy = await api.createFiscalYear({
        name, start_date: startDate, end_date: endDate, is_current: isCurrent,
      });
      setCreatedFyId(fy.id);
      const sugg = await api.getSuggestedOpening(fy.id);
      setSuggestions(sugg);
      setOpenings(Object.fromEntries(sugg.map((s) => [s.entity_id, { amount: "", source: "" }])));
      setStep(2);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setSubmitting(false);
    }
  }

  async function goToStep3() {
    setError(null);
    setSubmitting(true);
    if (!createdFyId) return;
    try {
      const entries = suggestions.map((s) => ({
        entity_id: s.entity_id,
        amount: parseFloat(openings[s.entity_id]?.amount || String(s.suggested_amount)),
        source: openings[s.entity_id]?.source || "",
      }));
      await api.upsertOpeningBalances(createdFyId, entries);
      setStep(3);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setSubmitting(false);
    }
  }

  async function finish() {
    setError(null);
    setSubmitting(true);
    if (!createdFyId) return;
    try {
      if (copyAllocations && previousYearId !== null) {
        const prevAllocs = await api.listAllocations(previousYearId);
        for (const a of prevAllocs) {
          await api.createAllocation(createdFyId, {
            entity_id: a.entity_id,
            category_id: a.category_id,
            amount: a.amount,
            notes: a.notes,
          });
        }
      }
      onCreated();
      onClose();
    } catch (e: any) {
      setError(e.message);
      setSubmitting(false);
    }
  }

  return (
    <div className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div
        className="bg-[#0a0a0a] border border-[#222] rounded-2xl max-w-2xl w-full max-h-[90vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between p-5 border-b border-[#222]">
          <h2 className="text-base font-semibold text-white">
            Nouvel exercice — étape {step}/3
          </h2>
          <button onClick={onClose} className="text-[#666] hover:text-white"><X size={18} /></button>
        </div>

        <div className="p-5 space-y-4">
          {error && (
            <div className="bg-[#1a0a0a] border border-[#FF5252]/30 text-[#FF5252] rounded-xl p-3 text-sm">
              {error}
            </div>
          )}

          {step === 1 && (
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-[#B0B0B0] mb-1.5">Nom</label>
                <input
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  className="w-full bg-[#0a0a0a] border border-[#222] rounded-xl px-3 py-2.5 text-sm text-white"
                />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-[#B0B0B0] mb-1.5">Début</label>
                  <input
                    type="date"
                    value={startDate}
                    onChange={(e) => setStartDate(e.target.value)}
                    className="w-full bg-[#0a0a0a] border border-[#222] rounded-xl px-3 py-2.5 text-sm text-white [color-scheme:dark]"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-[#B0B0B0] mb-1.5">Fin</label>
                  <input
                    type="date"
                    value={endDate}
                    onChange={(e) => setEndDate(e.target.value)}
                    className="w-full bg-[#0a0a0a] border border-[#222] rounded-xl px-3 py-2.5 text-sm text-white [color-scheme:dark]"
                  />
                </div>
              </div>
              <label className="flex items-center gap-2 text-sm text-[#B0B0B0]">
                <input type="checkbox" checked={isCurrent} onChange={(e) => setIsCurrent(e.target.checked)} />
                Définir comme exercice actif
              </label>
            </div>
          )}

          {step === 2 && (
            <div className="space-y-2">
              <p className="text-sm text-[#B0B0B0]">
                Saisis le vrai solde bancaire de chaque entité au {startDate}.
                Utilise les valeurs suggérées comme point de départ ou saisis tes relevés réels.
              </p>
              <div className="space-y-2">
                {suggestions.map((s) => (
                  <div key={s.entity_id} className="flex items-center gap-3 bg-[#111] border border-[#222] rounded-xl p-3">
                    <div className="flex-1">
                      <p className="text-sm text-white font-medium">{s.entity_name}</p>
                      <p className="text-xs text-[#666]">Suggéré : {s.suggested_amount.toFixed(2)} €</p>
                    </div>
                    <input
                      type="number"
                      step="0.01"
                      placeholder={String(s.suggested_amount)}
                      value={openings[s.entity_id]?.amount ?? ""}
                      onChange={(e) =>
                        setOpenings((p) => ({
                          ...p,
                          [s.entity_id]: { ...(p[s.entity_id] ?? { amount: "", source: "" }), amount: e.target.value },
                        }))
                      }
                      className="w-28 bg-[#0a0a0a] border border-[#333] rounded-lg px-2 py-1.5 text-sm text-white text-right"
                    />
                    <input
                      type="text"
                      placeholder="source (optionnel)"
                      value={openings[s.entity_id]?.source ?? ""}
                      onChange={(e) =>
                        setOpenings((p) => ({
                          ...p,
                          [s.entity_id]: { ...(p[s.entity_id] ?? { amount: "", source: "" }), source: e.target.value },
                        }))
                      }
                      className="w-40 bg-[#0a0a0a] border border-[#333] rounded-lg px-2 py-1.5 text-sm text-white"
                    />
                  </div>
                ))}
              </div>
            </div>
          )}

          {step === 3 && (
            <div className="space-y-3">
              {previousYearId !== null && (
                <label className="flex items-center gap-2 text-sm text-[#B0B0B0]">
                  <input type="checkbox" checked={copyAllocations} onChange={(e) => setCopyAllocations(e.target.checked)} />
                  Copier les allocations de l'exercice précédent
                </label>
              )}
              <p className="text-sm text-[#666]">
                L'exercice est prêt à être créé. Tu pourras affiner allocations et soldes à tout moment.
              </p>
            </div>
          )}
        </div>

        <div className="flex items-center justify-end gap-3 p-5 border-t border-[#222]">
          {step > 1 && (
            <button
              onClick={() => setStep((s) => (s - 1) as any)}
              className="px-4 py-2 text-sm text-[#B0B0B0] hover:text-white"
            >
              Retour
            </button>
          )}
          {step === 1 && (
            <button
              onClick={goToStep2}
              disabled={submitting || !name || !startDate || !endDate}
              className="px-5 py-2.5 text-sm font-semibold text-black bg-[#F2C48D] rounded-full hover:bg-[#e8b87a] disabled:opacity-50 inline-flex items-center gap-1"
            >
              Suivant <ArrowRight size={14} />
            </button>
          )}
          {step === 2 && (
            <button
              onClick={goToStep3}
              disabled={submitting}
              className="px-5 py-2.5 text-sm font-semibold text-black bg-[#F2C48D] rounded-full hover:bg-[#e8b87a] disabled:opacity-50"
            >
              Suivant
            </button>
          )}
          {step === 3 && (
            <button
              onClick={finish}
              disabled={submitting}
              className="px-5 py-2.5 text-sm font-semibold text-black bg-[#F2C48D] rounded-full hover:bg-[#e8b87a] disabled:opacity-50"
            >
              Créer l'exercice
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
