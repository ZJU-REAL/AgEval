import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import { DatasetDetailPage } from "@/pages/DatasetDetailPage";
import { DatasetsPage } from "@/pages/DatasetsPage";
import { LoginPage } from "@/pages/LoginPage";
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
        <Route path="/login" element={<LoginPage />} />
        <Route path="*" element={<Navigate to="/datasets" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
