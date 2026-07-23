import { useEffect, useState } from "react";
import { FileDown, AlertTriangle, Plus, Trash2, Sparkles } from "lucide-react";
import { useFiscalYear } from "../../core/FiscalYearContext";
import { useEntity } from "../../core/EntityContext";
import { useAuth } from "../../core/AuthContext";
import ConfirmDialog from "../../core/ConfirmDialog";
import { api } from "../../api";
import { formatEuros, eurosToCents } from "../../utils/format";

type TabId = "resultat" | "bilan" | "cloture" | "plan";

const TABS: { id: TabId; label: string }[] = [
  { id: "resultat", label: "Compte de résultat" },
  { id: "bilan", label: "Bilan" },
  { id: "cloture", label: "Clôture" },
  { id: "plan", label: "Plan comptable" },
];

const COLOR_OK = "#00C853";
const COLOR_KO = "#FF5252";

/** Charge des données dépendant de l'exercice (et de deps additionnelles), avec annulation à la sortie. */
function useYearData<T>(year: any, fetcher: (id: number) => Promise<T>, deps: any[] = []): { data: T | null; loading: boolean; error: string | null } {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    if (!year) { setData(null); setError(null); return; }
    let cancelled = false;
    setLoading(true); setError(null);
    fetcher(year.id)
      .then((d) => { if (!cancelled) setData(d); })
      .catch((e) => { if (!cancelled) { setData(null); setError(e?.message || "erreur inconnue"); } })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [year?.id, ...deps]);
  return { data, loading, error };
}

