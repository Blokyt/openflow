import { FormEvent, useEffect, useState } from "react";
import { api } from "../api";
import { useAuth } from "./AuthContext";

const inputClass =
  "w-full bg-[#0a0a0a] border border-[#222] rounded-xl px-4 py-2.5 text-sm text-white focus:outline-none focus:border-[#F2C48D] transition-colors placeholder-[#444]";

export default function InvitationPage() {
  const { reload } = useAuth();
  const token = new URLSearchParams(window.location.search).get("token") || "";
  const [email, setEmail] = useState<string | null>(null);
  const [invalid, setInvalid] = useState(false);
  const [displayName, setDisplayName] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!token) { setInvalid(true); return; }
    api.previewInvitation(token).then((r) => setEmail(r.email)).catch(() => setInvalid(true));
  }, [token]);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (password !== confirm) { setError("Les deux mots de passe ne correspondent pas"); return; }
    setBusy(true);
    setError(null);
    try {
      await api.acceptInvitation({ token, display_name: displayName, password });
      await reload();
      window.location.href = "/dashboard";
    } catch (err: any) {
      setError(err?.message || "Activation impossible");
    } finally {
      setBusy(false);
    }
  }

  if (invalid) {
    return (
      <div className="flex flex-col items-center justify-center h-screen bg-black gap-3 p-6 text-center">
        <p className="text-[#FF5252] font-semibold">Invitation invalide ou expirée</p>
        <p className="text-sm text-[#B0B0B0]">Demande un nouveau lien au trésorier du BDA.</p>
      </div>
    );
  }
  if (email === null) {
    return (
      <div className="flex items-center justify-center h-screen bg-black">
        <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-[#F2C48D]" />
      </div>
    );
  }
  return (
    <div className="flex items-center justify-center h-screen bg-black">
      <form onSubmit={onSubmit} className="w-full max-w-sm p-8 space-y-5">
        <div className="text-center space-y-1">
          <h1 className="text-2xl font-bold text-white">Bienvenue sur OpenFlow</h1>
          <p className="text-sm text-[#B0B0B0]">Active ton compte {email}</p>
        </div>
        <div className="space-y-3">
          <input required autoFocus value={displayName} onChange={(e) => setDisplayName(e.target.value)}
            placeholder="Ton prénom et nom"
            className={inputClass} />
          <input type="password" required minLength={10} value={password} onChange={(e) => setPassword(e.target.value)}
            placeholder="Mot de passe (10 caractères minimum)"
            className={inputClass} />
          <input type="password" required value={confirm} onChange={(e) => setConfirm(e.target.value)}
            placeholder="Confirme le mot de passe"
            className={inputClass} />
        </div>
        {error && <p className="text-sm text-[#FF5252]">{error}</p>}
        <button type="submit" disabled={busy}
          className="w-full px-4 py-2.5 text-sm font-semibold text-black bg-[#F2C48D] rounded-full hover:bg-[#e8b87a] transition-colors disabled:opacity-50">
          {busy ? "Activation..." : "Activer mon compte"}
        </button>
      </form>
    </div>
  );
}
