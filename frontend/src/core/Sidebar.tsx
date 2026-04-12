import { useState, useRef, useEffect } from "react";
import { NavLink } from "react-router-dom";
import {
  LayoutDashboard, ArrowLeftRight, Tags, PiggyBank, Repeat,
  TrendingUp, GitCompare, Receipt, Settings, FileText, RotateCcw,
  Building2, Users, Paperclip, MessageSquare, Download, Wallet,
  ShieldCheck, Bell, HandCoins, FileSpreadsheet, UsersRound,
  ChevronDown, GitBranch, Check, LogOut,
} from "lucide-react";
import { useEntity } from "./EntityContext";
import { useAuth } from "./AuthContext";
import { Entity } from "../types";

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

// ─── Entity selector dropdown ─────────────────────────────────────────────────

function EntitySelectorOption({
  entity,
  depth,
  selectedId,
  onSelect,
}: {
  entity: Entity;
  depth: number;
  selectedId: number | null;
  onSelect: (id: number) => void;
}) {
  return (
    <>
      <button
        className="w-full flex items-center gap-2 px-3 py-1.5 text-sm hover:bg-[#1a1a1a] transition-colors text-left"
        style={{ paddingLeft: `${12 + depth * 14}px` }}
        onClick={() => onSelect(entity.id)}
      >
        <span
          className="w-2 h-2 rounded-full flex-shrink-0"
          style={{ backgroundColor: entity.color || "#F2C48D" }}
        />
        <span className={`flex-1 truncate ${selectedId === entity.id ? "text-[#F2C48D]" : "text-[#B0B0B0]"}`}>
          {entity.name}
        </span>
        {selectedId === entity.id && <Check size={12} className="text-[#F2C48D] flex-shrink-0" />}
      </button>
      {entity.children?.map((child) => (
        <EntitySelectorOption
          key={child.id}
          entity={child}
          depth={depth + 1}
          selectedId={selectedId}
          onSelect={onSelect}
        />
      ))}
    </>
  );
}

function EntitySelector() {
  const { entities, selectedEntityId, selectedEntity, setSelectedEntityId } = useEntity();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  // Close on outside click
  useEffect(() => {
    function handler(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    if (open) document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  function handleSelect(id: number) {
    setSelectedEntityId(id);
    setOpen(false);
  }

  function handleClear(e: React.MouseEvent) {
    e.stopPropagation();
    setSelectedEntityId(null);
    setOpen(false);
  }

  if (entities.length === 0) return null;

  return (
    <div ref={ref} className="relative px-3 pb-3">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center gap-2 px-3 py-2 rounded-lg bg-[#111] border border-[#222] hover:border-[#333] transition-colors text-sm"
      >
        <GitBranch size={13} className="text-[#F2C48D] flex-shrink-0" strokeWidth={1.5} />
        <span className="flex-1 truncate text-left text-[#B0B0B0]">
          {selectedEntity ? selectedEntity.name : "Toutes les entités"}
        </span>
        <ChevronDown
          size={13}
          className={`text-[#555] transition-transform flex-shrink-0 ${open ? "rotate-180" : ""}`}
        />
      </button>

      {open && (
        <div className="absolute left-3 right-3 top-full mt-1 z-50 bg-[#111] border border-[#222] rounded-xl shadow-xl overflow-hidden">
          {/* All entities option */}
          <button
            className="w-full flex items-center gap-2 px-3 py-2 text-sm hover:bg-[#1a1a1a] transition-colors text-left border-b border-[#1a1a1a]"
            onClick={handleClear}
          >
            <span className="flex-1 text-[#666]">Toutes les entités</span>
            {selectedEntityId === null && <Check size={12} className="text-[#F2C48D]" />}
          </button>

          <div className="max-h-48 overflow-y-auto py-1">
            {entities.map((e) => (
              <EntitySelectorOption
                key={e.id}
                entity={e}
                depth={0}
                selectedId={selectedEntityId}
                onSelect={handleSelect}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Sidebar ──────────────────────────────────────────────────────────────────

interface SidebarProps {
  activeModuleIds: string[];
}

export default function Sidebar({ activeModuleIds }: SidebarProps) {
  const { user, logout } = useAuth();

  const navItems = [
    // Dashboard always first
    { to: "/dashboard", label: "Tableau de bord", icon: LayoutDashboard },
    // Transactions and categories are core, always shown
    { to: "/transactions", label: "Transactions", icon: ArrowLeftRight },
    { to: "/categories", label: "Catégories", icon: Tags },
    // Entities always shown
    { to: "/entities", label: "Entités", icon: GitBranch },
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

  // Show Users link only to admins when multi_users is active
  const isAdmin = user?.role === "admin";
  const multiUsersActive = activeModuleIds.includes("multi_users");

  const allItems = [...navItems, ...moduleNavItems];

  return (
    <aside className="w-60 bg-[#080808] border-r border-[#222] flex flex-col h-full flex-shrink-0">
      <div className="px-5 py-6 border-b border-[#222]">
        <span className="text-xl font-bold tracking-tight">
          <span className="text-white">Open</span>
          <span className="text-[#F2C48D]">Flow</span>
        </span>
      </div>
      <div className="pt-3 border-b border-[#1a1a1a]">
        <EntitySelector />
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
      <div className="px-3 pb-3 space-y-0.5 border-t border-[#222] pt-3">
        {isAdmin && multiUsersActive && (
          <NavLink
            to="/multi-users"
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
                <Users size={17} strokeWidth={1.5} />
                Utilisateurs
              </>
            )}
          </NavLink>
        )}
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

        {user && (
          <div className="mt-2 pt-2 border-t border-[#1a1a1a]">
            <div className="flex items-center justify-between px-3 py-2 rounded-lg bg-[#0a0a0a] border border-[#1a1a1a]">
              <div className="min-w-0">
                <p className="text-xs font-medium text-white truncate">
                  {user.display_name || user.username}
                </p>
                <p className="text-[10px] text-[#555] capitalize">{user.role}</p>
              </div>
              <button
                onClick={logout}
                className="text-[#555] hover:text-[#FF5252] transition-colors p-1 flex-shrink-0"
                title="Se déconnecter"
              >
                <LogOut size={14} strokeWidth={1.5} />
              </button>
            </div>
          </div>
        )}
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
