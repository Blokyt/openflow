import EntityTree from "./modules/entities/EntityTree";
import TransactionList from "./modules/transactions/TransactionList";
import CategoryManager from "./modules/categories/CategoryManager";
import BudgetManager from "./modules/budget/BudgetManager";
import BackupManager from "./modules/backup/BackupManager";
import SystemPage from "./modules/system/SystemPage";
import TiersList from "./modules/tiers/TiersList";
import ReimbursementManager from "./modules/reimbursements/ReimbursementManager";

export type ModuleRoute = { path: string; element: React.ReactNode };

export const MODULE_ROUTES: Record<string, ModuleRoute> = {
  transactions: { path: "/transactions", element: <TransactionList /> },
  categories: { path: "/categories", element: <CategoryManager /> },
  entities: { path: "/entities", element: <EntityTree /> },
  budget: { path: "/budget", element: <BudgetManager /> },
  tiers: { path: "/contacts", element: <TiersList /> },
  reimbursements: { path: "/reimbursements", element: <ReimbursementManager /> },
  backup: { path: "/backup", element: <BackupManager /> },
  system: { path: "/system", element: <SystemPage /> },
};

export const MODULE_IDS_WITH_ROUTE = new Set(Object.keys(MODULE_ROUTES));

// Table des emplacements intégrés (modules sans onglet dédié).
export const INTEGRATED_LOCATIONS: Record<string, string> = {
  attachments: "Détail d'une transaction → section Pièces jointes",
};
