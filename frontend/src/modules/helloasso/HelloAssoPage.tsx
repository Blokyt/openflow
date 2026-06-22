import { useCallback, useEffect, useState } from "react";
import { RefreshCw, KeyRound, Link2, CheckCircle2, AlertCircle, X, ArrowRight } from "lucide-react";
import { api } from "../../api";
import { useFiscalYear } from "../../core/FiscalYearContext";
import { formatEuros } from "../../utils/format";
import EmptyState from "../../core/EmptyState";

type Campaign = {
  form_type: string;
  form_slug: string;
  title: string;
  state: string;
  collected_cents: number;
  recorded_cents: number | null;
  gap_cents: number | null;
  link: { category_id: number | null; from_entity_id: number; to_entity_id: number } | null;
};
type Category = { id: number; name: string };
type Entity = { id: number; name: string; type: string };

const TYPE_LABELS: Record<string, string> = {
  Membership: "Cotisations",
  Event: "Billetterie",
  Donation: "Dons",
  CrowdFunding: "Collecte",
  Shop: "Boutique",
  PaymentForm: "Paiement",
};
const typeLabel = (t: string) => TYPE_LABELS[t] || t || "—";

const inputClass =
  "w-full bg-[#0a0a0a] border border-[#222] rounded-xl px-3 py-2.5 text-sm text-white focus:outline-none focus:border-[#F2C48D] transition-colors placeholder-[#444] [color-scheme:dark]";
const labelClass = "block text-sm font-medium text-[#B0B0B0] mb-1.5";

const money = (cents: number | null) => (cents == null ? "—" : formatEuros(cents));

