
import { Bot, LogOut } from "lucide-react";
import { Link, Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";

export default function AppLayout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const handleLogout = async () => {
    await logout();
    navigate("/login", { replace: true });
  };

  return (
    <div className="min-h-screen">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex h-14 max-w-6xl items-center justify-between px-4">
          {/* Brand and navigation */}
          <div className="flex items-center">
            <Link
              to="/dashboard"
              className="flex items-center gap-2 font-bold"
            >
              <Bot className="h-6 w-6 text-brand-600" />
              CoPilotHub AI
            </Link>

            {/* Phase 14 - Navigation */}
            <nav
              className="ml-6 hidden gap-4 text-sm sm:flex"
              aria-label="Main navigation"
            >
              <Link
                to="/dashboard"
                className="text-slate-600 hover:text-slate-900"
              >
                Sessions
              </Link>

              <Link
                to="/analytics"
                className="text-slate-600 hover:text-slate-900"
              >
                Analytics
              </Link>
            </nav>
          </div>

          {/* User profile and logout */}
          <div className="flex items-center gap-3">
            <div className="hidden text-right sm:block">
              <p className="text-sm font-medium leading-tight">
                {user?.full_name}
              </p>
              <p className="text-xs text-slate-500">
                @{user?.username}
              </p>
            </div>

            <button
              onClick={handleLogout}
              className="btn-secondary"
              aria-label="Log out"
            >
              <LogOut className="h-4 w-4" />
              <span className="hidden sm:inline">
                Logout
              </span>
            </button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-7xl px-4 py-8">
        <Outlet />
      </main>
    </div>
  );
}