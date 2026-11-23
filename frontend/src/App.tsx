import { Route, Routes } from "react-router-dom";
import ProtectedRoute from "./components/ProtectedRoute";
import AppLayout from "./layouts/AppLayout";
import AnalyticsOverview from "./pages/AnalyticsOverview";
import CreateSession from "./pages/CreateSession";
import Dashboard from "./pages/Dashboard";
import JoinSession from "./pages/JoinSession";
import Landing from "./pages/Landing";
import Login from "./pages/Login";
import NotFound from "./pages/NotFound";
import Register from "./pages/Register";
import ReportViewer from "./pages/ReportViewer";
import SessionAnalytics from "./pages/SessionAnalytics";
import SessionHistory from "./pages/SessionHistory";
import SessionRecords from "./pages/SessionRecords";
import SessionWorkspace from "./pages/SessionWorkspace";
import Settings from "./pages/Settings";

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route path="/login" element={<Login />} />
      <Route path="/register" element={<Register />} />

      <Route element={<ProtectedRoute />}>
        <Route element={<AppLayout />}>
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/history" element={<SessionHistory />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="/analytics" element={<AnalyticsOverview />} />
          <Route path="/sessions/new" element={<CreateSession />} />
          <Route path="/sessions/:id" element={<SessionWorkspace />} />
          <Route path="/sessions/:id/records" element={<SessionRecords />} />
          <Route path="/sessions/:id/report" element={<ReportViewer />} />
          <Route path="/sessions/:id/analytics" element={<SessionAnalytics />} />
          <Route path="/join/:code" element={<JoinSession />} />
        </Route>
      </Route>

      <Route path="*" element={<NotFound />} />
    </Routes>
  );
}