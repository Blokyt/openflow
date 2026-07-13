import { useEffect, useRef, useState } from "react";
import { UserPlus, X } from "lucide-react";
import { api } from "../api";
import { Contact } from "../types";

const inputClass = "w-full bg-[#0a0a0a] border border-[#222] rounded-xl px-3 py-2.5 text-sm text-white focus:outline-none focus:border-[#F2C48D] transition-colors placeholder-[#444] [color-scheme:dark]";

const CONTACT_TYPES: { value: string; label: string }[] = [
  { value: "membre", label: "Membre" },
  { value: "fournisseur", label: "Fournisseur" },
  { value: "client", label: "Client" },
  { value: "sponsor", label: "Sponsor" },
  { value: "other", label: "Autre" },
];

/** Sélecteur de contact (module tiers) avec recherche côté serveur.
 *
 * Partagé entre la saisie admin (TransactionForm) et le formulaire de
 * soumission. `allowCreate` contrôle la création de contact à la volée :
 * à désactiver pour les non-admins (POST /api/tiers/ est réservé à l'admin).
 */
export default function ContactCombobox({
  value,
  selectedName,
  onChange,
  onPick,
  placeholder,
  allowCreate = true,
}: {
  value: string;
  selectedName: string | null;
  onChange: (id: string) => void;
  onPick: (c: Contact) => void;
  placeholder: string;
  allowCreate?: boolean;
}) {
  const [search, setSearch] = useState("");
  const [results, setResults] = useState<Contact[]>([]);
  const [open, setOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState("");
  const [newType, setNewType] = useState("membre");
  const [saving, setSaving] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handle(e: MouseEvent) {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) {
        setOpen(false);
        setCreating(false);
      }
    }
    document.addEventListener("mousedown", handle);
    return () => document.removeEventListener("mousedown", handle);
  }, []);

  // Recherche côté serveur, temporisée : le carnet peut contenir des milliers
  // de contacts, on ne charge jamais la liste complète dans le navigateur.
  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    const t = setTimeout(() => {
      api.searchContacts(search)
        .then((items) => { if (!cancelled) setResults(items); })
        .catch(() => { if (!cancelled) setResults([]); });
    }, 250);
    return () => { cancelled = true; clearTimeout(t); };
  }, [search, open]);

  function selectContact(c: Contact) {
    onPick(c);
    onChange(String(c.id));
    setSearch("");
    setOpen(false);
    setCreating(false);
  }

  function clearContact() {
    onChange("");
    setSearch("");
  }

  async function handleCreate() {
    if (saving || !newName.trim()) return;
    setSaving(true);
    try {
      const created = await api.createContact({ name: newName.trim(), type: newType });
      onPick(created);
      onChange(String(created.id));
      setCreating(false);
      setNewName("");
      setOpen(false);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div ref={wrapRef} className="relative">
      {value ? (
        <div className="flex items-center justify-between bg-[#0a0a0a] border border-[#222] rounded-xl px-3 py-2.5">
          <span className="text-sm text-white">{selectedName ?? "…"}</span>
          <button
            type="button"
            onClick={clearContact}
            aria-label="Retirer le contact"
            title="Retirer le contact"
            className="text-[#555] hover:text-[#FF5252] transition-colors ml-2"
          >
            <X size={14} />
          </button>
        </div>
      ) : (
        <input
          type="text"
          value={search}
          onChange={(e) => { setSearch(e.target.value); setOpen(true); setCreating(false); }}
          onFocus={() => setOpen(true)}
          placeholder={placeholder}
          className={inputClass}
          autoComplete="off"
        />
      )}

      {open && !value && (
        <div className="absolute z-50 mt-1 w-full bg-[#111] border border-[#222] rounded-xl shadow-xl overflow-hidden max-h-52 overflow-y-auto">
          {results.length > 0 ? (
            results.map((c) => (
              <button
                key={c.id}
                type="button"
                onMouseDown={() => selectContact(c)}
                className="w-full text-left px-3 py-2 text-sm text-white hover:bg-[#1a1a1a] transition-colors flex items-center justify-between"
              >
                <span>{c.name}</span>
                <span className="text-xs text-[#555] ml-2">{c.type}</span>
              </button>
            ))
          ) : (
            <p className="px-3 py-2 text-sm text-[#555]">Aucun résultat</p>
          )}

          {allowCreate && (!creating ? (
            <button
              type="button"
              onMouseDown={() => { setCreating(true); setOpen(true); }}
              className="w-full text-left px-3 py-2 text-sm text-[#F2C48D] hover:bg-[#1a1a1a] transition-colors flex items-center gap-2 border-t border-[#1a1a1a]"
            >
              <UserPlus size={13} /> Créer un nouveau contact
            </button>
          ) : (
            <div className="border-t border-[#1a1a1a] p-3 space-y-2">
              <input
                type="text"
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                placeholder="Nom du contact"
                className="w-full bg-[#0a0a0a] border border-[#333] rounded-lg px-2 py-1.5 text-sm text-white focus:outline-none focus:border-[#F2C48D] placeholder-[#444]"
                autoFocus
                onKeyDown={(e) => { if (e.key === "Enter" && !saving) { e.preventDefault(); handleCreate(); } }}
              />
              <select
                value={newType}
                onChange={(e) => setNewType(e.target.value)}
                className="w-full bg-[#0a0a0a] border border-[#333] rounded-lg px-2 py-1.5 text-sm text-white focus:outline-none focus:border-[#F2C48D]"
              >
                {CONTACT_TYPES.map((t) => (
                  <option key={t.value} value={t.value}>{t.label}</option>
                ))}
              </select>
              <div className="flex gap-2">
                <button
                  type="button"
                  onMouseDown={handleCreate}
                  disabled={saving || !newName.trim()}
                  className="flex-1 px-3 py-1.5 text-xs font-semibold text-black bg-[#F2C48D] rounded-full hover:bg-[#e8b87a] disabled:opacity-50 transition-colors"
                >
                  {saving ? "Création..." : "Créer"}
                </button>
                <button
                  type="button"
                  onMouseDown={() => setCreating(false)}
                  className="px-3 py-1.5 text-xs text-[#8a8a8a] border border-[#333] rounded-full hover:text-white transition-colors"
                >
                  Annuler
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
