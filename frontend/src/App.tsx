import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { DashboardPage } from "./pages/DashboardPage";
import { HomePage } from "./pages/HomePage";
import { MatchesPage } from "./pages/MatchesPage";
import { ProcessingPage } from "./pages/ProcessingPage";
import { SetupPage } from "./pages/SetupPage";
import { UploadPage } from "./pages/UploadPage";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/upload" element={<UploadPage />} />
        <Route path="/matches" element={<MatchesPage />} />
        <Route path="/matches/:matchId" element={<DashboardPage />} />
        <Route path="/matches/:matchId/setup" element={<SetupPage />} />
        <Route path="/matches/:matchId/processing" element={<ProcessingPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
