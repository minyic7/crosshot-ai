import { BrowserRouter, Routes, Route } from "react-router-dom"
import { Layout } from "@/components/layout/layout"
import { Dashboard } from "@/pages/dashboard"
import { DatabasePage } from "@/pages/database"

function App() {
  return (
    <BrowserRouter>
      <Layout>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/database" element={<DatabasePage />} />
        </Routes>
      </Layout>
    </BrowserRouter>
  )
}

export default App