export default function HelloAssoPage() {
  const { selectedYear } = useFiscalYear();
  const [configured, setConfigured] = useState<boolean | null>(null);
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [entities, setEntities] = useState<Entity[]>([]);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [editingSlug, setEditingSlug] = useState<string | null>(null);
  const [adjustingSlug, setAdjustingSlug] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!selectedYear) return;
    setLoading(true);
    setError(null);
    try {
      const cfg = await api.getHelloAssoConfig();
      setConfigured(cfg.configured);
      if (cfg.configured) {
        const [camps, cats, ents] = await Promise.all([
          api.getHelloAssoCampaigns(selectedYear.id),
          api.getCategories(),
          api.getEntities(),
        ]);
        setCampaigns(camps);
        setCategories(cats);
        setEntities(ents);
      }
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [selectedYear?.id]);

  useEffect(() => {
    load();
  }, [load]);

  const refresh = async () => {
    if (!selectedYear) return;
    setSyncing(true);
    setError(null);
    try {
      await api.syncHelloAsso(selectedYear.id);
      await load();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setSyncing(false);
    }
  };

  const confirmAdjust = async (c: Campaign) => {
    if (!selectedYear) return;
    setSyncing(true);
    setError(null);
    try {
      await api.adjustHelloAsso({
        form_type: c.form_type,
        form_slug: c.form_slug,
        fiscal_year_id: selectedYear.id,
      });
      setAdjustingSlug(null);
      await load();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setSyncing(false);
    }
  };

  const totalCollected = campaigns.reduce((s, c) => s + (c.collected_cents || 0), 0);
  const toFix = campaigns.filter((c) => c.gap_cents != null && c.gap_cents !== 0).length;
  const editingCampaign = campaigns.find((c) => c.form_slug === editingSlug) || null;
  const adjustingCampaign = campaigns.find((c) => c.form_slug === adjustingSlug) || null;

  if (loading && configured === null) {
    return (
      <div className="p-8">
        <h1 className="text-3xl font-bold text-white" style={{ letterSpacing: "-0.02em" }}>HelloAsso</h1>
        <div className="flex items-center justify-center py-20">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-[#F2C48D]" />
        </div>
      </div>
    );
  }

  if (configured === false) {
    return (
      <div className="p-8">
        <h1 className="text-3xl font-bold text-white mb-1" style={{ letterSpacing: "-0.02em" }}>HelloAsso</h1>
        <p className="text-sm text-[#666] mb-8">Connecte ton compte pour suivre tes campagnes et billetteries.</p>
        <ConfigForm onSaved={load} />
      </div>
    );
  }

  return (
    <div className="p-8">
      <div className="flex items-start justify-between mb-8 gap-4">
        <div>
          <h1 className="text-3xl font-bold text-white" style={{ letterSpacing: "-0.02em" }}>HelloAsso</h1>
          <p className="text-sm text-[#666] mt-1">
            Collecté en ligne vs enregistré en compta, par campagne et par exercice.
          </p>
        </div>
        <button
          onClick={refresh}
          disabled={syncing}
          className="flex items-center gap-2 px-5 py-2.5 text-sm font-semibold text-black bg-[#F2C48D] rounded-full hover:bg-[#e8b87a] disabled:opacity-50 transition-colors whitespace-nowrap"
        >
          <RefreshCw size={15} className={syncing ? "animate-spin" : ""} />
          {syncing ? "Synchronisation…" : "Rafraîchir"}
        </button>
      </div>

      {error && (
        <div className="mb-6 bg-[#1a0a0a] border border-[#FF5252]/30 text-[#FF5252] rounded-2xl p-4 text-sm flex items-start justify-between gap-3">
          <span className="flex items-center gap-2"><AlertCircle size={16} /> {error}</span>
          <button onClick={() => setError(null)} className="text-[#FF5252]/70 hover:text-[#FF5252]"><X size={16} /></button>
        </div>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-6">
        <div className="bg-[#111] border border-[#222] rounded-2xl p-5">
          <div className="text-xs font-medium text-[#666] uppercase tracking-wider mb-2">Campagnes suivies</div>
          <div className="text-2xl font-bold text-white">{campaigns.length}</div>
        </div>
        <div className="bg-[#111] border border-[#222] rounded-2xl p-5">
          <div className="text-xs font-medium text-[#666] uppercase tracking-wider mb-2">Collecté (HelloAsso)</div>
          <div className="text-2xl font-bold text-[#F2C48D]">{formatEuros(totalCollected)}</div>
        </div>
        <div className="bg-[#111] border border-[#222] rounded-2xl p-5">
          <div className="text-xs font-medium text-[#666] uppercase tracking-wider mb-2">Écarts à régulariser</div>
          <div className={`text-2xl font-bold ${toFix > 0 ? "text-[#FF8A5B]" : "text-[#00C853]"}`}>{toFix}</div>
        </div>
      </div>

      {campaigns.length === 0 ? (
        <EmptyState
          icon={RefreshCw}
          title="Aucune campagne synchronisée"
          description="Connecte-toi à HelloAsso puis lance une synchronisation pour voir tes cotisations, billetteries et dons, et les comparer à ta compta."
          ctaLabel={syncing ? "Synchronisation…" : "Rafraîchir maintenant"}
          onCta={refresh}
        />
      ) : (
        <div className="bg-[#111] border border-[#222] rounded-2xl overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-[#1a1a1a]">
                  <th className="px-5 py-3.5 text-left text-xs font-medium text-[#666] uppercase tracking-wider">Campagne</th>
                  <th className="px-5 py-3.5 text-left text-xs font-medium text-[#666] uppercase tracking-wider">Type</th>
                  <th className="px-5 py-3.5 text-right text-xs font-medium text-[#666] uppercase tracking-wider">Collecté</th>
                  <th className="px-5 py-3.5 text-right text-xs font-medium text-[#666] uppercase tracking-wider">Enregistré</th>
                  <th className="px-5 py-3.5 text-right text-xs font-medium text-[#666] uppercase tracking-wider">Écart</th>
                  <th className="px-5 py-3.5 text-right text-xs font-medium text-[#666] uppercase tracking-wider">Action</th>
                </tr>
              </thead>
              <tbody>
                {campaigns.map((c, idx) => {
                  const gap = c.gap_cents;
                  const gapColor =
                    gap == null ? "text-[#555]" : gap === 0 ? "text-[#00C853]" : gap > 0 ? "text-[#FF8A5B]" : "text-[#FF5252]";
                  const gapText = gap == null ? "—" : (gap > 0 ? "+" : "") + formatEuros(gap);
                  return (
                    <tr key={`${c.form_type}/${c.form_slug}`} className={`hover:bg-[#1a1a1a] transition-colors ${idx > 0 ? "border-t border-[#1a1a1a]" : ""}`}>
                      <td className="px-5 py-3.5 font-medium text-white">{c.title || c.form_slug}</td>
                      <td className="px-5 py-3.5">
                        <span className="inline-flex px-2 py-0.5 rounded-full text-xs bg-[#1a1a1a] text-[#B0B0B0] border border-[#2a2a2a]">{typeLabel(c.form_type)}</span>
                      </td>
                      <td className="px-5 py-3.5 text-right font-semibold text-[#F2C48D] whitespace-nowrap">{formatEuros(c.collected_cents)}</td>
                      <td className="px-5 py-3.5 text-right text-[#B0B0B0] whitespace-nowrap">{money(c.recorded_cents)}</td>
                      <td className={`px-5 py-3.5 text-right font-semibold whitespace-nowrap ${gapColor}`}>{gapText}</td>
                      <td className="px-5 py-3.5 text-right">
                        {c.link == null ? (
                          <button
                            onClick={() => setEditingSlug(c.form_slug)}
                            className="inline-flex items-center gap-1.5 text-xs font-medium text-[#F2C48D] hover:text-[#e8b87a] transition-colors"
                          >
                            <Link2 size={13} /> Rattacher
                          </button>
                        ) : gap != null && gap !== 0 ? (
                          <div className="inline-flex items-center gap-3">
                            <button
                              onClick={() => setEditingSlug(c.form_slug)}
                              className="text-[#666] hover:text-white transition-colors"
                              title="Modifier le rattachement"
                            >
                              <Link2 size={13} />
                            </button>
                            <button
                              onClick={() => setAdjustingSlug(c.form_slug)}
                              disabled={syncing}
                              className="px-3 py-1.5 rounded-full text-xs font-semibold text-black bg-[#F2C48D] hover:bg-[#e8b87a] disabled:opacity-50 transition-colors"
                            >
                              Ajuster
                            </button>
                          </div>
                        ) : (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs bg-emerald-500/15 text-emerald-400 border border-emerald-500/30">
                            <CheckCircle2 size={11} /> Réglé
                          </span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {editingCampaign && (
        <LinkModal
          campaign={editingCampaign}
          categories={categories}
          entities={entities}
          onClose={() => setEditingSlug(null)}
          onSaved={async () => {
            setEditingSlug(null);
            await load();
          }}
        />
      )}

      {adjustingCampaign && (
        <AdjustModal
          campaign={adjustingCampaign}
          categories={categories}
          entities={entities}
          busy={syncing}
          onClose={() => setAdjustingSlug(null)}
          onConfirm={() => confirmAdjust(adjustingCampaign)}
        />
      )}
    </div>
  );
}

function Modal({ title, subtitle, onClose, children }: { title: string; subtitle?: string; onClose: () => void; children: React.ReactNode }) {
  return (
    <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4" onClick={onClose}>
      <div className="bg-[#111] border border-[#222] rounded-2xl p-6 w-full max-w-md" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-1">
          <h2 className="text-base font-semibold text-white">{title}</h2>
          <button onClick={onClose} className="text-[#666] hover:text-white transition-colors"><X size={18} /></button>
        </div>
        {subtitle && <p className="text-sm text-[#888] mb-5">{subtitle}</p>}
        {children}
      </div>
    </div>
  );
}

function ConfigForm({ onSaved }: { onSaved: () => void }) {
  const [clientId, setClientId] = useState("");
  const [clientSecret, setClientSecret] = useState("");
  const [slug, setSlug] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const save = async () => {
    setSaving(true);
    setError(null);
    try {
      await api.putHelloAssoConfig({ client_id: clientId, client_secret: clientSecret, organization_slug: slug });
      onSaved();
    } catch (e: any) {
      setError(e.message);
      setSaving(false);
    }
  };

  return (
    <div className="max-w-lg bg-[#111] border border-[#222] rounded-2xl p-6">
      <div className="flex items-center gap-3 mb-5">
        <div className="h-10 w-10 rounded-xl bg-[#F2C48D]/10 border border-[#F2C48D]/20 flex items-center justify-center text-[#F2C48D]">
          <KeyRound size={18} />
        </div>
        <div>
          <h2 className="text-base font-semibold text-white">Clé API HelloAsso</h2>
          <p className="text-xs text-[#666]">Espace admin de ton organisation, rubrique API / Intégrations.</p>
        </div>
      </div>
      {error && <div className="mb-4 bg-[#1a0a0a] border border-[#FF5252]/30 text-[#FF5252] rounded-xl p-3 text-sm">{error}</div>}
      <div className="space-y-4">
        <div>
          <label className={labelClass}>Identifiant (client_id)</label>
          <input className={inputClass} value={clientId} onChange={(e) => setClientId(e.target.value)} placeholder="ex : a1b2c3d4..." />
        </div>
        <div>
          <label className={labelClass}>Secret (client_secret)</label>
          <input type="password" className={inputClass} value={clientSecret} onChange={(e) => setClientSecret(e.target.value)} placeholder="••••••••" />
        </div>
        <div>
          <label className={labelClass}>Nom de l'organisation (slug)</label>
          <input className={inputClass} value={slug} onChange={(e) => setSlug(e.target.value)} placeholder="ex : bda-ens-paris-saclay" />
        </div>
        <div className="flex items-center gap-3 pt-1">
          <button
            onClick={save}
            disabled={saving || !clientId || !clientSecret || !slug}
            className="px-5 py-2.5 text-sm font-semibold text-black bg-[#F2C48D] rounded-full hover:bg-[#e8b87a] disabled:opacity-40 transition-colors"
          >
            {saving ? "Connexion…" : "Connecter"}
          </button>
          <span className="text-xs text-[#555]">Ta clé reste sur ta machine, jamais réaffichée.</span>
        </div>
      </div>
    </div>
  );
}

function LinkModal({
  campaign,
  categories,
  entities,
  onClose,
  onSaved,
}: {
  campaign: Campaign;
  categories: Category[];
  entities: Entity[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const internals = entities.filter((e) => e.type === "internal");
  const externals = entities.filter((e) => e.type === "external");
  const [categoryId, setCategoryId] = useState<string>(campaign.link?.category_id != null ? String(campaign.link.category_id) : "");
  const [toEntity, setToEntity] = useState<string>(
    campaign.link?.to_entity_id != null ? String(campaign.link.to_entity_id) : internals[0] ? String(internals[0].id) : ""
  );
  const [fromEntity, setFromEntity] = useState<string>(
    campaign.link?.from_entity_id != null ? String(campaign.link.from_entity_id) : externals[0] ? String(externals[0].id) : ""
  );
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const save = async () => {
    setSaving(true);
    setError(null);
    try {
      await api.putHelloAssoLink({
        form_type: campaign.form_type,
        form_slug: campaign.form_slug,
        category_id: categoryId ? Number(categoryId) : null,
        from_entity_id: Number(fromEntity),
        to_entity_id: Number(toEntity),
      });
      onSaved();
    } catch (e: any) {
      setError(e.message);
      setSaving(false);
    }
  };

  return (
    <Modal title="Rattacher la campagne" subtitle={`« ${campaign.title || campaign.form_slug} »`} onClose={onClose}>
      {error && <div className="mb-4 bg-[#1a0a0a] border border-[#FF5252]/30 text-[#FF5252] rounded-xl p-3 text-sm">{error}</div>}
      <div className="space-y-4">
        <div>
          <label className={labelClass}>Catégorie</label>
          <select className={inputClass} value={categoryId} onChange={(e) => setCategoryId(e.target.value)}>
            <option value="">— Aucune —</option>
            {categories.map((c) => (
              <option key={c.id} value={c.id}>{c.name}</option>
            ))}
          </select>
        </div>
        <div className="flex items-end gap-2">
          <div className="flex-1">
            <label className={labelClass}>De (contrepartie)</label>
            <select className={inputClass} value={fromEntity} onChange={(e) => setFromEntity(e.target.value)}>
              {externals.map((e) => (
                <option key={e.id} value={e.id}>{e.name}</option>
              ))}
            </select>
          </div>
          <ArrowRight size={16} className="text-[#555] mb-3 shrink-0" />
          <div className="flex-1">
            <label className={labelClass}>Vers (club)</label>
            <select className={inputClass} value={toEntity} onChange={(e) => setToEntity(e.target.value)}>
              {internals.map((e) => (
                <option key={e.id} value={e.id}>{e.name}</option>
              ))}
            </select>
          </div>
        </div>
        <div className="flex justify-end gap-3 pt-2">
          <button onClick={onClose} className="px-5 py-2.5 text-sm font-semibold text-white border border-[#333] rounded-full hover:border-[#444] hover:bg-[#1a1a1a] transition-colors">Annuler</button>
          <button
            onClick={save}
            disabled={saving || !fromEntity || !toEntity}
            className="px-5 py-2.5 text-sm font-semibold text-black bg-[#F2C48D] rounded-full hover:bg-[#e8b87a] disabled:opacity-40 transition-colors"
          >
            {saving ? "Enregistrement…" : "Enregistrer"}
          </button>
        </div>
      </div>
    </Modal>
  );
}

function AdjustModal({
  campaign,
  categories,
  entities,
  busy,
  onClose,
  onConfirm,
}: {
  campaign: Campaign;
  categories: Category[];
  entities: Entity[];
  busy: boolean;
  onClose: () => void;
  onConfirm: () => void;
}) {
  const gap = campaign.gap_cents ?? 0;
  const amount = Math.abs(gap);
  const link = campaign.link;
  const catName = link && link.category_id != null ? categories.find((c) => c.id === link.category_id)?.name ?? `#${link.category_id}` : "(sans catégorie)";
  const fromId = link ? (gap > 0 ? link.from_entity_id : link.to_entity_id) : null;
  const toId = link ? (gap > 0 ? link.to_entity_id : link.from_entity_id) : null;
  const entName = (id: number | null) => (id == null ? "—" : entities.find((e) => e.id === id)?.name ?? `#${id}`);

  const Row = ({ label, value }: { label: string; value: string }) => (
    <div className="flex items-center justify-between py-2 border-b border-[#1a1a1a] last:border-0">
      <span className="text-sm text-[#888]">{label}</span>
      <span className="text-sm text-white font-medium text-right">{value}</span>
    </div>
  );

  return (
    <Modal title="Créer l'ajustement" subtitle={`« ${campaign.title || campaign.form_slug} »`} onClose={onClose}>
      <p className="text-sm text-[#B0B0B0] mb-4">
        Une transaction va être créée dans ta compta pour combler l'écart. Vérifie le récapitulatif :
      </p>
      <div className="bg-[#0a0a0a] border border-[#222] rounded-xl px-4 py-2 mb-5">
        <Row label="Montant" value={formatEuros(amount)} />
        <Row label="Sens" value={`${entName(fromId)} → ${entName(toId)}`} />
        <Row label="Catégorie" value={catName} />
        <Row label="Date" value="aujourd'hui" />
      </div>
      <div className="flex justify-end gap-3">
        <button onClick={onClose} className="px-5 py-2.5 text-sm font-semibold text-white border border-[#333] rounded-full hover:border-[#444] hover:bg-[#1a1a1a] transition-colors">Annuler</button>
        <button
          onClick={onConfirm}
          disabled={busy}
          className="px-5 py-2.5 text-sm font-semibold text-black bg-[#F2C48D] rounded-full hover:bg-[#e8b87a] disabled:opacity-50 transition-colors"
        >
          {busy ? "Création…" : "Créer la transaction"}
        </button>
      </div>
    </Modal>
  );
}
