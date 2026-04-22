import { useEffect, useState } from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { api } from "./api";
import Sidebar from "./core/Sidebar";
import Dashboard from "./core/Dashboard";
import Settings from "./core/Settings";
import Login from "./core/Login";
import { AuthProvider, useAuth } from "./core/AuthContext";
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

function AppContent() {
  const { user, loading: authLoading } = useAuth();
  const [activeModules, setActiveModules] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.getModules()
      .then(setActiveModules)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  if (loading || authLoading) return <Spinner />;

  const activeModuleIds = activeModules.map((m: any) => m.id);

  const authRequired = activeModuleIds.includes("multi_users");
  if (authRequired && !user) return <Login />;

  return (
    <BrowserRouter>
      <FiscalYearProvider>
        <EntityProvider>
          <div className="flex h-screen bg-black">
            <Sidebar activeModules={activeModules} />
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
                <Route path="/multi_users" element={<Navigate to="/multi-users" replace />} />
                <Route path="/settings" element={<Settings />} />
                <Route path="*" element={<Navigate to="/dashboard" replace />} />
              </Routes>
            </main>
          </div>
        </EntityProvider>
      </FiscalYearProvider>
    </BrowserRouter>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <AppContent />
    </AuthProvider>
  );
}
