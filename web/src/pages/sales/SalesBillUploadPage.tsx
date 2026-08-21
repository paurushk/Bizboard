import { useAuth } from '@/auth/AuthContext';
import { BillUploadPage } from '@/pages/imports/BillUploadPage';
import { canImport } from '@/utils/permissions';

export function SalesBillUploadPage() {
  const { user } = useAuth();
  // Bill import (photo/PDF/CSV extraction, auto-creating customers/products)
  // is gated by the dedicated Import permission — the same gate the backend
  // ImportJobViewSet enforces for every ImportJob kind — not by can_create_sales.
  return <BillUploadPage kind="SALES_BILL" canAccess={canImport(user)} />;
}