export default function Reports() {
  const { years, selectedYear, setSelectedYearId } = useFiscalYear();
  // Le périmètre des rapports suit le focus entité global (sidebar) : même
  // sélection partout, modifiable aussi depuis cette page.
  const { selectedEntityId, setSelectedEntityId } = useEntity();
  const [tab, setTab] = useState<TabId>("resultat");
  const [entities, setEntities] = useState<any[]>([]);

  useEffect(() => {
    api.getEntities("internal").then(setEntities).catch(() => setEntities([]));
  }, []);

  // Une entité externe sélectionnée globalement n'a pas de sens comptable ici :
  // on retombe sur le périmètre consolidé sans toucher au focus global.
  const entityId = entities.some((e) => e.id === selectedEntityId) ? selectedEntityId : null;
  const scopeName = entityId ? entities.find((e) => e.id === entityId)?.name : null;
  const scoped = tab === "resultat" || tab === "bilan";

  return (
    <div className="p-8 space-y-6">
      <div className="flex items-end justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold text-white" style={{ letterSpacing: "-0.02em" }}>
            Rapports comptables
          </h1>
          <p className="text-sm text-[#8a8a8a] mt-1">
            {scoped && scopeName
              ? `Périmètre « ${scopeName} » : le club et ses sous-entités (les dotations reçues comptent comme produits).`
              : "Compte de résultat et bilan de l'exercice, sur le périmètre consolidé de l'association."}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {scoped && entities.length > 0 && (
            <select
              value={entityId ?? ""}
              onChange={(e) => setSelectedEntityId(e.target.value ? parseInt(e.target.value, 10) : null)}
              className="bg-bg-card border border-border rounded-xl px-3 py-2.5 text-sm text-white focus:outline-none focus:border-accent-sand"
            >
              <option value="">Toute l'association</option>
              {entities.map((e) => (
                <option key={e.id} value={e.id}>{e.name}</option>
              ))}
            </select>
          )}
          {years.length > 0 && (
            <select
              value={selectedYear?.id ?? ""}
              onChange={(e) => setSelectedYearId(parseInt(e.target.value, 10))}
              className="bg-bg-card border border-border rounded-xl px-3 py-2.5 text-sm text-white focus:outline-none focus:border-accent-sand"
            >
              {years.map((y) => (
                <option key={y.id} value={y.id}>
                  {y.name}{y.end_date === null ? " ●" : ""}
                </option>
              ))}
            </select>
          )}
        </div>
      </div>

      <div className="flex gap-1 border-b border-border">
        {TABS.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors ${
              tab === t.id
                ? "border-accent-sand text-white"
                : "border-transparent text-[#8a8a8a] hover:text-white"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === "resultat" && <CompteResultatTab year={selectedYear} entityId={entityId} />}
      {tab === "bilan" && <BilanTab year={selectedYear} entityId={entityId} />}
      {tab === "cloture" && <ClotureTab year={selectedYear} />}
      {tab === "plan" && <PlanComptableTab />}
    </div>
  );
}

// ─── Composants partagés ──────────────────────────────────────────────────

function EmptyYear() {
  return (
    <div className="rounded-2xl border border-border bg-bg-card p-10 text-center text-sm text-[#777]">
      Aucun exercice sélectionné. Crée d'abord un exercice dans le module Budget.
    </div>
  );
}

function Loading() {
  return <div className="text-sm text-[#777] py-8">Chargement…</div>;
}

function ErrorNote({ message }: { message: string }) {
  return (
    <div className="bg-[#1a0a0a] border border-alert/30 text-alert rounded-2xl p-4 text-sm my-4">
      Impossible de charger le rapport : {message}
    </div>
  );
}

function PdfButton({ onClick }: { onClick: () => void }) {
  const [busy, setBusy] = useState(false);
  const [pdfError, setPdfError] = useState<string | null>(null);
  return (
    <div className="flex flex-col items-end gap-2">
      {pdfError && (
        <div className="bg-[#1a0a0a] border border-alert/30 text-alert rounded-xl p-3 text-sm">
          {pdfError}
        </div>
      )}
      <button
        onClick={async () => {
          setBusy(true);
          setPdfError(null);
          try {
            await onClick();
          } catch (e: any) {
            setPdfError(e?.message || "Erreur lors de la génération du PDF");
          } finally {
            setBusy(false);
          }
        }}
        disabled={busy}
        className="flex items-center gap-2 px-4 py-2.5 text-sm font-semibold text-white border border-border-hover rounded-full hover:border-[#444] hover:bg-[#1a1a1a] transition-colors disabled:opacity-50"
      >
        <FileDown size={15} strokeWidth={1.5} />
        {busy ? "Génération…" : "Télécharger le PDF"}
      </button>
    </div>
  );
}

// ─── Compte de résultat ─────────────────────────────────────────────────────

function CompteResultatTab({ year, entityId }: { year: any; entityId: number | null }) {
  const { data, loading, error } = useYearData(
    year,
    (id) => api.getCompteResultat({ fiscal_year_id: id, entity_id: entityId ?? undefined }),
    [entityId],
  );

  if (!year) return <EmptyYear />;
  if (error) return <ErrorNote message={error} />;
  if (loading || !data) return <Loading />;

  const resultat: number = data.resultat;
  const excedent = resultat >= 0;

  return (
    <div className="space-y-6">
      <div className="flex justify-end">
        <PdfButton onClick={() => api.downloadReportPdf("compte-resultat", { fiscal_year_id: year.id, entity_id: entityId ?? undefined })} />
      </div>

      <ResultatSection
        titre="Produits"
        postes={data.produits_par_compte}
        total={data.total_produits}
        accent={COLOR_OK}
        totalLabel="Total des produits"
      />
      <ResultatSection
        titre="Charges"
        postes={data.charges_par_compte}
        total={data.total_charges}
        accent={COLOR_KO}
        totalLabel="Total des charges"
      />

      <div
        className="flex items-center justify-between rounded-2xl border px-5 py-4"
        style={{ borderColor: (excedent ? COLOR_OK : COLOR_KO) + "33", background: (excedent ? COLOR_OK : COLOR_KO) + "0d" }}
      >
        <span className="text-base font-semibold text-white">
          {excedent ? "Excédent de l'exercice" : "Déficit de l'exercice"}
        </span>
        <span className="text-xl font-bold" style={{ color: excedent ? COLOR_OK : COLOR_KO }}>
          {formatEuros(Math.abs(resultat))}
        </span>
      </div>
    </div>
  );
}

function ResultatSection({
  titre, postes, total, accent, totalLabel,
}: { titre: string; postes: any[]; total: number; accent: string; totalLabel: string }) {
  return (
    <div className="rounded-2xl border border-border bg-bg-card overflow-x-auto">
      <div className="px-5 py-3 border-b border-border flex items-center gap-2">
        <span className="w-2 h-2 rounded-full" style={{ background: accent }} />
        <h2 className="text-sm font-semibold uppercase tracking-wide text-white">{titre}</h2>
      </div>
      <table className="w-full text-sm">
        <tbody>
          {(!postes || postes.length === 0) && (
            <tr>
              <td className="px-5 py-4 text-[#8a8a8a]" colSpan={2}>Aucun montant sur l'exercice.</td>
            </tr>
          )}
          {postes?.map((p) => (
            <tr key={p.account_id ?? p.code} className="border-b border-[#1a1a1a] last:border-0 align-top">
              <td className="px-5 py-3">
                <div className="text-white">
                  <span className="text-[#777] mr-2">{p.code}</span>{p.label}
                </div>
                {p.categories?.length > 0 && (
                  <div className="mt-1 space-y-0.5">
                    {p.categories.map((c: any) => (
                      <div key={`${c.category_id}`} className="flex justify-between text-xs text-[#8a8a8a] pl-6">
                        <span>{c.category_name}</span>
                        <span>{formatEuros(c.montant)}</span>
                      </div>
                    ))}
                  </div>
                )}
              </td>
              <td className="px-5 py-3 text-right text-white whitespace-nowrap font-medium">
                {formatEuros(p.montant)}
              </td>
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr className="border-t border-border bg-[#0d0d0d]">
            <td className="px-5 py-3 font-semibold text-white uppercase text-xs tracking-wide">{totalLabel}</td>
            <td className="px-5 py-3 text-right font-bold text-white whitespace-nowrap">{formatEuros(total)}</td>
          </tr>
        </tfoot>
      </table>
    </div>
  );
}

// ─── Bilan ──────────────────────────────────────────────────────────────────

function BilanTab({ year, entityId }: { year: any; entityId: number | null }) {
  const { data, loading, error } = useYearData(
    year,
    (id) => api.getBilan({ fiscal_year_id: id, entity_id: entityId ?? undefined }),
    [entityId],
  );

  if (!year) return <EmptyYear />;
  if (error) return <ErrorNote message={error} />;
  if (loading || !data || !data.actif) return <Loading />;

  const { actif, passif, equilibre } = data;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-xs text-[#777]">Arrêté au {data.arrete_le}.</p>
        <PdfButton onClick={() => api.downloadReportPdf("bilan", { fiscal_year_id: year.id, entity_id: entityId ?? undefined })} />
      </div>
      {/* L'équilibre actif = passif est la norme : on n'alerte qu'en cas d'anomalie. */}
      {!equilibre && (
        <span
          className="inline-flex items-center gap-2 rounded-full px-3 py-1 text-xs font-medium"
          style={{ color: COLOR_KO, background: COLOR_KO + "0d" }}
        >
          <AlertTriangle size={14} /> Bilan déséquilibré : vérifie les saisies de clôture.
        </span>
      )}

      <div className="grid md:grid-cols-2 gap-4">
        <BilanColumn title="Actif">
          {actif.disponibilites.map((d: any) => (
            <BilanRow key={d.entity_id} label={`Disponibilités · ${d.name}`} montant={d.montant} />
          ))}
          {actif.total_creances > 0 && (
            <BilanRow label="Créances (produits à recevoir)" montant={actif.total_creances} detail={actif.creances_detail} />
          )}
          <BilanRow label="Total de l'actif" montant={actif.total} bold />
        </BilanColumn>

        <BilanColumn title="Passif">
          <BilanRow label="Fonds associatifs et report à nouveau" montant={passif.report_a_nouveau} />
          <BilanRow label="Résultat de l'exercice" montant={passif.resultat_exercice} />
          {passif.total_dettes > 0 && (
            <BilanRow label="Dettes (charges à payer)" montant={passif.total_dettes} detail={passif.dettes_detail} />
          )}
          <BilanRow label="Total du passif" montant={passif.total} bold />
        </BilanColumn>
      </div>
    </div>
  );
}

function BilanColumn({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-2xl border border-border bg-bg-card overflow-hidden">
      <div className="px-5 py-3 border-b border-border">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-white">{title}</h2>
      </div>
      <div>{children}</div>
    </div>
  );
}

function BilanRow({
  label, montant, bold, detail,
}: { label: string; montant: number; bold?: boolean; detail?: any[] }) {
  return (
    <div className={`border-b border-[#1a1a1a] last:border-0 ${bold ? "bg-[#0d0d0d]" : ""}`}>
      <div className="flex items-center justify-between px-5 py-3">
        <span className={bold ? "text-xs font-semibold uppercase tracking-wide text-white" : "text-sm text-[#ccc]"}>
          {label}
        </span>
        <span className={`whitespace-nowrap ${bold ? "font-bold text-white" : "text-white"}`}>
          {formatEuros(montant)}
        </span>
      </div>
      {detail && detail.length > 0 && (
        <div className="px-5 pb-3 -mt-1 space-y-0.5">
          {detail.map((d: any) => (
            <div key={d.category_id ?? d.category_name} className="flex justify-between text-xs text-[#8a8a8a] pl-6">
              <span>{d.category_name}</span>
              <span>{formatEuros(d.montant)}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ─── Plan comptable (mapping catégorie -> compte) ───────────────────────────

function PlanComptableTab() {
  const { isAdmin } = useAuth();
  const [accounts, setAccounts] = useState<any[]>([]);
  const [rows, setRows] = useState<any[]>([]);
  const [suggestions, setSuggestions] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState<number | null>(null);
  const [applying, setApplying] = useState(false);
  const [planError, setPlanError] = useState<string | null>(null);

  function loadMapping() {
    return api.getReportMapping().then((m) => {
      const toRow = (x: any, account_id: number | null) => ({
        category_id: x.category_id,
        category_name: x.category_name,
        account_id,
      });
      const merged = [
        ...m.mapping.map((x: any) => toRow(x, x.account_id)),
        ...m.unmapped.map((x: any) => toRow(x, null)),
      ];
      setRows(merged.sort((p, q) => p.category_name.localeCompare(q.category_name, "fr")));
    });
  }

  function loadSuggestions() {
    return api.getReportMappingSuggestions().then((s) => setSuggestions(s.suggestions));
  }

  useEffect(() => {
    setLoading(true);
    // Les comptes ne changent pas au gré du mapping : chargés une seule fois.
    Promise.all([
      api.getReportAccounts().then((a) => setAccounts(a.accounts)),
      loadMapping(),
      loadSuggestions(),
    ]).finally(() => setLoading(false));
  }, []);

  async function change(categoryId: number, accountId: number | null) {
    setSaving(categoryId);
    setPlanError(null);
    try {
      await api.setReportMapping(categoryId, accountId);
      await Promise.all([loadMapping(), loadSuggestions()]);
    } catch (e: any) {
      setPlanError(e?.message || "Erreur lors de la mise à jour du mapping");
    } finally {
      setSaving(null);
    }
  }

  async function applyAllSuggestions() {
    setApplying(true);
    setPlanError(null);
    try {
      await api.applyReportMappingSuggestions(
        suggestions.map((s) => ({ category_id: s.category_id, account_id: s.suggested_account_id })),
      );
      await Promise.all([loadMapping(), loadSuggestions()]);
    } catch (e: any) {
      setPlanError(e?.message || "Erreur lors de l'application des suggestions");
    } finally {
      setApplying(false);
    }
  }

  function accountLabel(accountId: number | null) {
    if (!accountId) return "Non mappée (compte Autres par défaut)";
    const a = accounts.find((x) => x.id === accountId);
    return a ? `${a.code} · ${a.label}` : "Compte inconnu";
  }

  if (loading) return <Loading />;

  const produits = accounts.filter((a) => a.kind === "produit");
  const charges = accounts.filter((a) => a.kind === "charge");

  return (
    <div className="space-y-4">
      <p className="text-sm text-[#999]">
        Associe chaque catégorie à un poste du plan comptable. Cela ne change pas tes catégories ni
        les totaux : le sens produit/charge vient du flux. Une catégorie non mappée tombe dans le
        compte « Autres » de son sens.
      </p>

      {!isAdmin && (
        <p className="text-sm text-[#8a8a8a]">
          Lecture seule : le plan comptable est géré par l'administrateur.
        </p>
      )}

      {planError && (
        <div className="bg-[#1a0a0a] border border-alert/30 text-alert rounded-xl p-3 text-sm">
          {planError}
        </div>
      )}

      {suggestions.length > 0 && (
        <div className="rounded-2xl border border-accent-sand/30 bg-accent-sand/[0.06] p-4 flex items-start justify-between gap-4">
          <div className="flex items-start gap-2 min-w-0">
            <Sparkles size={16} className="text-accent-sand flex-shrink-0 mt-0.5" />
            <div className="min-w-0">
              <p className="text-sm font-medium text-white">
                {suggestions.length} catégorie{suggestions.length > 1 ? "s" : ""} {suggestions.length > 1 ? "peuvent" : "peut"} être classée{suggestions.length > 1 ? "s" : ""} automatiquement
              </p>
              <p className="text-xs text-[#999] mt-0.5 truncate">
                {suggestions.slice(0, 4).map((s) => `${s.category_name} → ${s.suggested_account_code}`).join(", ")}
                {suggestions.length > 4 ? "…" : ""}
              </p>
            </div>
          </div>
          {isAdmin && (
            <button
              onClick={applyAllSuggestions}
              disabled={applying}
              className="flex items-center gap-1.5 rounded-xl bg-accent-sand px-3 py-2 text-sm font-medium text-black hover:opacity-90 transition disabled:opacity-50 whitespace-nowrap"
            >
              <Sparkles size={14} /> {applying ? "Application…" : `Appliquer (${suggestions.length})`}
            </button>
          )}
        </div>
      )}

      {rows.length === 0 && (
        <div className="rounded-2xl border border-border bg-bg-card p-10 text-center text-sm text-[#777]">
          Aucune catégorie. Crée d'abord des catégories dans le module Catégories.
        </div>
      )}

      {rows.length > 0 && (
        <div className="rounded-2xl border border-border bg-bg-card overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-[#8a8a8a] text-xs font-medium uppercase border-b border-border">
                <th className="px-5 py-3 text-left">Catégorie</th>
                <th className="px-5 py-3 text-left">Compte comptable</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.category_id} className="border-b border-[#1a1a1a] last:border-0">
                  <td className="px-5 py-3 text-white">{r.category_name}</td>
                  <td className="px-5 py-3">
                    {isAdmin ? (
                      <select
                        value={r.account_id ?? ""}
                        disabled={saving === r.category_id}
                        onChange={(e) =>
                          change(r.category_id, e.target.value ? parseInt(e.target.value, 10) : null)
                        }
                        className="bg-[#0d0d0d] border border-border rounded-lg px-3 py-1.5 text-sm text-white min-w-[18rem] disabled:opacity-50"
                      >
                        <option value="">Non mappée (compte Autres par défaut)</option>
                        <optgroup label="Produits (classe 7)">
                          {produits.map((a) => (
                            <option key={a.id} value={a.id}>{a.code} · {a.label}</option>
                          ))}
                        </optgroup>
                        <optgroup label="Charges (classe 6)">
                          {charges.map((a) => (
                            <option key={a.id} value={a.id}>{a.code} · {a.label}</option>
                          ))}
                        </optgroup>
                      </select>
                    ) : (
                      <span className="text-[#8a8a8a]">{accountLabel(r.account_id)}</span>
                    )}
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

// ─── Clôture : saisie des créances et dettes (engagement) ───────────────────

const inputCls = "bg-[#0d0d0d] border border-border rounded-lg px-3 py-2 text-sm text-white";

function Field({ label, children, className }: { label: string; children: React.ReactNode; className?: string }) {
  return (
    <label className={`flex flex-col gap-1 ${className ?? ""}`}>
      <span className="text-xs text-[#777]">{label}</span>
      {children}
    </label>
  );
}

function ClotureTab({ year }: { year: any }) {
  const { isAdmin } = useAuth();
  const [accruals, setAccruals] = useState<any[]>([]);
  const [categories, setCategories] = useState<any[]>([]);
  const [entities, setEntities] = useState<any[]>([]);
  const [kind, setKind] = useState<"creance" | "dette">("creance");
  const [label, setLabel] = useState("");
  const [amount, setAmount] = useState("");
  const [categoryId, setCategoryId] = useState("");
  const [entityId, setEntityId] = useState("");
  const [saving, setSaving] = useState(false);
  const [clotureError, setClotureError] = useState<string | null>(null);
  const [pendingDelete, setPendingDelete] = useState<number | null>(null);
  const [deleting, setDeleting] = useState(false);

  function reload() {
    if (!year) return;
    api.getAccruals(year.id).then(setAccruals).catch(() => setAccruals([]));
  }

  useEffect(() => {
    if (!year) { setAccruals([]); return; }
    reload();
  }, [year?.id]);

  useEffect(() => {
    api.getCategories().then(setCategories).catch(() => setCategories([]));
    api.getEntities("internal").then(setEntities).catch(() => setEntities([]));
  }, []);

  if (!year) return <EmptyYear />;

  async function add() {
    const cents = eurosToCents(amount);
    if (!label.trim() || cents <= 0) {
      setClotureError("Renseigne un libellé et un montant positif.");
      return;
    }
    setSaving(true);
    setClotureError(null);
    try {
      await api.createAccrual({
        fiscal_year_id: year.id,
        kind,
        amount: cents,
        label: label.trim(),
        category_id: categoryId ? Number(categoryId) : null,
        entity_id: entityId ? Number(entityId) : null,
      });
      setLabel(""); setAmount(""); setCategoryId(""); setEntityId("");
      reload();
    } catch (e: any) {
      setClotureError(e?.message || "Erreur lors de l'enregistrement");
    } finally {
      setSaving(false);
    }
  }

  async function confirmRemove() {
    if (pendingDelete == null) return;
    setDeleting(true);
    try {
      await api.deleteAccrual(pendingDelete);
      setPendingDelete(null);
      reload();
    } catch (e: any) {
      setClotureError(e?.message || "Erreur lors de la suppression");
      setPendingDelete(null);
    } finally {
      setDeleting(false);
    }
  }

  const creances = accruals.filter((a) => a.kind === "creance");
  const dettes = accruals.filter((a) => a.kind === "dette");

  return (
    <div className="space-y-6">
      <p className="text-sm text-[#999]">
        Saisis les <strong className="text-white">restes à recevoir</strong> (créances : subventions ou cotisations
        dues mais pas encore encaissées) et les <strong className="text-white">restes à payer</strong> (dettes :
        factures reçues mais pas encore payées) de l'exercice. Ils rattachent le produit ou la charge à cet exercice ;
        l'encaissement ou le paiement de l'exercice suivant est neutralisé automatiquement (extourne).
      </p>

      {clotureError && (
        <div className="bg-[#1a0a0a] border border-alert/30 text-alert rounded-xl p-3 text-sm">
          {clotureError}
        </div>
      )}

      {isAdmin ? (
        <div className="rounded-2xl border border-border bg-bg-card p-4 grid gap-3 md:grid-cols-6 items-end">
          <Field label="Nature">
            <select value={kind} onChange={(e) => setKind(e.target.value as any)} className={inputCls}>
              <option value="creance">Créance (à recevoir)</option>
              <option value="dette">Dette (à payer)</option>
            </select>
          </Field>
          <Field label="Libellé" className="md:col-span-2">
            <input
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              placeholder="Subvention BDE à recevoir"
              className={inputCls}
            />
          </Field>
          <Field label="Montant (€)">
            <input
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              inputMode="decimal"
              placeholder="0,00"
              className={inputCls}
            />
          </Field>
          <Field label="Catégorie">
            <select value={categoryId} onChange={(e) => setCategoryId(e.target.value)} className={inputCls}>
              <option value="">Aucune</option>
              {categories.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
          </Field>
          <Field label="Entité">
            <select value={entityId} onChange={(e) => setEntityId(e.target.value)} className={inputCls}>
              <option value="">Aucune</option>
              {entities.map((en) => <option key={en.id} value={en.id}>{en.name}</option>)}
            </select>
          </Field>
          <div className="md:col-span-6">
            <button
              onClick={add}
              disabled={saving}
              className="flex items-center gap-2 rounded-xl bg-accent-sand px-4 py-2 text-sm font-medium text-black hover:opacity-90 transition disabled:opacity-50"
            >
              <Plus size={15} strokeWidth={2} />
              Ajouter
            </button>
          </div>
        </div>
      ) : (
        <p className="text-sm text-[#8a8a8a]">
          Lecture seule : les écritures de clôture sont gérées par l'administrateur.
        </p>
      )}

      <AccrualList title="Restes à recevoir (créances)" items={creances} onDelete={(id) => setPendingDelete(id)} accent={COLOR_OK} isAdmin={isAdmin} />
      <AccrualList title="Restes à payer (dettes)" items={dettes} onDelete={(id) => setPendingDelete(id)} accent={COLOR_KO} isAdmin={isAdmin} />

      <ConfirmDialog
        open={pendingDelete !== null}
        danger
        title="Supprimer cette écriture ?"
        message="Cette écriture de clôture (créance ou dette) sera définitivement supprimée et le bilan de l'exercice recalculé."
        confirmLabel="Supprimer"
        busy={deleting}
        onConfirm={confirmRemove}
        onCancel={() => setPendingDelete(null)}
      />
    </div>
  );
}

function AccrualList({
  title, items, onDelete, accent, isAdmin,
}: { title: string; items: any[]; onDelete: (id: number) => void; accent: string; isAdmin: boolean }) {
  return (
    <div className="rounded-2xl border border-border bg-bg-card overflow-hidden">
      <div className="px-5 py-3 border-b border-border flex items-center gap-2">
        <span className="w-2 h-2 rounded-full" style={{ background: accent }} />
        <h2 className="text-sm font-semibold uppercase tracking-wide text-white">{title}</h2>
      </div>
      {items.length === 0 ? (
        <div className="px-5 py-4 text-sm text-[#8a8a8a]">Aucune saisie.</div>
      ) : (
        <table className="w-full text-sm">
          <tbody>
            {items.map((a) => (
              <tr key={a.id} className="border-b border-[#1a1a1a] last:border-0">
                <td className="px-5 py-3 text-white">
                  {a.label}
                  {(a.category_name || a.entity_name) && (
                    <span className="text-xs text-[#8a8a8a] ml-2">
                      {[a.category_name, a.entity_name].filter(Boolean).join(" · ")}
                    </span>
                  )}
                </td>
                <td className="px-5 py-3 text-right text-white whitespace-nowrap">{formatEuros(a.amount)}</td>
                <td className="px-3 py-3 text-right">
                  {isAdmin && (
                    <button
                      onClick={() => onDelete(a.id)}
                      className="text-[#8a8a8a] hover:text-alert transition"
                      title="Supprimer"
                    >
                      <Trash2 size={15} strokeWidth={1.5} />
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
