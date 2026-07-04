import { FormEvent, useState } from "react";
import { useAuth } from "./AuthContext";

const inputClass =
  "w-full bg-[#0a0a0a] border border-[#222] rounded-xl px-4 py-2.5 text-sm text-white focus:outline-none focus:border-[#F2C48D] transition-colors placeholder-[#444]";

export default function LoginPage() {
  const { login } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(email, password);
    } catch (err: any) {
      setError(err?.message || "Connexion impossible");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex items-center justify-center h-screen bg-black">
      <form onSubmit={onSubmit} className="w-full max-w-sm p-8 space-y-5">
        <div className="text-center space-y-1">
          <h1 className="text-2xl font-bold text-white">OpenFlow</h1>
          <p className="text-sm text-[#B0B0B0]">Connecte-toi pour accéder à la trésorerie</p>
        </div>
        <div className="space-y-3">
          <input
            type="email"
            required
            autoFocus
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="Email"
            className={inputClass}
          />
          <input
            type="password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="Mot de passe"
            className={inputClass}
          />
        </div>
        {error && <p className="text-sm text-[#FF5252]">{error}</p>}
        <button
          type="submit"
          disabled={busy}
          className="w-full px-4 py-2.5 text-sm font-semibold text-black bg-[#F2C48D] rounded-full hover:bg-[#e8b87a] transition-colors disabled:opacity-50"
        >
          {busy ? "Connexion..." : "Se connecter"}
        </button>
      </form>
    </div>
  );
}
