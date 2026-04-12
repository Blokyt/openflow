import { useState } from "react";
import { useAuth } from "./AuthContext";

export default function Login() {
  const { login } = useAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await login(username, password);
    } catch (err: any) {
      setError(err.message || "Identifiants incorrects");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen bg-black flex items-center justify-center">
      <div className="bg-[#111] border border-[#222] rounded-2xl p-8 w-full max-w-sm">
        <h1
          className="text-2xl font-bold text-white mb-1 text-center"
          style={{ letterSpacing: "-0.02em" }}
        >
          <span className="text-white">Open</span>
          <span className="text-[#F2C48D]">Flow</span>
        </h1>
        <p className="text-[#666] text-sm text-center mb-6">Connexion</p>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-xs text-[#666] mb-1.5">Identifiant</label>
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="w-full bg-[#0a0a0a] border border-[#333] rounded-lg px-3 py-2.5 text-sm text-white focus:outline-none focus:border-[#F2C48D]"
              autoFocus
              required
            />
          </div>
          <div>
            <label className="block text-xs text-[#666] mb-1.5">Mot de passe</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full bg-[#0a0a0a] border border-[#333] rounded-lg px-3 py-2.5 text-sm text-white focus:outline-none focus:border-[#F2C48D]"
              required
            />
          </div>

          {error && <p className="text-[#FF5252] text-xs">{error}</p>}

          <button
            type="submit"
            disabled={loading}
            className="w-full bg-[#F2C48D] text-black font-medium rounded-lg py-2.5 text-sm hover:bg-[#e5b87e] transition-colors disabled:opacity-50"
          >
            {loading ? "Connexion..." : "Se connecter"}
          </button>
        </form>
      </div>
    </div>
  );
}
