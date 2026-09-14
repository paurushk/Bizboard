export function App() {
  return (
    <Routes>
      <Route path={dynamicPath} element={<LoginPage />} />
      <Route path="/ok" element={<HomePage />} />
    </Routes>
  );
}
