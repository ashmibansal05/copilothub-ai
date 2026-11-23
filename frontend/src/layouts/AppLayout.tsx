import { Bot, LogOut } from "lucide-react";
import { Link, NavLink, Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";

const links = [
  { to: "/dashboard", label: "Sessions" },
  { to: "/history", label: "History" },
  { to: "/analytics", label: "Analytics" },
  { to: "/settings", label: "Settings" },
];

const linkClass = ({ isActive }: { isActive: boolean }) =>
  `text-sm ${isActive ? "font-semibold text-brand-700" : "text-slate-600 hover:text-slate-900"}`;

export default function AppLayout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const handleLogout = async () => {
    await logout();
    navigate("/login", { replace: true });
  };

  return (
    <div className="min-h-screen">
      <a href="#main" className="skip-link">Skip to main content</a>
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex h-14 max-w-7xl items-center justify-between px-4">
          <div className="flex items-center gap-6">
            <Link to="/dashboard" className="flex items-center gap-2 font-bold">
              <Bot className="h-6 w-6 text-brand-600" /> CoPilotHub AI
            </Link>
            <nav aria-label="Main" className="hidden gap-4 sm:flex">
              {links.map((l) => <NavLink key={l.to} to={l.to} className={linkClass}>{l.label}</NavLink>)}
            </nav>
          </div>
          <div className="flex items-center gap-3">
            <div className="hidden text-right sm:block">
              <p className="text-sm font-medium leading-tight">{user?.full_name}</p>
              <p className="text-xs text-slate-500">@{user?.username}</p>
            </div>
            <button onClick={handleLogout} className="btn-secondary" aria-label="Log out">
              <LogOut className="h-4 w-4" />
              <span className="hidden sm:inline">Logout</span>
            </button>
          </div>
        </div>
        <nav aria-label="Main (mobile)" className="flex gap-4 overflow-x-auto border-t border-slate-100 px-4 py-2 sm:hidden">
          {links.map((l) => <NavLink key={l.to} to={l.to} className={linkClass}>{l.label}</NavLink>)}
        </nav>
      </header>
      <main id="main" tabIndex={-1} className="mx-auto max-w-7xl px-4 py-8 outline-none">
        <Outlet />
      </main>
    </div>
  );
}