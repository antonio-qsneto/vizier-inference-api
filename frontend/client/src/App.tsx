import { useEffect } from "react";
import { Route, Switch, useLocation } from "wouter";
import { Toaster } from "sonner";
import ErrorBoundary from "@/components/ErrorBoundary";
import { AppShell } from "@/components/AppShell";
import { LoadingState } from "@/components/primitives";
import { AuthProvider, useAuth } from "@/auth/AuthContext";
import AuthCallbackPage from "@/pages/AuthCallbackPage";
import BillingPage from "@/pages/BillingPage";
import BillingResultPage from "@/pages/BillingResultPage";
import ClinicPage from "@/pages/ClinicPage";
import DashboardPage from "@/pages/DashboardPage";
import InvitationsPage from "@/pages/InvitationsPage";
import LoginPage from "@/pages/LoginPage";
import NotFoundPage from "@/pages/NotFoundPage";
import StudyDetailPage from "@/pages/StudyDetailPage";
import StudiesPage from "@/pages/StudiesPage";
import StudyUploadPage from "@/pages/StudyUploadPage";
import StudyViewerPage from "@/pages/StudyViewerPage";

function AuthGate({ children }: { children: React.ReactNode }) {
  const { status } = useAuth();
  const [, navigate] = useLocation();

  useEffect(() => {
    if (status === "guest") {
      navigate("/login");
    }
  }, [navigate, status]);

  if (status !== "authenticated") {
    return <LoadingState label="Validando sessão..." />;
  }

  return <AppShell>{children}</AppShell>;
}

function HomeRoute() {
  const { status } = useAuth();
  const [, navigate] = useLocation();

  useEffect(() => {
    if (status === "authenticated") {
      navigate("/dashboard");
    }
    if (status === "guest") {
      navigate("/login");
    }
  }, [navigate, status]);

  return <LoadingState label="Preparing workspace..." />;
}

function Router() {
  return (
    <Switch>
      <Route path="/" component={HomeRoute} />
      <Route path="/login" component={LoginPage} />
      <Route path="/auth/callback" component={AuthCallbackPage} />

      <Route path="/dashboard">
        <AuthGate>
          <DashboardPage />
        </AuthGate>
      </Route>

      <Route path="/clinic">
        <AuthGate>
          <ClinicPage />
        </AuthGate>
      </Route>

      <Route path="/invitations">
        <AuthGate>
          <InvitationsPage />
        </AuthGate>
      </Route>

      <Route path="/studies/new">
        <AuthGate>
          <StudyUploadPage />
        </AuthGate>
      </Route>

      <Route path="/studies/:studyId">
        {(params) => (
          <AuthGate>
            <StudyDetailPage studyId={params.studyId} />
          </AuthGate>
        )}
      </Route>

      <Route path="/studies/:studyId/viewer">
        {(params) => (
          <AuthGate>
            <StudyViewerPage studyId={params.studyId} />
          </AuthGate>
        )}
      </Route>

      <Route path="/studies">
        <AuthGate>
          <StudiesPage />
        </AuthGate>
      </Route>

      <Route path="/billing/success">
        <AuthGate>
          <BillingResultPage status="success" />
        </AuthGate>
      </Route>

      <Route path="/billing/cancel">
        <AuthGate>
          <BillingResultPage status="cancel" />
        </AuthGate>
      </Route>

      <Route path="/billing">
        <AuthGate>
          <BillingPage />
        </AuthGate>
      </Route>

      <Route component={NotFoundPage} />
    </Switch>
  );
}

export default function App() {
  return (
    <ErrorBoundary>
      <AuthProvider>
        <Toaster richColors position="top-right" />
        <Router />
      </AuthProvider>
    </ErrorBoundary>
  );
}
