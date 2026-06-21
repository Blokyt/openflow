import { useCallback, useEffect, useState } from "react";
import { api } from "../../api";
import { useFiscalYear } from "../../core/FiscalYearContext";

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

const euros = (cents: number | null) =>
  cents == null ? "-" : (cents / 100).toLocaleString("fr-FR", { style: "currency", currency: "EUR" });

export default function HelloAssoPage() {
  const { selectedYear } = useFiscalYear();
  const [configured, setConfigured] = useState<boolean | null>(null);
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [entities, setEntities] = useState<Entity[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<string | null>(null);

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
    setLoading(true);
    setError(null);
    try {
      await api.syncHelloAsso(selectedYear.id);
      await load();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  const adjust = async (c: Campaign) => {
    if (!selectedYear) return;
    try {
      await api.adjustHelloAsso({
        form_type: c.form_type,
        form_slug: c.form_slug,
        fiscal_year_id: selectedYear.id,
      });
      await load();
    } catch (e: any) {
      setError(e.message);
    }
  };

  if (configured === false) {
    return (
      <div className="p-6">
        <h1 className="text-xl font-semibold mb-2">HelloAsso</h1>
        <ConfigForm onSaved={load} />
      </div>
    );
  }

  return (
    <div className="p-6">
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-xl font-semibold">HelloAsso</h1>
        <button onClick={refresh} disabled={loading} className="px-3 py-1.5 rounded bg-blue-600 text-white disabled:opacity-50">
          {loading ? "Synchronisation..." : "Rafraîchir"}
        </button>
      </div>
      {error && <div className="mb-3 text-red-600">{error}</div>}
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left border-b">
            <th className="py-2">Campagne</th>
            <th>Type</th>
            <th>Statut</th>
            <th className="text-right">Collecté</th>
            <th className="text-right">Enregistré</th>
            <th className="text-right">Écart</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {campaigns.map((c) => (
            <tr key={`${c.form_type}/${c.form_slug}`} className="border-b">
              <td className="py-2">{c.title}</td>
              <td>{c.form_type}</td>
              <td>{c.state}</td>
              <td className="text-right">{euros(c.collected_cents)}</td>
              <td className="text-right">{euros(c.recorded_cents)}</td>
              <td className="text-right">{euros(c.gap_cents)}</td>
              <td className="text-right">
                {c.link == null ? (
                  <button onClick={() => setEditing(c.form_slug)} className="text-blue-600">À rattacher</button>
                ) : c.gap_cents !== 0 ? (
                  <button onClick={() => adjust(c)} className="text-blue-600">Ajuster</button>
                ) : (
                  <span className="text-green-600">OK</span>
                )}
                {editing === c.form_slug && (
                  <LinkForm
                    campaign={c}
                    categories={categories}
                    entities={entities}
                    onClose={() => setEditing(null)}
                    onSaved={async () => {
                      setEditing(null);
                      await load();
                    }}
                  />
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {campaigns.length === 0 && !loading && (
        <p className="text-gray-500 mt-4">Aucune campagne en cache. Clique sur "Rafraîchir" pour synchroniser.</p>
      )}
    </div>
  );
}

function ConfigForm({ onSaved }: { onSaved: () => void }) {
  const [clientId, setClientId] = useState("");
  const [clientSecret, setClientSecret] = useState("");
  const [slug, setSlug] = useState("");
  const [error, setError] = useState<string | null>(null);

  const save = async () => {
    try {
      await api.putHelloAssoConfig({ client_id: clientId, client_secret: clientSecret, organization_slug: slug });
      onSaved();
    } catch (e: any) {
      setError(e.message);
    }
  };

  return (
    <div className="max-w-md space-y-3">
      <p className="text-gray-600">Configure ta clé API HelloAsso (espace admin de ton organisation, section API).</p>
      {error && <div className="text-red-600">{error}</div>}
      <input className="w-full border rounded px-2 py-1" placeholder="Identifiant (client_id)" value={clientId} onChange={(e) => setClientId(e.target.value)} />
      <input className="w-full border rounded px-2 py-1" placeholder="Secret (client_secret)" type="password" value={clientSecret} onChange={(e) => setClientSecret(e.target.value)} />
      <input className="w-full border rounded px-2 py-1" placeholder="Nom de l'organisation (slug)" value={slug} onChange={(e) => setSlug(e.target.value)} />
      <button onClick={save} className="px-3 py-1.5 rounded bg-blue-600 text-white">Enregistrer</button>
    </div>
  );
}

function LinkForm({
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
  const [categoryId, setCategoryId] = useState<string>("");
  const [toEntity, setToEntity] = useState<string>(internals[0] ? String(internals[0].id) : "");
  const [fromEntity, setFromEntity] = useState<string>(externals[0] ? String(externals[0].id) : "");

  const save = async () => {
    await api.putHelloAssoLink({
      form_type: campaign.form_type,
      form_slug: campaign.form_slug,
      category_id: categoryId ? Number(categoryId) : null,
      from_entity_id: Number(fromEntity),
      to_entity_id: Number(toEntity),
    });
    onSaved();
  };

  return (
    <div className="mt-2 p-3 border rounded bg-gray-50 text-left space-y-2">
      <div className="font-medium">Rattacher "{campaign.title}"</div>
      <select className="w-full border rounded px-2 py-1" value={categoryId} onChange={(e) => setCategoryId(e.target.value)}>
        <option value="">(Catégorie)</option>
        {categories.map((c) => (
          <option key={c.id} value={c.id}>{c.name}</option>
        ))}
      </select>
      <select className="w-full border rounded px-2 py-1" value={toEntity} onChange={(e) => setToEntity(e.target.value)}>
        {internals.map((e) => (
          <option key={e.id} value={e.id}>Club : {e.name}</option>
        ))}
      </select>
      <select className="w-full border rounded px-2 py-1" value={fromEntity} onChange={(e) => setFromEntity(e.target.value)}>
        {externals.map((e) => (
          <option key={e.id} value={e.id}>Contrepartie : {e.name}</option>
        ))}
      </select>
      <div className="flex gap-2">
        <button onClick={save} className="px-3 py-1 rounded bg-blue-600 text-white">Enregistrer</button>
        <button onClick={onClose} className="px-3 py-1 rounded border">Annuler</button>
      </div>
    </div>
  );
}
