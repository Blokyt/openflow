import { useEffect, useState } from "react";
import { FileDown, Info, Table2 } from "lucide-react";
import { useFiscalYear } from "../../core/FiscalYearContext";
import { api } from "../../api";

export default function DirensPage() {
  const { years } = useFiscalYear();
  const [bilanId, setBilanId] = useState<number | null>(null);
  const [budgetId, setBudgetId] = useState<number | null>(null);
  const [assocName, setAssocName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Préremplit le nom de l'association depuis la config.
  useEffect(() => {
    api.getConfig().then((c) => setAssocName(c?.entity?.name ?? "")).catch(() => {});
  }, []);

  // Défauts intelligents : bilan = dernier exercice clôturé, budget = exercice ouvert.
  useEffect(() => {
    if (!years.length) return;
    const closed = years.filter((y: any) => y.end_date);
    const open = years.find((y: any) => !y.end_date);
    setBilanId((prev) => prev ?? (closed[0]?.id ?? years[0].id));
    setBudgetId((prev) => prev ?? (open?.id ?? null));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [years.length]);

  async function handleDownload() {
    if (!bilanId) return;
    setBusy(true);
    setError(null);
    try {
      await api.downloadDirens({
        bilan_fiscal_year_id: bilanId,
        budget_fiscal_year_id: budgetId ?? undefined,
        assoc_name: assocName,
      });
    } catch (e: any) {
      setError(e?.message || "Erreur lors de la génération du fichier");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="p-8 space-y-6">
      <div>
        <h1 className="text-3xl font-bold text-white" style={{ letterSpacing: "-0.02em" }}>
          DirENS
        </h1>
        <p className="text-sm text-[#999] mt-1">
          Génère le fichier Excel financier officiel demandé par la DirENS, entièrement pré-rempli
          à partir des données de l'app.
        </p>
      </div>

      <div className="flex items-start gap-2 rounded-xl border border-[#222] bg-[#0d0d0d] px-4 py-3 text-xs text-[#999]">
        <Info size={15} className="text-[#F2C48D] flex-shrink-0 mt-0.5" strokeWidth={1.5} />
        <p>
          Aucune configuration. Les lignes reprennent tes catégories OpenFlow en respectant la
          hiérarchie (catégorie parente en gras, sous-catégories indentées en dessous), et chaque
          club actif devient une colonne ; un club sans mouvement n'apparaît pas. Le titre et
          l'année sont déduits du mandat choisi. Seuls les deux premiers onglets sont remplis
          (bilan réalisé + budget prévisionnel) ; le 3e (demande de subventions) reste vierge.
          La mise en forme du modèle officiel est conservée.
        </p>
      </div>

      {error && (
        <div className="bg-[#1a0a0a] border border-[#FF5252]/30 text-[#FF5252] rounded-xl p-3 text-sm max-w-2xl">
          {error}
        </div>
      )}

      {!years.length ? (
        <div className="rounded-2xl border border-[#222] bg-[#111] p-10 text-center text-sm text-[#777] max-w-2xl">
          Aucun exercice. Crée d'abord un exercice dans le module Budget.
        </div>
      ) : (
        <div className="space-y-5 max-w-2xl">
          <div className="rounded-2xl border border-[#222] bg-[#111] p-5 space-y-4">
            <Field label="Onglet 1 — Bilan financier (exercice réalisé)">
              <select
                value={bilanId ?? ""}
                onChange={(e) => setBilanId(parseInt(e.target.value, 10))}
                className="bg-[#0d0d0d] border border-[#222] rounded-lg px-3 py-2 text-sm text-white w-full"
              >
                {years.map((y: any) => (
                  <option key={y.id} value={y.id}>
                    {y.name}{y.end_date === null ? " ● (en cours)" : ""}
                  </option>
                ))}
              </select>
            </Field>

            <Field label="Onglet 2 — Budget prévisionnel (exercice à venir, optionnel)">
              <select
                value={budgetId ?? ""}
                onChange={(e) => setBudgetId(e.target.value ? parseInt(e.target.value, 10) : null)}
                className="bg-[#0d0d0d] border border-[#222] rounded-lg px-3 py-2 text-sm text-white w-full"
              >
                <option value="">Ne pas remplir l'onglet budget</option>
                {years.map((y: any) => (
                  <option key={y.id} value={y.id}>
                    {y.name}{y.end_date === null ? " ● (en cours)" : ""}
                  </option>
                ))}
              </select>
            </Field>

            <Field label="Nom de l'association (cellule A3 du modèle)">
              <input
                value={assocName}
                onChange={(e) => setAssocName(e.target.value)}
                placeholder="Nom de l'association"
                className="bg-[#0d0d0d] border border-[#222] rounded-lg px-3 py-2 text-sm text-white w-full"
              />
            </Field>

            <button
              onClick={handleDownload}
              disabled={busy || !bilanId}
              className="flex items-center gap-2 rounded-xl bg-[#F2C48D] px-4 py-2.5 text-sm font-semibold text-black hover:opacity-90 transition disabled:opacity-50"
            >
              <FileDown size={16} strokeWidth={2} />
              {busy ? "Génération…" : "Télécharger l'Excel DirENS"}
            </button>
          </div>

          <div className="flex items-start gap-2 rounded-xl border border-[#222] bg-[#0d0d0d] px-4 py-3 text-xs text-[#888]">
            <Table2 size={15} className="text-[#666] flex-shrink-0 mt-0.5" strokeWidth={1.5} />
            <p>
              Le solde de trésorerie est estimé à partir de l'app ; les lignes « Solde compte bancaire »
              affichent « à compléter » car l'app ne distingue pas encore compte courant, Livret A et
              caisse physique. Plus généralement, tout ce qui n'est pas déductible des données n'est pas
              rempli (placeholder au plus). Les transactions sans catégorie sont regroupées sur une ligne
              « Non catégorisé ».
            </p>
          </div>
        </div>
      )}
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="text-xs text-[#999]">{label}</span>
      {children}
    </label>
  );
}
