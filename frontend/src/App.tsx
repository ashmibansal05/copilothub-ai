
import { Navigate, Route, Routes } from "react-router-dom";

import ProtectedRoute from "./components/ProtectedRoute";
import AppLayout from "./layouts/AppLayout";

import CreateSession from "./pages/CreateSession";
import Dashboard from "./pages/Dashboard";
import JoinSession from "./pages/JoinSession";
import Landing from "./pages/Landing";
import Login from "./pages/Login";
import Register from "./pages/Register";
import SessionWorkspace from "./pages/SessionWorkspace";

// Phase 14 - Reports and Analytics
import AnalyticsOverview from "./pages/AnalyticsOverview";
import ReportViewer from "./pages/ReportViewer";
import SessionAnalytics from "./pages/SessionAnalytics";

export default function App() {
  return (
    <Routes>
      {/* Public Routes */}
      <Route path="/" element={<Landing />} />
      <Route path="/login" element={<Login />} />
      <Route path="/register" element={<Register />} />

      {/* Protected Routes */}
      <Route element={<ProtectedRoute />}>
        <Route element={<AppLayout />}>
          {/* Existing routes */}
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/sessions/new" element={<CreateSession />} />
          <Route path="/sessions/:id" element={<SessionWorkspace />} />
          <Route path="/join/:code" element={<JoinSession />} />

          {/* Phase 14 - Reports and Analytics */}
          <Route path="/analytics" element={<AnalyticsOverview />} />
          <Route path="/sessions/:id/report" element={<ReportViewer />} />
          <Route path="/sessions/:id/analytics" element={<SessionAnalytics />} />
        </Route>
      </Route>

      {/* Fallback Route */}
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}