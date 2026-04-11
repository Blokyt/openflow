import { NavLink } from "react-router-dom";
import { LayoutDashboard, ArrowLeftRight, Tags, PiggyBank, Repeat, Settings } from "lucide-react";

const navItems = [
  { to: "/dashboard", label: "Tableau de bord", icon: LayoutDashboard },
  { to: "/transactions", label: "Transactions", icon: ArrowLeftRight },
  { to: "/categories", label: "Catégories", icon: Tags },
  { to: "/budget", label: "Budget", icon: PiggyBank },
  { to: "/recurring", label: "Récurrences", icon: Repeat },
];

export default function Sidebar() {
  return (
    <aside className="w-56 bg-white border-r border-gray-200 flex flex-col h-full shadow-sm">
      <div className="px-5 py-5 border-b border-gray-200">
        <span className="text-xl font-bold text-indigo-600 tracking-tight">OpenFlow</span>
      </div>
      <nav className="flex-1 py-4 px-2 space-y-1">
        {navItems.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                isActive
                  ? "bg-indigo-50 text-indigo-700"
                  : "text-gray-600 hover:bg-gray-100 hover:text-gray-900"
              }`
            }
          >
            <Icon size={18} />
            {label}
          </NavLink>
        ))}
      </nav>
      <div className="px-2 py-4 border-t border-gray-200">
        <NavLink
          to="/settings"
          className={({ isActive }) =>
            `flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
              isActive
                ? "bg-indigo-50 text-indigo-700"
                : "text-gray-600 hover:bg-gray-100 hover:text-gray-900"
            }`
          }
        >
          <Settings size={18} />
          Paramètres
        </NavLink>
      </div>
    </aside>
  );
}
