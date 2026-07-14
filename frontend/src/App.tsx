import { useEffect, useState } from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { api } from "./api";
import Sidebar from "./core/Sidebar";
import Dashboard from "./core/Dashboard";
import Settings from "./core/Settings";
import ContextBar from "./core/ContextBar";
import { EntityProvider } from "./core/EntityContext";
import { FiscalYearProvider } from "./core/FiscalYearContext";
import { AuthProvider, useAuth } from "./core/AuthContext";
import { ToastProvider } from "./core/ToastContext";
import LoginPage from "./core/LoginPage";
import InvitationPage from "./core/InvitationPage";
import ResetPage from "./core/ResetPage";
import { MODULE_ROUTES } from "./routes";
import Spinner from "./core/Spinner";

function ErrorScreen({ message }: { message: string }) {
  return (
    <div className="flex flex-col items-center justify-center h-screen bg-black gap-4 p-6 text-center">
      <p className="text-alert font-semibold">Impossible de charger l'application</p>
      <p className="text-sm text-text-secondary max-w-md">{message}</p>
      <button
        onClick={() => window.location.reload()}
        className="px-4 py-2 text-sm font-semibold text-black bg-accent-sand rounded-full hover:bg-accent-sand transition-colors"
      >
        Réessayer
      </button>
    </div>
  );
}

function AppContent() {
  const [activeModules, setActiveModules] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const { isAdmin } = useAuth();

  useEffect(() => {
    api.getModules()
      .then(setActiveModules)
      .catch((e) => setError(e?.message || "Erreur réseau au chargement des modules."))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <Spinner />;
  if (error) return <ErrorScreen message={error} />;

  // Filtrage par rôle : un module dont le manifest a requires_admin: true
  // n'apparaît ni dans la sidebar ni dans les routes pour un non-admin.
  const visibleModules = activeModules.filter((m: any) => isAdmin || !m.requires_admin);
  const activeModuleIds = visibleModules.map((m: any) => m.id);

  return (
    <BrowserRouter>
      <FiscalYearProvider>
        <EntityProvider>
          <div className="flex h-screen bg-black">
            <Sidebar activeModules={visibleModules} />
            <div className="flex-1 flex flex-col overflow-hidden">
              <ContextBar />
              <main className="flex-1 overflow-auto bg-black">
                <Routes>
                  <Route path="/" element={<Navigate to="/dashboard" replace />} />
                  <Route path="/dashboard" element={<Dashboard />} />
                  {Object.entries(MODULE_ROUTES).map(([moduleId, route]) =>
                    activeModuleIds.includes(moduleId) ? (
                      <Route key={moduleId} path={route.path} element={route.element} />
                    ) : null
                  )}
                  <Route path="/tiers" element={<Navigate to="/contacts" replace />} />
                  <Route path="/settings" element={<Settings />} />
                  <Route path="*" element={<Navigate to="/dashboard" replace />} />
                </Routes>
              </main>
            </div>
          </div>
        </EntityProvider>
      </FiscalYearProvider>
    </BrowserRouter>
  );
}

function AuthGate() {
  const { user, loading } = useAuth();
  if (window.location.pathname === "/reset") return <ResetPage />;
  if (window.location.pathname === "/invitation") return <InvitationPage />;
  if (loading) return <Spinner />;
  if (!user) return <LoginPage />;
  return <AppContent />;
}

export default function App() {
  return (
    <AuthProvider>
      <ToastProvider>
        <AuthGate />
      </ToastProvider>
    </AuthProvider>
  );
}
