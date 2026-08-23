import { BrowserRouter } from "react-router-dom";

import { Shell } from "@/components/layout";
import { HubRoutes } from "@/hub-routes";

export default function App() {
  return (
    <BrowserRouter>
      <Shell>
        <HubRoutes />
      </Shell>
    </BrowserRouter>
  );
}
