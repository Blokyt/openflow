import EntityTree from "./modules/entities/EntityTree";
import TransactionList from "./modules/transactions/TransactionList";
import CategoryManager from "./modules/categories/CategoryManager";
import BudgetManager from "./modules/budget/BudgetManager";
import UserManager from "./modules/multi_users/UserManager";
import BackupManager from "./modules/backup/BackupManager";
import SmartImportPage from "./modules/smart_import/SmartImportPage";
import SystemPage from "./modules/system/SystemPage";
import TiersList from "./modules/tiers/TiersList";
import ReimbursementManager from "./modules/reimbursements/ReimbursementManager";
import InvoicesView from "./modules/invoices/InvoicesView";

export type ModuleRoute = { path: string; element: React.ReactNode };

export const MODULE_ROUTES: Record<string, ModuleRoute> = {
  transactions: { path: "/transactions", element: <TransactionList /> },
  categories: { path: "/categories", element: <CategoryManager /> },
  entities: { path: "/entities", element: <EntityTree /> },
  budget: { path: "/budget", element: <BudgetManager /> },
  tiers: { path: "/contacts", element: <TiersList /> },
  reimbursements: { path: "/reimbursements", element: <ReimbursementManager /> },
  multi_users: { path: "/multi-users", element: <UserManager /> },
  backup: { path: "/backup", element: <BackupManager /> },
  smart_import: { path: "/smart-import", element: <SmartImportPage /> },
  system: { path: "/system", element: <SystemPage /> },
  invoices: { path: "/invoices", element: <InvoicesView /> },
};

export const MODULE_IDS_WITH_ROUTE = new Set(Object.keys(MODULE_ROUTES));

// Table des emplacements intégrés (modules sans onglet dédié).
// Remplie dans la Task 11.
export const INTEGRATED_LOCATIONS: Record<string, string> = {
  annotations: "Détail d'une transaction → section Notes",
  attachments: "Détail d'une transaction → section Pièces jointes",
  export: "Page Transactions → boutons CSV/JSON en haut",
  audit: "Paramètres → section Journal d'audit",
  fec_export: "Paramètres → section Export FEC",
};
