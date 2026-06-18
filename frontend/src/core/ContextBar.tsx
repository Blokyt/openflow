import { X } from "lucide-react";
import { useEntity } from "./EntityContext";
import { useFiscalYear } from "./FiscalYearContext";

/**
 * Barre de contexte globale persistante affichée sous le header.
 * Affiche l'entité et l'exercice sélectionnés, avec un bouton
 * de réinitialisation pour chacun.
 */
export default function ContextBar() {
  const { selectedEntity, setSelectedEntityId } = useEntity();
  const { selectedYear, setSelectedYearId } = useFiscalYear();

  const hasAny = selectedEntity !== null || selectedYear !== null;
  if (!hasAny) return null;

  return (
    <div className="flex flex-wrap items-center gap-2 px-6 py-2 bg-[#0a0a0a] border-b border-[#1a1a1a] text-xs">
      {selectedEntity && (
        <span className="flex items-center gap-1.5 bg-[#111] border border-[#222] rounded-full px-3 py-1 text-[#B0B0B0]">
          <span className="text-[#666]">Entité :</span>
          <span className="text-white font-medium">{selectedEntity.name}</span>
          <button
            onClick={() => setSelectedEntityId(null)}
            className="text-[#555] hover:text-[#FF5252] transition-colors ml-0.5"
            title="Effacer le filtre entité"
          >
            <X size={11} />
          </button>
        </span>
      )}
      {selectedYear && (
        <span className="flex items-center gap-1.5 bg-[#111] border border-[#222] rounded-full px-3 py-1 text-[#B0B0B0]">
          <span className="text-[#666]">Exercice :</span>
          <span className="text-white font-medium">{selectedYear.name}</span>
          <button
            onClick={() => setSelectedYearId(null)}
            className="text-[#555] hover:text-[#FF5252] transition-colors ml-0.5"
            title="Effacer le filtre exercice"
          >
            <X size={11} />
          </button>
        </span>
      )}
    </div>
  );
}
