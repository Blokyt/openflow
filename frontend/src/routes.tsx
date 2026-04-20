import EntityTree from "./modules/entities/EntityTree";
import TransactionList from "./modules/transactions/TransactionList";
import CategoryManager from "./modules/categories/CategoryManager";
import BudgetManager from "./modules/budget/BudgetManager";
import RecurringManager from "./modules/recurring/RecurringManager";
import ForecastingView from "./modules/forecasting/ForecastingView";
import BankReconciliation from "./modules/bank_reconciliation/BankReconciliation";
import TaxReceiptsView from "./modules/tax_receipts/TaxReceiptsView";
import UserManager from "./modules/multi_users/UserManager";
import BackupManager from "./modules/backup/BackupManager";
import SmartImportPage from "./modules/smart_import/SmartImportPage";
import SystemPage from "./modules/system/SystemPage";
import TiersList from "./modules/tiers/TiersList";
import ReimbursementManager from "./modules/reimbursements/ReimbursementManager";
import GrantsView from "./modules/grants/GrantsView";

export type ModuleRoute = { path: string; element: React.ReactNode };

export const MODULE_ROUTES: Record<string, ModuleRoute> = {
  transactions: { path: "/transactions", element: <TransactionList /> },
  categories: { path: "/categories", element: <CategoryManager /> },
  entities: { path: "/entities", element: <EntityTree /> },
  budget: { path: "/budget", element: <BudgetManager /> },
  recurring: { path: "/recurring", element: <RecurringManager /> },
  forecasting: { path: "/forecasting", element: <ForecastingView /> },
  bank_reconciliation: { path: "/bank-reconciliation", element: <BankReconciliation /> },
  tax_receipts: { path: "/tax-receipts", element: <TaxReceiptsView /> },
  tiers: { path: "/tiers", element: <TiersList /> },
  reimbursements: { path: "/reimbursements", element: <ReimbursementManager /> },
  grants: { path: "/grants", element: <GrantsView /> },
  multi_users: { path: "/multi-users", element: <UserManager /> },
  backup: { path: "/backup", element: <BackupManager /> },
  smart_import: { path: "/smart-import", element: <SmartImportPage /> },
  system: { path: "/system", element: <SystemPage /> },
};

export const MODULE_IDS_WITH_ROUTE = new Set(Object.keys(MODULE_ROUTES));
