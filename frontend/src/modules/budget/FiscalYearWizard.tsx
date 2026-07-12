import { useState } from "react";
import { api } from "../../api";
import { X, ArrowRight } from "lucide-react";

interface WizardProps {
  previousYearId: number | null;
  onClose: () => void;
  onCreated: () => void;
}

export default function FiscalYearWizard({ previousYearId, onClose, onCreated }: WizardProps) {
  const [step, setStep] = useState<1 | 2>(1);
  const today = new Date();
  const defaultStart = `${today.getFullYear()}-09-01`;

  const [name, setName] = useState(`${today.getFullYear()}-${today.getFullYear() + 1}`);
  const [startDate, setStartDate] = useState(defaultStart);
  const [presidentName, setPresidentName] = useState("");
  const [tresorierName, setTresorierName] = useState("");

  const [createdFyId, setCreatedFyId] = useState<number | null>(null);
  const [initMode, setInitMode] = useState<"empty" | "copy" | "realized">(
    previousYearId !== null ? "realized" : "empty",
  );
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function goToStep2() {
    setError(null);
    setSubmitting(true);
    try {
      const fy = await api.createFiscalYear({
        name,
        start_date: startDate,
        president_name: presidentName,
        tresorier_name: tresorierName,
      });
      setCreatedFyId(fy.id);
      setStep(2);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setSubmitting(false);
    }
  }

  async function finish() {
    if (!createdFyId) return;
    setError(null);
    setSubmitting(true);
    try {
      if (previousYearId !== null && initMode === "copy") {
        const prevAllocs = await api.listAllocations(previousYearId);
        await Promise.all(
          prevAllocs.map((a) =>
            api.createAllocation(createdFyId, {
              entity_id: a.entity_id,
              category_id: a.category_id,
              direction: a.direction,
              amount: a.amount,
              notes: a.notes,
              // Copie d'un exercice précédent = placeholder hérité (gris tant que non modifié).
              origin: "seeded",
            })
          )
        );
      } else if (previousYearId !== null && initMode === "realized") {
        await api.seedBudgetFromRealized(createdFyId);
      }
      onCreated();
      onClose();
    } catch (e: any) {
      setError(e.message);
      setSubmitting(false);
    }
  }

  return (
    <div
      className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4"
      onClick={step === 1 && !createdFyId ? onClose : undefined}
    >
      <div
        className="bg-[#0a0a0a] border border-[#222] rounded-2xl max-w-lg w-full"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between p-5 border-b border-[#222]">
          <h2 className="text-base font-semibold text-white">
            Nouvel exercice — étape {step}/2
          </h2>
          <button onClick={onClose} className="text-[#8a8a8a] hover:text-white">
            <X size={18} />
          </button>
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
              <div>
                <label className="block text-sm font-medium text-[#B0B0B0] mb-1.5">Date de début</label>
                <input
                  type="date"
                  value={startDate}
                  onChange={(e) => setStartDate(e.target.value)}
                  className="w-full bg-[#0a0a0a] border border-[#222] rounded-xl px-3 py-2.5 text-sm text-white [color-scheme:dark]"
                />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-sm font-medium text-[#B0B0B0] mb-1.5">
                    Président <span className="text-[#555]">(optionnel)</span>
                  </label>
                  <input
                    value={presidentName}
                    onChange={(e) => setPresidentName(e.target.value)}
                    placeholder="Nom du président"
                    className="w-full bg-[#0a0a0a] border border-[#222] rounded-xl px-3 py-2.5 text-sm text-white placeholder:text-[#444]"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-[#B0B0B0] mb-1.5">
                    Trésorier <span className="text-[#555]">(optionnel)</span>
                  </label>
                  <input
                    value={tresorierName}
                    onChange={(e) => setTresorierName(e.target.value)}
                    placeholder="Nom du trésorier"
                    className="w-full bg-[#0a0a0a] border border-[#222] rounded-xl px-3 py-2.5 text-sm text-white placeholder:text-[#444]"
                  />
                </div>
              </div>
              <p className="text-xs text-[#555]">
                L'exercice restera ouvert jusqu'à ce que tu le closes manuellement.
              </p>
            </div>
          )}

          {step === 2 && (
            <div className="space-y-3">
              {previousYearId !== null ? (
                <fieldset className="space-y-2">
                  <legend className="text-sm font-medium text-[#B0B0B0] mb-1">Initialiser le budget</legend>
                  {([
                    { v: "realized", label: "Pré-remplir avec le réel de l'an dernier", hint: "À partir des transactions réelles, par catégorie. Recommandé." },
                    { v: "copy", label: "Copier le budget prévisionnel de l'an dernier", hint: "Reprend les allocations saisies l'an dernier." },
                    { v: "empty", label: "Partir d'un budget vide", hint: "Tout saisir à la main." },
                  ] as const).map((opt) => (
                    <label key={opt.v} className="flex items-start gap-2 text-sm text-[#B0B0B0] cursor-pointer">
                      <input
                        type="radio"
                        name="initMode"
                        className="mt-1"
                        checked={initMode === opt.v}
                        onChange={() => setInitMode(opt.v)}
                      />
                      <span>
                        <span className="text-white">{opt.label}</span>
                        <span className="block text-xs text-[#8a8a8a]">{opt.hint}</span>
                      </span>
                    </label>
                  ))}
                </fieldset>
              ) : (
                <p className="text-sm text-[#8a8a8a]">
                  Aucun exercice précédent : tu partiras d'un budget vide.
                </p>
              )}
              <p className="text-sm text-[#8a8a8a]">
                Tu pourras affiner les allocations à tout moment depuis l'onglet Catégories.
              </p>
            </div>
          )}
        </div>

        <div className="flex items-center justify-end gap-3 p-5 border-t border-[#222]">
          {step === 1 && (
            <button
              onClick={goToStep2}
              disabled={submitting || !name.trim() || !startDate}
              className="px-5 py-2.5 text-sm font-semibold text-black bg-[#F2C48D] rounded-full hover:bg-[#e8b87a] disabled:opacity-50 inline-flex items-center gap-1"
            >
              Suivant <ArrowRight size={14} />
            </button>
          )}
          {step === 2 && (
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
