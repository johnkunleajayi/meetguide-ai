import { useEffect } from "react";
import { BrowserRouter, Link, Route, Routes, useNavigate } from "react-router-dom";
import { RequireAuth } from "./components/RequireAuth";
import { ThemeToggle } from "./components/ThemeToggle";
import { useAuth } from "./hooks/useAuth";
import { PublicLayout } from "./layouts/PublicLayout";
import { WorkspaceLayout } from "./layouts/WorkspaceLayout";
import { consumeWorkspaceIntent } from "./lib/auth";
import { LandingPage } from "./pages/LandingPage";
import { WorkspacePage } from "./pages/WorkspacePage";

export function AppRoutes() {
  const auth = useAuth();
  const navigate = useNavigate();

  useEffect(() => {
    if (auth.state.status === "authenticated" && consumeWorkspaceIntent()) {
      navigate("/app", { replace: true });
    }
  }, [auth.state.status, navigate]);

  const controls = { ...auth, logout: async () => {
    const success = await auth.logout();
    if (success) navigate("/", { replace: true });
    return success;
  } };

  return <Routes>
    <Route element={<PublicLayout auth={controls} />}>
      <Route path="/" element={<LandingPage />} />
    </Route>
    <Route element={<WorkspaceLayout auth={controls} />}>
      <Route path="/app" element={<RequireAuth auth={controls}>
        {auth.state.status === "authenticated" && <WorkspacePage key={auth.state.user.id} user={auth.state.user} />}
      </RequireAuth>} />
    </Route>
    <Route path="*" element={<main className="route-message container">
      <ThemeToggle /><h1>Page not found</h1><Link to="/">Return to MeetGuide</Link>
    </main>} />
  </Routes>;
}

export default function App() {
  return <BrowserRouter><AppRoutes /></BrowserRouter>;
}
