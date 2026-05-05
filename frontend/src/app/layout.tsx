import { NavLink, Outlet, useLocation } from "react-router-dom";
import { useAppStore } from "@/stores/appStore";
import {
  FlaskConical,
  TrendingUp,
  Settings2,
  ChevronLeft,
  ChevronRight,
  Thermometer,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { useEffect } from "react";

const NAV_ITEMS = [
  { to: "/", label: "Calibration", icon: FlaskConical, page: "calibration" as const },
  { to: "/prediction", label: "Prediction", icon: TrendingUp, page: "prediction" as const },
  { to: "/compressor", label: "Compressor", icon: Thermometer, page: "compressor" as const },
  { to: "/profiles", label: "Profiles", icon: Settings2, page: "profiles" as const },
];

export default function Layout() {
  const { sidebarCollapsed, toggleSidebar, setActivePage } = useAppStore();
  const location = useLocation();

  // Sync activePage with route
  useEffect(() => {
    const current = NAV_ITEMS.find((item) => item.to === location.pathname);
    if (current) {
      setActivePage(current.page);
    }
  }, [location.pathname, setActivePage]);

  return (
    <div className="flex h-screen overflow-hidden bg-background text-foreground">
      {/* Sidebar */}
      <aside
        className={`flex flex-col border-r border-border bg-card transition-all duration-200 ${
          sidebarCollapsed ? "w-14" : "w-56"
        }`}
      >
        {/* Logo / Title */}
        <div className="flex h-12 items-center border-b border-border px-3">
          {!sidebarCollapsed && (
            <span className="text-sm font-semibold tracking-tight truncate">
              Motor Thermal Model
            </span>
          )}
        </div>

        {/* Navigation */}
        <nav className="flex-1 space-y-1 px-2 py-3">
          {NAV_ITEMS.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                `flex items-center gap-2 rounded-md px-2 py-1.5 text-sm transition-colors ${
                  isActive
                    ? "bg-primary text-primary-foreground"
                    : "text-muted-foreground hover:bg-muted hover:text-foreground"
                } ${sidebarCollapsed ? "justify-center" : ""}`
              }
              title={label}
            >
              <Icon className="size-4 shrink-0" />
              {!sidebarCollapsed && <span>{label}</span>}
            </NavLink>
          ))}
        </nav>

        {/* Collapse toggle */}
        <div className="border-t border-border p-2">
          <Button
            variant="ghost"
            size="icon-sm"
            onClick={toggleSidebar}
            className="w-full"
            aria-label={sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"}
          >
            {sidebarCollapsed ? (
              <ChevronRight className="size-4" />
            ) : (
              <ChevronLeft className="size-4" />
            )}
          </Button>
        </div>
      </aside>

      {/* Main Content */}
      <main className="flex-1 overflow-y-auto">
        <Outlet />
      </main>
    </div>
  );
}
