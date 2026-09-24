import { MotionConfig } from "motion/react";
import { lazy, Suspense, useEffect, type ReactNode } from "react";
import { BrowserRouter, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { Toaster } from "sonner";
import { AuthProvider } from "./auth/AuthContext";
import { RequireAuth } from "./auth/RequireAuth";
import { FullPageStatus } from "./components/layout/PageShell";
import { HomePage } from "./pages/HomePage";

// lazy load the other pages
const DashboardPage = lazy(() => import("./pages/DashboardPage").then((m) => ({ default: m.DashboardPage })));
const LoginPage = lazy(() => import("./pages/LoginPage").then((m) => ({ default: m.LoginPage })));
const MatchesPage = lazy(() => import("./pages/MatchesPage").then((m) => ({ default: m.MatchesPage })));
const ProcessingPage = lazy(() => import("./pages/ProcessingPage").then((m) => ({ default: m.ProcessingPage })));
const SetupPage = lazy(() => import("./pages/SetupPage").then((m) => ({ default: m.SetupPage })));
const SignupPage = lazy(() => import("./pages/SignupPage").then((m) => ({ default: m.SignupPage })));
const UploadPage = lazy(() => import("./pages/UploadPage").then((m) => ({ default: m.UploadPage })));

function ScrollToTop() {
  const { pathname } = useLocation();
  useEffect(() => {
    window.scrollTo(0, 0);
  }, [pathname]);
  return null;
}

const guarded = (page: ReactNode) => <RequireAuth>{page}</RequireAuth>;

export default function App() {
  return (
    <MotionConfig reducedMotion="user">
      <AuthProvider>
        <BrowserRouter>
          <ScrollToTop />
          <Suspense fallback={<FullPageStatus>Loading…</FullPageStatus>}>
          <Routes>
            <Route path="/" element={<HomePage />} />
            <Route path="/login" element={<LoginPage />} />
            <Route path="/signup" element={<SignupPage />} />
            <Route path="/upload" element={guarded(<UploadPage />)} />
            <Route path="/matches" element={guarded(<MatchesPage />)} />
            <Route path="/matches/:matchId" element={guarded(<DashboardPage />)} />
            <Route path="/matches/:matchId/setup" element={guarded(<SetupPage />)} />
            <Route path="/matches/:matchId/processing" element={guarded(<ProcessingPage />)} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
          </Suspense>
        </BrowserRouter>
        <Toaster
          theme="dark"
          position="bottom-right"
          toastOptions={{
            style: {
              background: "#0e1713",
              border: "1px solid rgb(255 255 255 / 0.1)",
              color: "#f4f4f5",
              borderRadius: 12,
            },
          }}
        />
      </AuthProvider>
    </MotionConfig>
  );
}
