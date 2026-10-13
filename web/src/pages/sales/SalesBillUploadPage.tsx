import { useAuth } from '@/auth/AuthContext';
import { BillUploadPage } from '@/pages/imports/BillUploadPage';
import { canImportSalesBill } from '@/utils/permissions';

export function SalesBillUploadPage() {
  const { user } = useAuth();
  // Bill import (photo/PDF/CSV extraction, auto-creating customers/products)
  // needs the Import permission AND the right to create the sales invoice it
  // produces — the same pair the backend ImportJobViewSet enforces.
  return <BillUploadPage kind="SALES_BILL" canAccess={canImportSalesBill(user)} />;
}
