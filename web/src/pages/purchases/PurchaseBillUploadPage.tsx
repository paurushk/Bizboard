import { useAuth } from '@/auth/AuthContext';
import { BillUploadPage } from '@/pages/imports/BillUploadPage';
import { canImportPurchaseBill } from '@/utils/permissions';

export function PurchaseBillUploadPage() {
  const { user } = useAuth();
  return <BillUploadPage kind="PURCHASE_BILL" canAccess={canImportPurchaseBill(user)} />;
}
