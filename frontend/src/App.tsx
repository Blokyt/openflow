import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import Sidebar from "./core/Sidebar";
import Dashboard from "./core/Dashboard";
import Settings from "./core/Settings";
import TransactionList from "./modules/transactions/TransactionList";
import CategoryManager from "./modules/categories/CategoryManager";
import BudgetManager from "./modules/budget/BudgetManager";
import RecurringManager from "./modules/recurring/RecurringManager";
import ForecastingView from "./modules/forecasting/ForecastingView";
import BankReconciliation from "./modules/bank_reconciliation/BankReconciliation";

export default function App() {
  return (
    <BrowserRouter>
      <div className="flex h-screen bg-gray-50">
        <Sidebar />
        <main className="flex-1 overflow-auto">
          <Routes>
            <Route path="/" element={<Navigate to="/dashboard" replace />} />
            <Route path="/dashboard" element={<Dashboard />} />
            <Route path="/transactions" element={<TransactionList />} />
            <Route path="/categories" element={<CategoryManager />} />
            <Route path="/budget" element={<BudgetManager />} />
            <Route path="/recurring" element={<RecurringManager />} />
            <Route path="/forecasting" element={<ForecastingView />} />
            <Route path="/bank-reconciliation" element={<BankReconciliation />} />
            <Route path="/settings" element={<Settings />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  );
}
