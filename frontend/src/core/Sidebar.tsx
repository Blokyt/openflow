import { NavLink } from "react-router-dom";
import {
  LayoutDashboard, ArrowLeftRight, Tags, PiggyBank, Repeat,
  TrendingUp, GitCompare, Receipt, Settings, FileText, RotateCcw,
  Building2, Users, Paperclip, MessageSquare, Download, Wallet,
  ShieldCheck, Bell, HandCoins, FileSpreadsheet, UsersRound,
} from "lucide-react";

const ICON_MAP: Record<string, any> = {
  "layout-dashboard": LayoutDashboard,
  "arrow-left-right": ArrowLeftRight,
  "tags": Tags,
  "piggy-bank": PiggyBank,
  "repeat": Repeat,
  "trending-up": TrendingUp,
  "git-compare": GitCompare,
  "receipt": Receipt,
  "file-text": FileText,
  "rotate-ccw": RotateCcw,
  "building-2": Building2,
  "users": Users,
  "paperclip": Paperclip,
  "message-square": MessageSquare,
  "download": Download,
  "wallet": Wallet,
  "shield-check": ShieldCheck,
  "bell": Bell,
  "hand-coins": HandCoins,
  "file-spreadsheet": FileSpreadsheet,
  "users-round": UsersRound,
};

const MODULE_PATH_MAP: Record<string, string> = {
  dashboard: "/dashboard",
  transactions: "/transactions",
  categories: "/categories",
  budget: "/budget",
  recurring: "/recurring",
  forecasting: "/forecasting",
  bank_reconciliation: "/bank-reconciliation",
  tax_receipts: "/tax-receipts",
  invoices: "/invoices",
  reimbursements: "/reimbursements",
  divisions: "/divisions",
  tiers: "/tiers",
  attachments: "/attachments",
  annotations: "/annotations",
  export: "/export",
  multi_accounts: "/multi-accounts",
  audit: "/audit",
  alerts: "/alerts",
  grants: "/grants",
  fec_export: "/fec-export",
  multi_users: "/multi-users",
};

// Modules that have a page (not just backend-only)
const MODULES_WITH_PAGES = new Set([
  "dashboard", "transactions", "categories", "budget", "recurring",
  "forecasting", "bank_reconciliation", "tax_receipts",
]);

interface SidebarProps {
  activeModuleIds: string[];
}

export default function Sidebar({ activeModuleIds }: SidebarProps) {
  const navItems = [
    // Dashboard always first
    { to: "/dashboard", label: "Tableau de bord", icon: LayoutDashboard },
    // Transactions and categories are core, always shown
    { to: "/transactions", label: "Transactions", icon: ArrowLeftRight },
    { to: "/categories", label: "Catégories", icon: Tags },
  ];

  // Add module pages that are active
  const moduleNavItems: { to: string; label: string; icon: any }[] = [];
  const moduleLabels: Record<string, string> = {
    budget: "Budget",
    recurring: "Récurrences",
    forecasting: "Prévisions",
    bank_reconciliation: "Rapprochement",
    tax_receipts: "Reçus fiscaux",
  };

  for (const modId of activeModuleIds) {
    if (["dashboard", "transactions", "categories"].includes(modId)) continue;
    if (!MODULES_WITH_PAGES.has(modId)) continue;
    const path = MODULE_PATH_MAP[modId];
    if (!path) continue;
    const icon = ICON_MAP[getModuleIcon(modId)] || LayoutDashboard;
    moduleNavItems.push({
      to: path,
      label: moduleLabels[modId] || modId,
      icon,
    });
  }

  const allItems = [...navItems, ...moduleNavItems];

  return (
    <aside className="w-60 bg-[#080808] border-r border-[#222] flex flex-col h-full flex-shrink-0">
      <div className="px-5 py-6 border-b border-[#222]">
        <span className="text-xl font-bold tracking-tight">
          <span className="text-white">Open</span>
          <span className="text-[#F2C48D]">Flow</span>
        </span>
      </div>
      <nav className="flex-1 py-4 px-3 space-y-0.5 overflow-y-auto">
        {allItems.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors relative ${
                isActive
                  ? "text-white bg-[#111]"
                  : "text-[#666] hover:bg-[#111] hover:text-white"
              }`
            }
          >
            {({ isActive }) => (
              <>
                {isActive && (
                  <span className="absolute left-0 top-1/2 -translate-y-1/2 w-0.5 h-5 bg-[#F2C48D] rounded-r" />
                )}
                <Icon size={17} strokeWidth={1.5} />
                {label}
              </>
            )}
          </NavLink>
        ))}
      </nav>
      <div className="px-3 py-4 border-t border-[#222]">
        <NavLink
          to="/settings"
          className={({ isActive }) =>
            `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors relative ${
              isActive
                ? "text-white bg-[#111]"
                : "text-[#666] hover:bg-[#111] hover:text-white"
            }`
          }
        >
          {({ isActive }) => (
            <>
              {isActive && (
                <span className="absolute left-0 top-1/2 -translate-y-1/2 w-0.5 h-5 bg-[#F2C48D] rounded-r" />
              )}
              <Settings size={17} strokeWidth={1.5} />
              Paramètres
            </>
          )}
        </NavLink>
      </div>
    </aside>
  );
}

function getModuleIcon(moduleId: string): string {
  const map: Record<string, string> = {
    budget: "piggy-bank",
    recurring: "repeat",
    forecasting: "trending-up",
    bank_reconciliation: "git-compare",
    tax_receipts: "receipt",
    invoices: "file-text",
    reimbursements: "rotate-ccw",
    divisions: "building-2",
    tiers: "users",
    attachments: "paperclip",
    annotations: "message-square",
    export: "download",
    multi_accounts: "wallet",
    audit: "shield-check",
    alerts: "bell",
    grants: "hand-coins",
    fec_export: "file-spreadsheet",
    multi_users: "users-round",
  };
  return map[moduleId] || "layout-dashboard";
}
