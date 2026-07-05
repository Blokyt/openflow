import { lazy, Suspense } from "react";

// Pages chargées à la demande : le bundle initial ne contient que le shell
// et le dashboard ; chaque module n'est téléchargé qu'à la première visite.
const EntityTree = lazy(() => import("./modules/entities/EntityTree"));
const TransactionList = lazy(() => import("./modules/transactions/TransactionList"));
const CategoryManager = lazy(() => import("./modules/categories/CategoryManager"));
const BudgetManager = lazy(() => import("./modules/budget/BudgetManager"));
const BackupManager = lazy(() => import("./modules/backup/BackupManager"));
const SystemPage = lazy(() => import("./modules/system/SystemPage"));
const TiersList = lazy(() => import("./modules/tiers/TiersList"));
const ReimbursementManager = lazy(() => import("./modules/reimbursements/ReimbursementManager"));
const Reports = lazy(() => import("./modules/reports/index"));
const HelloAssoPage = lazy(() => import("./modules/helloasso/HelloAssoPage"));
const DirensPage = lazy(() => import("./modules/direns/index"));
const UsersAdmin = lazy(() => import("./modules/users/UsersAdmin"));
const SubmissionsPage = lazy(() => import("./modules/submissions/index"));

function Page({ children }: { children: React.ReactNode }) {
  return (
    <Suspense
      fallback={
        <div className="flex items-center justify-center h-full">
          <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-[#F2C48D]" />
        </div>
      }
    >
      {children}
    </Suspense>
  );
}

export type ModuleRoute = { path: string; element: React.ReactNode };

export const MODULE_ROUTES: Record<string, ModuleRoute> = {
  transactions: { path: "/transactions", element: <Page><TransactionList /></Page> },
  categories: { path: "/categories", element: <Page><CategoryManager /></Page> },
  entities: { path: "/entities", element: <Page><EntityTree /></Page> },
  budget: { path: "/budget", element: <Page><BudgetManager /></Page> },
  tiers: { path: "/contacts", element: <Page><TiersList /></Page> },
  reimbursements: { path: "/reimbursements", element: <Page><ReimbursementManager /></Page> },
  reports: { path: "/reports", element: <Page><Reports /></Page> },
  direns: { path: "/direns", element: <Page><DirensPage /></Page> },
  backup: { path: "/backup", element: <Page><BackupManager /></Page> },
  system: { path: "/system", element: <Page><SystemPage /></Page> },
  helloasso: { path: "/helloasso", element: <Page><HelloAssoPage /></Page> },
  users: { path: "/users", element: <Page><UsersAdmin /></Page> },
  submissions: { path: "/submissions", element: <Page><SubmissionsPage /></Page> },
};

export const MODULE_IDS_WITH_ROUTE = new Set(Object.keys(MODULE_ROUTES));

// Table des emplacements intégrés (modules sans onglet dédié).
export const INTEGRATED_LOCATIONS: Record<string, string> = {
  attachments: "Détail d'une transaction → section Pièces jointes",
};
