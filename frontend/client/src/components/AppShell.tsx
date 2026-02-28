import type { ReactNode } from "react";
import { Link, useLocation } from "wouter";
import {
  Activity,
  ArrowUpFromLine,
  Building2,
  CreditCard,
  FolderOpen,
  LayoutDashboard,
  LogOut,
  ScanEye,
  UserPlus,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useAuth } from "@/auth/AuthContext";

const navItems = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/studies", label: "Clinical Cases", icon: FolderOpen },
  { href: "/studies/new", label: "Exam Upload", icon: ArrowUpFromLine },
  { href: "/clinic", label: "Clinic", icon: Building2 },
  { href: "/invitations", label: "Invitations", icon: UserPlus },
  { href: "/billing", label: "Billing", icon: CreditCard },
];

function getUserInitials(
  fullName: string | null | undefined,
  email: string | null | undefined,
) {
  const source = (fullName || email || "AI").trim();
  if (!source) {
    return "AI";
  }

  const parts = source.split(/\s+/).filter(Boolean);
  if (parts.length === 1) {
    return parts[0].slice(0, 2).toUpperCase();
  }

  return `${parts[0][0] || ""}${parts[1][0] || ""}`.toUpperCase();
}

export function AppShell({ children }: { children: ReactNode }) {
  const [location] = useLocation();
  const { logout, user } = useAuth();
  const userInitials = getUserInitials(user?.full_name, user?.email);

  return (
    <div className="min-h-screen w-full bg-[linear-gradient(180deg,#1f2025,#1b1c22)] text-white">
      <div className="grid min-h-screen w-full lg:grid-cols-[250px_minmax(0,1fr)]">
        <aside className="hidden min-h-screen border-r border-white/6 bg-[linear-gradient(180deg,#2c2c31,#25262c)] lg:flex lg:flex-col">
          <div className="flex items-center gap-3 border-b border-white/6 px-4 py-4">
            <div className="inline-flex h-9 w-9 items-center justify-center rounded-[12px] bg-sky-500/20 text-sky-200">
              <ScanEye className="h-5 w-5" />
            </div>
            <div>
              <p className="text-base font-semibold text-white">NeuroAI</p>
              <p className="text-xs text-slate-400">Clinical workspace</p>
            </div>
          </div>

          <nav className="flex-1 space-y-1 px-3 py-5">
            {navItems.map((item) => {
              const Icon = item.icon;
              const isActive =
                location === item.href || location.startsWith(`${item.href}/`);

              return (
                <Link key={item.href} href={item.href}>
                  <a
                    className={cn(
                      "flex items-center gap-3 rounded-[12px] px-3 py-3 text-sm font-medium transition",
                      isActive
                        ? "bg-white/6 text-white shadow-[inset_0_0_0_1px_rgba(10,132,255,0.32)]"
                        : "text-slate-300 hover:bg-white/4 hover:text-white",
                    )}
                  >
                    <Icon
                      className={cn(
                        "h-4.5 w-4.5",
                        isActive ? "text-sky-400" : "text-sky-500/90",
                      )}
                    />
                    <span>{item.label}</span>
                  </a>
                </Link>
              );
            })}
          </nav>

          <div className="border-t border-white/6 p-3">
            <div className="space-y-3 rounded-[14px] border border-white/8 bg-[#2f3036] p-4">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-400">
                    Session
                  </p>
                  <p className="mt-2 text-sm font-semibold text-white">
                    {user?.full_name || user?.email || "Authenticated user"}
                  </p>
                  <p className="mt-1 text-sm text-slate-400">
                    {user?.clinic_name || "No clinic linked"}
                  </p>
                </div>
                <div className="inline-flex h-9 w-9 items-center justify-center rounded-full bg-sky-500 text-xs font-semibold text-white">
                  {userInitials}
                </div>
              </div>

              <div className="flex items-center justify-between text-xs uppercase tracking-[0.16em] text-slate-500">
                <span>Plan</span>
                <span>{user?.subscription_plan || "free"}</span>
              </div>

              <button
                type="button"
                onClick={() => logout(true)}
                className="inline-flex w-full items-center justify-center gap-2 rounded-[10px] border border-white/8 bg-[#25262d] px-4 py-2.5 text-sm font-semibold text-slate-100 transition hover:bg-[#2e3038]"
              >
                <LogOut className="h-4 w-4 text-sky-400" />
                Logout
              </button>
            </div>
          </div>
        </aside>

        <div className="flex min-w-0 flex-col">
          <header className="border-b border-white/6 bg-[linear-gradient(180deg,#34353b,#2f3035)] px-4 py-4 md:px-6 lg:px-8">
            <div className="flex items-center justify-between gap-4">
              <div className="min-w-0">
                <p className="truncate text-xl font-semibold tracking-tight text-sky-500">
                  Clinical Neuro AI Platform
                </p>
                <p className="mt-1 text-sm text-slate-400">
                  {user?.clinic_name || "Individual workspace"}
                </p>
              </div>

              <div className="flex items-center gap-3">
                <div className="hidden items-center gap-2 rounded-[10px] border border-white/8 bg-[#2a2b31] px-3 py-2 text-xs font-semibold uppercase tracking-[0.16em] text-slate-300 md:inline-flex">
                  <Activity className="h-3.5 w-3.5 text-sky-400" />
                  System online
                </div>
                <div className="inline-flex h-9 w-9 items-center justify-center rounded-full bg-sky-500 text-sm font-semibold text-white">
                  {userInitials}
                </div>
              </div>
            </div>

            <nav className="mt-4 flex gap-2 overflow-x-auto pb-1 lg:hidden">
              {navItems.map((item) => {
                const Icon = item.icon;
                const isActive =
                  location === item.href ||
                  location.startsWith(`${item.href}/`);

                return (
                  <Link key={item.href} href={item.href}>
                    <a
                      className={cn(
                        "inline-flex items-center gap-2 rounded-[10px] border px-3 py-2 text-xs font-semibold uppercase tracking-[0.14em] whitespace-nowrap transition",
                        isActive
                          ? "border-sky-300/30 bg-sky-500/12 text-white"
                          : "border-white/8 bg-[#2a2b31] text-slate-300 hover:bg-[#32343c]",
                      )}
                    >
                      <Icon className="h-3.5 w-3.5 text-sky-400" />
                      {item.label}
                    </a>
                  </Link>
                );
              })}
            </nav>
          </header>

          <main className="min-w-0 flex-1 bg-[linear-gradient(180deg,#23242a,#1e1f25)] px-4 py-5 md:px-6 lg:px-8 lg:py-7">
            {children}
          </main>
        </div>
      </div>
    </div>
  );
}
