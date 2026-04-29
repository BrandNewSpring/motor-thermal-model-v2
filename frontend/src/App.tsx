import { Routes, Route } from "react-router-dom";
import { Providers } from "./app/providers";
import Layout from "./app/layout";
import Calibration from "./pages/Calibration";
import Prediction from "./pages/Prediction";
import Profiles from "./pages/Profiles";

function AppContent() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<Calibration />} />
        <Route path="/prediction" element={<Prediction />} />
        <Route path="/profiles" element={<Profiles />} />
      </Route>
    </Routes>
  );
}

function App() {
  return (
    <Providers>
      <AppContent />
    </Providers>
  );
}

export default App;
