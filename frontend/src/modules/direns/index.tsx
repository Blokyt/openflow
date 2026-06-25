import { useEffect, useMemo, useState } from "react";
import { FileDown, Info, Table2, AlertTriangle } from "lucide-react";
import { useFiscalYear } from "../../core/FiscalYearContext";
import { api } from "../../api";

type TabId = "export" | "mapping";

const TABS: { id: TabId; label: string }[] = [
  { id: "export", label: "Exporter" },
  { id: "mapping", label: "Correspondances" },
];

export default function DirensPage() {
  const [tab, setTab] = useState<TabId>("export");

  return (
    <div className="p-8 space-y-6">
      <div>
        <h1 className="text-3xl font-bold text-white" style={{ letterSpacing: "-0.02em" }}>
          DirENS
        </h1>
        <p className="text-sm text-[#999] mt-1">
          Génère le fichier Excel financier officiel demandé par la DirENS, pré-rempli à partir des données de l'app.
        </p>
      </div>

      <div className="flex items-start gap-2 rounded-xl border border-[#222] bg-[#0d0d0d] px-4 py-3 text-xs text-[#999]">
        <Info size={15} className="text-[#F2C48D] flex-shrink-0 mt-0.5" strokeWidth={1.5} />
        <p>
          Seuls les deux premiers onglets sont remplis (bilan financier réalisé et budget prévisionnel) :
          un club par colonne, les montants ventilés sur les lignes de nature selon l'écran « Correspondances ».
          Le 3e onglet (demande de subventions) reste vierge, à compléter à la main. La mise en forme du
          modèle officiel est conservée à l'identique.
        </p>
      </div>

      <div className="flex gap-1 border-b border-[#222]">
        {TABS.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors ${
              tab === t.id
                ? "border-[#F2C48D] text-white"
                : "border-transparent text-[#666] hover:text-white"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === "export" && <ExportTab />}
      {tab === "mapping" && <MappingTab />}
    </div>
  );
}

// ─── Onglet Exporter ────────────────────────────────────────────────────────

function ExportTab() {
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

  if (!years.length) {
    return (
      <div className="rounded-2xl border border-[#222] bg-[#111] p-10 text-center text-sm text-[#777]">
        Aucun exercice. Crée d'abord un exercice dans le module Budget.
      </div>
    );
  }

  return (
    <div className="space-y-5 max-w-2xl">
      {error && (
        <div className="bg-[#1a0a0a] border border-[#FF5252]/30 text-[#FF5252] rounded-xl p-3 text-sm">
          {error}
        </div>
      )}

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
          Pense à vérifier l'écran « Correspondances » : seules les catégories associées à une ligne DirENS
          sont reportées dans le fichier. Les en-têtes de colonnes reprennent le nom des clubs ; tu peux les
          renommer dans le fichier généré.
        </p>
      </div>
    </div>
  );
}

// ─── Onglet Correspondances ────────────────────────────────────────────────

function MappingTab() {
  const [mapping, setMapping] = useState<any[]>([]);
  const [unmapped, setUnmapped] = useState<any[]>([]);
  const [rowGroups, setRowGroups] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState<number | null>(null);

  function load() {
    return api.getDirensLineMap().then((d) => {
      setMapping(d.mapping);
      setUnmapped(d.unmapped);
      setRowGroups(d.rows);
    });
  }

  useEffect(() => {
    setLoading(true);
    load().finally(() => setLoading(false));
  }, []);

  // row -> section (pour reconstruire la section au changement).
  const rowSection = useMemo(() => {
    const m: Record<number, string> = {};
    for (const g of rowGroups) for (const r of g.rows) m[r.row] = g.section;
    return m;
  }, [rowGroups]);

  const categories = useMemo(() => {
    const merged = [
      ...mapping.map((x) => ({ category_id: x.category_id, category_name: x.category_name, direns_row: x.direns_row })),
      ...unmapped.map((x) => ({ category_id: x.category_id, category_name: x.category_name, direns_row: null })),
    ];
    return merged.sort((a, b) => a.category_name.localeCompare(b.category_name, "fr"));
  }, [mapping, unmapped]);

  async function change(categoryId: number, value: string) {
    setSaving(categoryId);
    try {
      if (!value) {
        await api.deleteDirensLineMap(categoryId);
      } else {
        const row = parseInt(value, 10);
        await api.setDirensLineMap(categoryId, row, rowSection[row] ?? "expense");
      }
      await load();
    } finally {
      setSaving(null);
    }
  }

  if (loading) return <div className="text-sm text-[#777] py-8">Chargement…</div>;

  return (
    <div className="space-y-4">
      <p className="text-sm text-[#999]">
        Associe chaque catégorie OpenFlow à une ligne du modèle DirENS. Seules les catégories mappées
        apparaissent dans le fichier généré. La nomenclature des lignes (nourriture, locations, assurance…)
        est imposée par la DirENS ; le mapping est réutilisable d'une année sur l'autre.
      </p>

      {categories.length === 0 ? (
        <div className="rounded-2xl border border-[#222] bg-[#111] p-10 text-center text-sm text-[#777]">
          Aucune catégorie. Crée d'abord des catégories dans le module Catégories.
        </div>
      ) : (
        <div className="rounded-2xl border border-[#222] bg-[#111] overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-[#666] text-xs font-medium uppercase border-b border-[#222]">
                <th className="px-5 py-3 text-left">Catégorie</th>
                <th className="px-5 py-3 text-left">Ligne DirENS</th>
              </tr>
            </thead>
            <tbody>
              {categories.map((r) => (
                <tr key={r.category_id} className="border-b border-[#1a1a1a] last:border-0">
                  <td className="px-5 py-3 text-white">
                    <span className="inline-flex items-center gap-2">
                      {r.direns_row == null && (
                        <AlertTriangle size={13} className="text-[#F2C48D]" strokeWidth={1.8} />
                      )}
                      {r.category_name}
                    </span>
                  </td>
                  <td className="px-5 py-3">
                    <select
                      value={r.direns_row ?? ""}
                      disabled={saving === r.category_id}
                      onChange={(e) => change(r.category_id, e.target.value)}
                      className="bg-[#0d0d0d] border border-[#222] rounded-lg px-3 py-1.5 text-sm text-white min-w-[20rem] disabled:opacity-50"
                    >
                      <option value="">Non mappée (absente du fichier)</option>
                      {rowGroups.map((g) => (
                        <optgroup key={g.group} label={g.group}>
                          {g.rows.map((row: any) => (
                            <option key={row.row} value={row.row}>{row.label}</option>
                          ))}
                        </optgroup>
                      ))}
                    </select>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
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
