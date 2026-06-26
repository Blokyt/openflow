import { useEffect, useState } from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { api } from "./api";
import Sidebar from "./core/Sidebar";
import Dashboard from "./core/Dashboard";
import Settings from "./core/Settings";
import ContextBar from "./core/ContextBar";
import { EntityProvider } from "./core/EntityContext";
import { FiscalYearProvider } from "./core/FiscalYearContext";
import { MODULE_ROUTES } from "./routes";

function Spinner() {
  return (
    <div className="flex items-center justify-center h-screen bg-black">
      <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-[#F2C48D]" />
    </div>
  );
}

function ErrorScreen({ message }: { message: string }) {
  return (
    <div className="flex flex-col items-center justify-center h-screen bg-black gap-4 p-6 text-center">
      <p className="text-[#FF5252] font-semibold">Impossible de charger l'application</p>
      <p className="text-sm text-[#B0B0B0] max-w-md">{message}</p>
      <button
        onClick={() => window.location.reload()}
        className="px-4 py-2 text-sm font-semibold text-black bg-[#F2C48D] rounded-full hover:bg-[#e8b87a] transition-colors"
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

  useEffect(() => {
    api.getModules()
      .then(setActiveModules)
      .catch((e) => setError(e?.message || "Erreur réseau au chargement des modules."))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <Spinner />;
  if (error) return <ErrorScreen message={error} />;

  const activeModuleIds = activeModules.map((m: any) => m.id);

  return (
    <BrowserRouter>
      <FiscalYearProvider>
        <EntityProvider>
          <div className="flex h-screen bg-black">
            <Sidebar activeModules={activeModules} />
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

export default function App() {
  return <AppContent />;
}
