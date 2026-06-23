import { useCallback, useEffect, useState } from "react";
import { RefreshCw, KeyRound, Check, CheckCircle2, AlertCircle, X, RotateCcw } from "lucide-react";
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
  acknowledged_cents: number;
  pending_cents: number;
};

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

const TypeBadge = ({ t }: { t: string }) => (
  <span className="inline-flex px-2 py-0.5 rounded-full text-xs bg-[#1a1a1a] text-[#B0B0B0] border border-[#2a2a2a]">{typeLabel(t)}</span>
);

export default function HelloAssoPage() {
  const { selectedYear } = useFiscalYear();
  const [configured, setConfigured] = useState<boolean | null>(null);
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busySlug, setBusySlug] = useState<string | null>(null);
  const [showDone, setShowDone] = useState(false);

  const load = useCallback(async () => {
    if (!selectedYear) return;
    setLoading(true);
    setError(null);
    try {
      const cfg = await api.getHelloAssoConfig();
      setConfigured(cfg.configured);
      if (cfg.configured) {
        setCampaigns(await api.getHelloAssoCampaigns(selectedYear.id));
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

  const setAck = async (c: Campaign, ack: boolean) => {
    if (!selectedYear) return;
    setBusySlug(c.form_slug);
    setError(null);
    try {
      const body = { form_type: c.form_type, form_slug: c.form_slug, fiscal_year_id: selectedYear.id };
      if (ack) await api.acknowledgeHelloAsso(body);
      else await api.unacknowledgeHelloAsso(body);
      await load();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusySlug(null);
    }
  };

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

  const toTreat = campaigns.filter((c) => c.pending_cents > 0).sort((a, b) => b.pending_cents - a.pending_cents);
  const done = campaigns.filter((c) => c.pending_cents <= 0 && c.collected_cents > 0);
  const totalPending = toTreat.reduce((s, c) => s + c.pending_cents, 0);
  const totalCollected = campaigns.reduce((s, c) => s + c.collected_cents, 0);

  return (
    <div className="p-8">
      <div className="flex items-start justify-between mb-8 gap-4">
        <div>
          <h1 className="text-3xl font-bold text-white" style={{ letterSpacing: "-0.02em" }}>HelloAsso</h1>
          <p className="text-sm text-[#666] mt-1">
            Pointe ce que tu as enregistré dans ta compta. Une campagne réapparaît si HelloAsso encaisse davantage.
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
          <div className="text-xs font-medium text-[#666] uppercase tracking-wider mb-2">Reste à pointer</div>
          <div className={`text-2xl font-bold ${totalPending > 0 ? "text-[#FF8A5B]" : "text-[#00C853]"}`}>{formatEuros(totalPending)}</div>
        </div>
        <div className="bg-[#111] border border-[#222] rounded-2xl p-5">
          <div className="text-xs font-medium text-[#666] uppercase tracking-wider mb-2">Campagnes à traiter</div>
          <div className="text-2xl font-bold text-white">{toTreat.length}</div>
        </div>
        <div className="bg-[#111] border border-[#222] rounded-2xl p-5">
          <div className="text-xs font-medium text-[#666] uppercase tracking-wider mb-2">Collecté (exercice)</div>
          <div className="text-2xl font-bold text-[#F2C48D]">{formatEuros(totalCollected)}</div>
        </div>
      </div>

      {campaigns.length === 0 ? (
        <EmptyState
          icon={RefreshCw}
          title="Aucune campagne synchronisée"
          description="Lance une synchronisation pour récupérer tes cotisations, billetteries et dons encaissés sur HelloAsso pendant cet exercice."
          ctaLabel={syncing ? "Synchronisation…" : "Rafraîchir maintenant"}
          onCta={refresh}
        />
      ) : (
        <>
          {toTreat.length > 0 ? (
            <div className="bg-[#111] border border-[#222] rounded-2xl overflow-hidden">
              <div className="px-5 py-3 border-b border-[#1a1a1a] text-xs font-medium text-[#666] uppercase tracking-wider">À prendre en compte</div>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-[#1a1a1a]">
                      <th className="px-5 py-3 text-left text-xs font-medium text-[#666] uppercase tracking-wider">Campagne</th>
                      <th className="px-5 py-3 text-left text-xs font-medium text-[#666] uppercase tracking-wider">Type</th>
                      <th className="px-5 py-3 text-right text-xs font-medium text-[#666] uppercase tracking-wider">Collecté</th>
                      <th className="px-5 py-3 text-right text-xs font-medium text-[#666] uppercase tracking-wider">À pointer</th>
                      <th className="px-5 py-3 text-right text-xs font-medium text-[#666] uppercase tracking-wider"></th>
                    </tr>
                  </thead>
                  <tbody>
                    {toTreat.map((c, idx) => (
                      <tr key={`${c.form_type}/${c.form_slug}`} className={`hover:bg-[#1a1a1a] transition-colors ${idx > 0 ? "border-t border-[#1a1a1a]" : ""}`}>
                        <td className="px-5 py-3.5 font-medium text-white">{c.title || c.form_slug}</td>
                        <td className="px-5 py-3.5"><TypeBadge t={c.form_type} /></td>
                        <td className="px-5 py-3.5 text-right text-[#B0B0B0] whitespace-nowrap">{formatEuros(c.collected_cents)}</td>
                        <td className="px-5 py-3.5 text-right font-semibold text-[#FF8A5B] whitespace-nowrap">{formatEuros(c.pending_cents)}</td>
                        <td className="px-5 py-3.5 text-right">
                          <button
                            onClick={() => setAck(c, true)}
                            disabled={busySlug === c.form_slug}
                            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-semibold text-black bg-[#F2C48D] hover:bg-[#e8b87a] disabled:opacity-50 transition-colors"
                          >
                            <Check size={13} /> Pris en compte
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ) : (
            <div className="bg-[#111] border border-[#222] rounded-2xl p-8 text-center">
              <CheckCircle2 size={28} className="mx-auto text-[#00C853] mb-3" />
              <p className="text-white font-semibold">Tout est à jour</p>
              <p className="text-sm text-[#666] mt-1">Aucune campagne en attente. Clique sur Rafraîchir pour vérifier les nouveaux encaissements.</p>
            </div>
          )}

          {done.length > 0 && (
            <div className="mt-4">
              <button
                onClick={() => setShowDone((v) => !v)}
                className="text-sm text-[#666] hover:text-[#B0B0B0] transition-colors"
              >
                {showDone ? "Masquer" : "Voir"} les {done.length} campagne{done.length > 1 ? "s" : ""} déjà à jour
              </button>
              {showDone && (
                <div className="mt-3 bg-[#111] border border-[#222] rounded-2xl overflow-hidden">
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <tbody>
                        {done.map((c, idx) => (
                          <tr key={`${c.form_type}/${c.form_slug}`} className={`${idx > 0 ? "border-t border-[#1a1a1a]" : ""}`}>
                            <td className="px-5 py-3 font-medium text-[#B0B0B0]">{c.title || c.form_slug}</td>
                            <td className="px-5 py-3"><TypeBadge t={c.form_type} /></td>
                            <td className="px-5 py-3 text-right text-[#777] whitespace-nowrap">{formatEuros(c.collected_cents)}</td>
                            <td className="px-5 py-3">
                              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs bg-emerald-500/15 text-emerald-400 border border-emerald-500/30">
                                <CheckCircle2 size={11} /> À jour
                              </span>
                            </td>
                            <td className="px-5 py-3 text-right">
                              <button
                                onClick={() => setAck(c, false)}
                                disabled={busySlug === c.form_slug}
                                className="inline-flex items-center gap-1.5 text-xs text-[#666] hover:text-white disabled:opacity-50 transition-colors"
                                title="Annuler le pointage (la campagne réapparaîtra à traiter)"
                              >
                                <RotateCcw size={12} /> Annuler
                              </button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </div>
          )}
        </>
      )}
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
          <input className={inputClass} value={slug} onChange={(e) => setSlug(e.target.value)} placeholder="ex : bureau-des-arts-mines-paristech" />
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
