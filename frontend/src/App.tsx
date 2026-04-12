import { useEffect, useState } from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { api } from "./api";
import Sidebar from "./core/Sidebar";
import Dashboard from "./core/Dashboard";
import Settings from "./core/Settings";
import Login from "./core/Login";
import { AuthProvider, useAuth } from "./core/AuthContext";
import { EntityProvider } from "./core/EntityContext";
import EntityTree from "./modules/entities/EntityTree";
import TransactionList from "./modules/transactions/TransactionList";
import CategoryManager from "./modules/categories/CategoryManager";
import BudgetManager from "./modules/budget/BudgetManager";
import RecurringManager from "./modules/recurring/RecurringManager";
import ForecastingView from "./modules/forecasting/ForecastingView";
import BankReconciliation from "./modules/bank_reconciliation/BankReconciliation";
import TaxReceiptsView from "./modules/tax_receipts/TaxReceiptsView";
import UserManager from "./modules/multi_users/UserManager";

const MODULE_ROUTES: Record<string, { path: string; element: React.ReactNode }> = {
  transactions: { path: "/transactions", element: <TransactionList /> },
  categories: { path: "/categories", element: <CategoryManager /> },
  budget: { path: "/budget", element: <BudgetManager /> },
  recurring: { path: "/recurring", element: <RecurringManager /> },
  forecasting: { path: "/forecasting", element: <ForecastingView /> },
  bank_reconciliation: { path: "/bank-reconciliation", element: <BankReconciliation /> },
  tax_receipts: { path: "/tax-receipts", element: <TaxReceiptsView /> },
  entities: { path: "/entities", element: <EntityTree /> },
  multi_users: { path: "/multi-users", element: <UserManager /> },
};

function Spinner() {
  return (
    <div className="flex items-center justify-center h-screen bg-black">
      <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-[#F2C48D]" />
    </div>
  );
}

function AppContent() {
  const { user, loading: authLoading } = useAuth();
  const [activeModuleIds, setActiveModuleIds] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.getModules()
      .then((mods) => setActiveModuleIds(mods.map((m: any) => m.id)))
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  if (loading || authLoading) return <Spinner />;

  // If multi_users module is active and user is not logged in, show login page
  const authRequired = activeModuleIds.includes("multi_users");
  if (authRequired && !user) return <Login />;

  return (
    <BrowserRouter>
      <EntityProvider>
        <div className="flex h-screen bg-black">
          <Sidebar activeModuleIds={activeModuleIds} />
          <main className="flex-1 overflow-auto bg-black">
            <Routes>
              <Route path="/" element={<Navigate to="/dashboard" replace />} />
              <Route path="/dashboard" element={<Dashboard />} />
              <Route path="/entities" element={<EntityTree />} />
              {Object.entries(MODULE_ROUTES).map(([moduleId, route]) =>
                moduleId !== "entities" && activeModuleIds.includes(moduleId) ? (
                  <Route key={moduleId} path={route.path} element={route.element} />
                ) : null
              )}
              <Route path="/settings" element={<Settings />} />
            </Routes>
          </main>
        </div>
      </EntityProvider>
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
