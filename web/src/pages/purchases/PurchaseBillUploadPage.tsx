import { useAuth } from '@/auth/AuthContext';
import { BillUploadPage } from '@/pages/imports/BillUploadPage';
import { canImport } from '@/utils/permissions';

export function PurchaseBillUploadPage() {
  const { user } = useAuth();
  return <BillUploadPage kind="PURCHASE_BILL" canAccess={canImport(user)} />;
}
