import { useEffect, useState, type ReactNode } from "react";
import { Link, useLocation } from "wouter";
import {
  Activity,
  ArrowUpFromLine,
  Building2,
  CreditCard,
  FolderOpen,
  LayoutDashboard,
  LogOut,
  PanelLeft,
  ScanEye,
  UserCog,
  UserPlus,
} from "lucide-react";
import { toast } from "sonner";
import { acknowledgeNotices } from "@/api/services";
import { getActiveNavHref } from "@/components/appShellNav";
import { cn } from "@/lib/utils";
import { useAuth } from "@/auth/AuthContext";

interface NavItem {
  href: string;
  label: string;
  icon: typeof LayoutDashboard;
}

const SIDEBAR_HIDDEN_STORAGE_KEY = "vizier_sidebar_hidden_v1";

function resolveEffectiveRole(
  effectiveRole: string | null | undefined,
  legacyRole: string | null | undefined,
) {
  if (effectiveRole) {
    return effectiveRole;
  }
  if (legacyRole === "CLINIC_ADMIN") {
    return "clinic_admin";
  }
  if (legacyRole === "CLINIC_DOCTOR") {
    return "clinic_doctor";
  }
  return "individual";
}

function buildNavItems(params: {
  effectiveRole: string;
  hasClinic: boolean;
  canAccessClinicMenu: boolean;
}): NavItem[] {
  const { effectiveRole, hasClinic, canAccessClinicMenu } = params;
  const items: NavItem[] = [
    { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
    { href: "/studies", label: "Clinical Cases", icon: FolderOpen },
  ];

  if (effectiveRole !== "clinic_admin") {
    items.push({
      href: "/studies/new",
      label: "Exam Upload",
      icon: ArrowUpFromLine,
    });
  }

  if (canAccessClinicMenu) {
    items.push({ href: "/clinic", label: "Clinic", icon: Building2 });
  }

  items.push({ href: "/invitations", label: "Invitations", icon: UserPlus });

  const canSeeIndividualBilling = effectiveRole === "individual" && !hasClinic;
  if (canSeeIndividualBilling) {
    items.push({ href: "/billing", label: "Billing", icon: CreditCard });
  }

  return items;
}

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
  const [location, navigate] = useLocation();
  const { accessToken, logout, refreshProfile, user } = useAuth();
  const [acknowledgingNoticeId, setAcknowledgingNoticeId] = useState<
    string | null
  >(null);
  const [isSidebarHidden, setIsSidebarHidden] = useState(false);
  const userInitials = getUserInitials(user?.full_name, user?.email);
  const effectiveRole = resolveEffectiveRole(user?.effective_role, user?.role);
  const isIndividualPaidSubscriber = Boolean(
    effectiveRole === "individual" &&
      !user?.clinic_id &&
      user?.subscription_plan &&
      user.subscription_plan !== "free",
  );
  const navItems = buildNavItems({
    effectiveRole,
    hasClinic: Boolean(user?.clinic_id),
    canAccessClinicMenu: !isIndividualPaidSubscriber,
  });
  const activeNavHref = getActiveNavHref(location, navItems);
  const pendingNotice = user?.notices?.[0] ?? null;

  useEffect(() => {
    try {
      const hiddenValue = window.localStorage.getItem(SIDEBAR_HIDDEN_STORAGE_KEY);
      setIsSidebarHidden(hiddenValue === "true");
    } catch {
      setIsSidebarHidden(false);
    }
  }, []);

  useEffect(() => {
    try {
      window.localStorage.setItem(
        SIDEBAR_HIDDEN_STORAGE_KEY,
        String(isSidebarHidden),
      );
    } catch {
      // Ignore storage failures and keep default behavior.
    }
  }, [isSidebarHidden]);

  async function handleAcknowledgeNotice(noticeId: string) {
    if (!accessToken) {
      return;
    }

    try {
      setAcknowledgingNoticeId(noticeId);
      await acknowledgeNotices(accessToken, [noticeId]);
      await refreshProfile();
    } catch (requestError) {
      toast.error(
        requestError instanceof Error
          ? requestError.message
          : "Falha ao confirmar aviso",
      );
    } finally {
      setAcknowledgingNoticeId(null);
    }
  }

  return (
    <div className="min-h-screen w-full bg-[linear-gradient(180deg,#1f2025,#1b1c22)] text-white">
      <div
        className={cn(
          "grid min-h-screen w-full transition-[grid-template-columns] duration-200",
          isSidebarHidden
            ? "lg:grid-cols-[56px_minmax(0,1fr)]"
            : "lg:grid-cols-[250px_minmax(0,1fr)]",
        )}
      >
        <aside
          className={cn(
            "hidden min-h-screen border-r border-white/6 bg-[linear-gradient(180deg,#2c2c31,#25262c)] lg:flex lg:flex-col",
          )}
        >
          {isSidebarHidden ? (
            <>
              <div className="flex w-full items-start justify-center px-2 py-4">
                <button
                  type="button"
                  onClick={() => setIsSidebarHidden(false)}
                  className="inline-flex h-10 w-10 items-center justify-center rounded-[10px] border border-white/8 bg-[#2a2b31] text-slate-200 transition hover:bg-[#32343c]"
                  aria-label="Mostrar menu"
                  title="Mostrar menu"
                >
                  <PanelLeft className="h-4.5 w-4.5 text-sky-400" />
                </button>
              </div>

              <nav className="flex flex-1 flex-col items-center gap-2 px-2 py-2">
                {navItems.map((item) => {
                  const Icon = item.icon;
                  const isActive = item.href === activeNavHref;

                  return (
                    <Link key={item.href} href={item.href}>
                      <a
                        aria-label={item.label}
                        title={item.label}
                        className={cn(
                          "flex h-10 w-10 shrink-0 items-center justify-center rounded-[10px] border transition",
                          isActive
                            ? "border-sky-300/30 bg-white/6 text-white shadow-[inset_0_0_0_1px_rgba(10,132,255,0.32)]"
                            : "border-white/8 bg-[#2a2b31] text-slate-300 hover:bg-[#32343c] hover:text-white",
                        )}
                      >
                        <Icon
                          className={cn(
                            "h-4.5 w-4.5",
                            isActive ? "text-sky-400" : "text-sky-500/90",
                          )}
                        />
                      </a>
                    </Link>
                  );
                })}
              </nav>

              <div className="px-2 py-4">
                <div className="flex flex-col items-center gap-2">
                  <button
                    type="button"
                    onClick={() => {
                      navigate("/profile");
                    }}
                    aria-label="Gerenciar perfil"
                    title="Gerenciar perfil"
                    className="flex h-10 w-10 items-center justify-center rounded-[10px] border border-white/8 bg-[#2a2b31] text-slate-300 transition hover:bg-[#32343c] hover:text-white"
                  >
                    <UserCog className="h-4.5 w-4.5 text-sky-400" />
                  </button>
                  <button
                    type="button"
                    onClick={() => logout(true)}
                    aria-label="Logout"
                    title="Logout"
                    className="flex h-10 w-10 items-center justify-center rounded-[10px] border border-white/8 bg-[#2a2b31] text-slate-300 transition hover:bg-[#32343c] hover:text-white"
                  >
                    <LogOut className="h-4.5 w-4.5 text-sky-400" />
                  </button>
                </div>
              </div>
            </>
          ) : (
            <>
              <div className="flex items-center justify-between gap-3 border-b border-white/6 px-4 py-4">
                <div className="flex items-center gap-3">
                  <div className="inline-flex h-9 w-9 items-center justify-center rounded-[12px] bg-sky-500/20 text-sky-200">
                    <ScanEye className="h-5 w-5" />
                  </div>
                  <div>
                    <p className="text-base font-semibold text-white">Vizier Med</p>
                    <p className="text-xs text-slate-400">Medical Assistance AI</p>
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => setIsSidebarHidden(true)}
                  className="inline-flex h-9 w-9 items-center justify-center rounded-[10px] border border-white/8 bg-[#2a2b31] text-slate-200 transition hover:bg-[#32343c]"
                  aria-label="Esconder menu"
                  title="Esconder menu"
                >
                  <PanelLeft className="h-4 w-4 text-sky-400" />
                </button>
              </div>

              <nav className="flex-1 space-y-1 px-3 py-5">
                {navItems.map((item) => {
                  const Icon = item.icon;
                  const isActive = item.href === activeNavHref;

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

                  {effectiveRole !== "clinic_doctor" ? (
                    <div className="flex items-center justify-between text-xs uppercase tracking-[0.16em] text-slate-500">
                      <span>Plan</span>
                      <span>{user?.subscription_plan || "free"}</span>
                    </div>
                  ) : null}

                  <button
                    type="button"
                    onClick={() => {
                      navigate("/profile");
                    }}
                    className="inline-flex w-full items-center justify-center gap-2 rounded-[10px] border border-white/8 bg-[#25262d] px-4 py-2.5 text-sm font-semibold text-slate-100 transition hover:bg-[#2e3038]"
                  >
                    <UserCog className="h-4 w-4 text-sky-400" />
                    Gerenciar perfil
                  </button>

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
            </>
          )}
        </aside>

        <div className="flex min-w-0 flex-col">
          <header className="border-b border-white/6 bg-[linear-gradient(180deg,#34353b,#2f3035)] px-4 py-4 md:px-6 lg:px-8">
            <div className="flex items-center justify-between gap-4">
              <div className="min-w-0">
                <p className="truncate text-xl font-semibold tracking-tight text-sky-500">
                  Workspace
                </p>
                <p className="mt-1 text-sm text-slate-400">
                  {user?.clinic_name || "Individual workspace"}
                </p>
              </div>

              <div className="flex items-center gap-3">
                <button
                  type="button"
                  onClick={() => {
                    navigate("/profile");
                  }}
                  className="inline-flex h-9 w-9 items-center justify-center rounded-[10px] border border-white/8 bg-[#2a2b31] text-slate-200 transition hover:bg-[#32343c] lg:hidden"
                  aria-label="Gerenciar perfil"
                  title="Gerenciar perfil"
                >
                  <UserCog className="h-4 w-4 text-sky-400" />
                </button>
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
                const isActive = item.href === activeNavHref;

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
            {pendingNotice ? (
              <div className="mb-5 rounded-2xl border border-amber-300/30 bg-amber-500/10 px-4 py-4">
                <p className="text-xs font-semibold uppercase tracking-[0.2em] text-amber-200">
                  {pendingNotice.title}
                </p>
                <p className="mt-2 text-sm text-amber-50">
                  {pendingNotice.message}
                </p>
                <button
                  type="button"
                  disabled={acknowledgingNoticeId === pendingNotice.id}
                  onClick={() => void handleAcknowledgeNotice(pendingNotice.id)}
                  className="mt-4 rounded-xl border border-amber-300/40 bg-amber-500/20 px-4 py-2 text-sm font-semibold text-amber-50 transition hover:bg-amber-500/30 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {acknowledgingNoticeId === pendingNotice.id
                    ? "Confirmando..."
                    : "Entendi"}
                </button>
              </div>
            ) : null}
            {children}
          </main>
        </div>
      </div>
    </div>
  );
}
