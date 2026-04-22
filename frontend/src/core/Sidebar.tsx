import { useState, useRef, useEffect } from "react";
import { NavLink } from "react-router-dom";
import {
  LayoutDashboard, ArrowLeftRight, Tags, PiggyBank, Repeat,
  TrendingUp, GitCompare, Receipt, Settings, FileText, RotateCcw,
  Building2, Users, Paperclip, MessageSquare, Download, Wallet,
  ShieldCheck, Bell, HandCoins, FileSpreadsheet, UsersRound,
  ChevronDown, GitBranch, Check, LogOut, Archive, FileUp, Activity,
} from "lucide-react";
import { useEntity } from "./EntityContext";
import { useAuth } from "./AuthContext";
import { Entity } from "../types";
import { MODULE_IDS_WITH_ROUTE } from "../routes";

// Map manifest icon names → React components
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
  "git-branch": GitBranch,
  "archive": Archive,
  "file-up": FileUp,
  "activity": Activity,
};

// Module ID → route path. Must match MODULE_ROUTES in ../routes.tsx.
// Keep only modules that actually have a React component — the MODULE_IDS_WITH_ROUTE
// filter in optionalModules hides any tab not listed here.
const MODULE_PATH_MAP: Record<string, string> = {
  dashboard: "/dashboard",
  transactions: "/transactions",
  categories: "/categories",
  entities: "/entities",
  budget: "/budget",
  tiers: "/tiers",
  reimbursements: "/reimbursements",
  invoices: "/invoices",
  multi_users: "/multi-users",
  backup: "/backup",
  smart_import: "/smart-import",
  system: "/system",
};

// Core modules: always shown, in fixed order
const CORE_IDS = ["dashboard", "transactions", "categories", "entities"];

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

// ─── Nav item component ─────────────────────────────────────────────────────

function NavItem({ to, label, icon: Icon, badge }: { to: string; label: string; icon: any; badge?: number }) {
  return (
    <NavLink
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
          <span className="flex-1">{label}</span>
          {badge !== undefined && badge > 0 && (
            <span className="text-[10px] font-semibold text-black bg-[#F2C48D] rounded-full px-1.5 py-0.5 min-w-[18px] text-center">
              {badge}
            </span>
          )}
        </>
      )}
    </NavLink>
  );
}

// ─── Sidebar ──────────────────────────────────────────────────────────────────

interface SidebarProps {
  activeModules: any[];
}

export default function Sidebar({ activeModules }: SidebarProps) {
  const { user, logout } = useAuth();
  const [pendingReimbursements, setPendingReimbursements] = useState(0);

  const reimbursementsActive = activeModules.some((m) => m.id === "reimbursements");
  useEffect(() => {
    if (!reimbursementsActive) return;
    let cancelled = false;
    fetch("/api/reimbursements/?status=pending")
      .then((r) => (r.ok ? r.json() : []))
      .then((d) => {
        if (!cancelled) setPendingReimbursements(Array.isArray(d) ? d.length : 0);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [reimbursementsActive]);

  const [budgetBadge, setBudgetBadge] = useState(0);
  const budgetActive = activeModules.some((m) => m.id === "budget");
  useEffect(() => {
    if (!budgetActive) return;
    let cancelled = false;
    (async () => {
      try {
        const r = await fetch("/api/budget/fiscal-years/current");
        if (!r.ok) return;
        const fy = await r.json();
        const v = await fetch(`/api/budget/view?fiscal_year_id=${fy.id}`);
        if (!v.ok) return;
        const data = await v.json();
        const count = (data.entities as any[]).filter(
          (e) => e.allocated_total > 0 && Math.abs(e.realized_total) / e.allocated_total >= 0.95
        ).length;
        if (!cancelled) setBudgetBadge(count);
      } catch {}
    })();
    return () => { cancelled = true; };
  }, [budgetActive]);

  // Build core nav items (fixed, always shown)
  const coreManifests = CORE_IDS
    .map((id) => activeModules.find((m) => m.id === id))
    .filter(Boolean);

  const coreItems = coreManifests.map((m: any) => ({
    to: MODULE_PATH_MAP[m.id] || `/${m.id}`,
    label: m.menu?.label || m.name,
    icon: ICON_MAP[m.menu?.icon] || LayoutDashboard,
  }));

  // Build optional module nav items (sorted by manifest menu.position)
  // Hard guarantee: only show modules that have BOTH a menu entry AND a
  // registered React route. Prevents ghost tabs when a backend module lacks
  // its frontend component. Complements the check.py invariant.
  const optionalModules = activeModules
    .filter((m) => !CORE_IDS.includes(m.id) && m.id !== "multi_users")
    .filter((m) => m.menu && MODULE_IDS_WITH_ROUTE.has(m.id))
    .sort((a, b) => (a.menu?.position ?? 99) - (b.menu?.position ?? 99));

  const optionalItems = optionalModules.map((m: any) => ({
    id: m.id,
    to: MODULE_PATH_MAP[m.id] || `/${m.id}`,
    label: m.menu?.label || m.name,
    icon: ICON_MAP[m.menu?.icon] || LayoutDashboard,
    badge:
      m.id === "reimbursements" ? pendingReimbursements :
      m.id === "budget" ? budgetBadge :
      undefined,
  }));

  // Multi-users shown only for admins, at the bottom
  const isAdmin = user?.role === "admin";
  const multiUsersActive = activeModules.some((m) => m.id === "multi_users");

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
        {/* Core modules */}
        {coreItems.map((item) => (
          <NavItem key={item.to} {...item} />
        ))}

        {/* Separator if there are optional modules */}
        {optionalItems.length > 0 && (
          <div className="!my-3 border-t border-[#1a1a1a]" />
        )}

        {/* Optional modules — each one = one sidebar entry */}
        {optionalItems.map((item) => (
          <NavItem key={item.to} {...item} />
        ))}
      </nav>

      {/* Bottom section: admin + settings + user */}
      <div className="px-3 pb-3 space-y-0.5 border-t border-[#222] pt-3">
        {isAdmin && multiUsersActive && (
          <NavItem to="/multi-users" label="Utilisateurs" icon={UsersRound} />
        )}
        <NavItem to="/settings" label="Paramètres" icon={Settings} />

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
