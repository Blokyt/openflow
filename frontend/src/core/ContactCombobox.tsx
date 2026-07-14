import { useEffect, useRef, useState } from "react";
import { UserPlus, X } from "lucide-react";
import { api } from "../api";
import { Contact } from "../types";
import { inputClass } from "./formStyles";
import useDebounce from "../utils/useDebounce";

export const CONTACT_TYPES: { value: string; label: string }[] = [
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
  const debouncedSearch = useDebounce(search, 250);
  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    api.searchContacts(debouncedSearch)
      .then((items) => { if (!cancelled) setResults(items); })
      .catch(() => { if (!cancelled) setResults([]); });
    return () => { cancelled = true; };
  }, [debouncedSearch, open]);

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
        <div className="flex items-center justify-between bg-[#0a0a0a] border border-border rounded-xl px-3 py-2.5">
          <span className="text-sm text-white">{selectedName ?? "…"}</span>
          <button
            type="button"
            onClick={clearContact}
            aria-label="Retirer le contact"
            title="Retirer le contact"
            className="text-[#555] hover:text-alert transition-colors ml-2"
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
        <div className="absolute z-50 mt-1 w-full bg-bg-card border border-border rounded-xl shadow-xl overflow-hidden max-h-52 overflow-y-auto">
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
              className="w-full text-left px-3 py-2 text-sm text-accent-sand hover:bg-[#1a1a1a] transition-colors flex items-center gap-2 border-t border-[#1a1a1a]"
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
                className="w-full bg-[#0a0a0a] border border-border-hover rounded-lg px-2 py-1.5 text-sm text-white focus:outline-none focus:border-accent-sand placeholder-text-muted"
                autoFocus
                onKeyDown={(e) => { if (e.key === "Enter" && !saving) { e.preventDefault(); handleCreate(); } }}
              />
              <select
                value={newType}
                onChange={(e) => setNewType(e.target.value)}
                className="w-full bg-[#0a0a0a] border border-border-hover rounded-lg px-2 py-1.5 text-sm text-white focus:outline-none focus:border-accent-sand"
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
                  className="flex-1 px-3 py-1.5 text-xs font-semibold text-black bg-accent-sand rounded-full hover:bg-accent-sand disabled:opacity-50 transition-colors"
                >
                  {saving ? "Création..." : "Créer"}
                </button>
                <button
                  type="button"
                  onMouseDown={() => setCreating(false)}
                  className="px-3 py-1.5 text-xs text-[#8a8a8a] border border-border-hover rounded-full hover:text-white transition-colors"
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
