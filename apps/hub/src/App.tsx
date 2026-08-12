import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import { AttemptEvidencePage } from "@/pages/AttemptEvidencePage";
import { DatasetDetailPage } from "@/pages/DatasetDetailPage";
import { DatasetsPage } from "@/pages/DatasetsPage";
import { LoginCallbackPage } from "@/pages/LoginCallbackPage";
import { LoginPage } from "@/pages/LoginPage";
import { OrganizationDetailPage } from "@/pages/OrganizationDetailPage";
import { OrganizationsPage } from "@/pages/OrganizationsPage";
import { PluginDetailPage } from "@/pages/PluginDetailPage";
import { PluginsPage } from "@/pages/PluginsPage";
import { TaskDetailPage } from "@/pages/TaskDetailPage";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Navigate to="/datasets" replace />} />
        <Route path="/datasets" element={<DatasetsPage />} />
        <Route path="/datasets/:datasetId" element={<DatasetDetailPage />} />
        <Route
          path="/datasets/:datasetId/tasks/:taskId"
          element={<TaskDetailPage />}
        />
        <Route
          path="/datasets/:datasetId/tasks/:taskId/attempts/:runId"
          element={<AttemptEvidencePage />}
        />
        <Route path="/plugins" element={<PluginsPage />} />
        <Route path="/plugins/:pluginId" element={<PluginDetailPage />} />
        <Route path="/organizations" element={<OrganizationsPage />} />
        <Route
          path="/organizations/:orgId"
          element={<OrganizationDetailPage />}
        />
        <Route path="/login" element={<LoginPage />} />
        <Route path="/login/callback" element={<LoginCallbackPage />} />
        <Route path="*" element={<Navigate to="/datasets" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
