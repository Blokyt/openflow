import { NavLink } from "react-router-dom";
import { LayoutDashboard, ArrowLeftRight, Tags, PiggyBank, Repeat, TrendingUp, GitCompare, Receipt, Settings } from "lucide-react";

const navItems = [
  { to: "/dashboard", label: "Tableau de bord", icon: LayoutDashboard },
  { to: "/transactions", label: "Transactions", icon: ArrowLeftRight },
  { to: "/categories", label: "Catégories", icon: Tags },
  { to: "/budget", label: "Budget", icon: PiggyBank },
  { to: "/recurring", label: "Récurrences", icon: Repeat },
  { to: "/forecasting", label: "Prévisions", icon: TrendingUp },
  { to: "/bank-reconciliation", label: "Rapprochement", icon: GitCompare },
  { to: "/tax-receipts", label: "Recus fiscaux", icon: Receipt },
];

export default function Sidebar() {
  return (
    <aside className="w-60 bg-[#080808] border-r border-[#222] flex flex-col h-full flex-shrink-0">
      <div className="px-5 py-6 border-b border-[#222]">
        <span className="text-xl font-bold tracking-tight">
          <span className="text-white">Open</span>
          <span className="text-[#F2C48D]">Flow</span>
        </span>
      </div>
      <nav className="flex-1 py-4 px-3 space-y-0.5">
        {navItems.map(({ to, label, icon: Icon }) => (
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
