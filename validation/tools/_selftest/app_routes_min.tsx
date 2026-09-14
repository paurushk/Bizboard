export function App() {
  return (
    <Suspense>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/pay/:token" element={<PublicPayPage />} />
        <Route path="/old" element={<Navigate to="/login" replace />} />
        <Route element={<ProtectedRoute />}>
          <Route element={<AppShell />}>
            <Route index element={<HomePage />} />
            <Route element={<RoleRoute allow={canCreateSales} />}>
              <Route path="sales/new" element={<SalesInvoiceEditor />} />
            </Route>
            <Route element={<RoleRoute allow={allowPos} />}>
              <Route path="pos" element={<PosPage />} />
            </Route>
          </Route>
        </Route>
      </Routes>
    </Suspense>
  );
}
