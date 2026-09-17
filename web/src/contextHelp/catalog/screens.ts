import { helpVariant, mustPage } from '../buildPage';
import type { ContextHelpPage } from '../types';
import { MORE_HELP } from './more';
import { PAYMENTS_HELP } from './payments';
import { PURCHASE_HELP } from './purchases';
import { REPORTS_HELP } from './reports';
import { SALES_HELP } from './sales';

const salesOrders = mustPage(SALES_HELP, 'sales-orders');
const challans = mustPage(SALES_HELP, 'delivery-challans');
const salesCn = mustPage(SALES_HELP, 'sales-credit-notes');
const salesDn = mustPage(SALES_HELP, 'sales-debit-notes');
const purchaseOrders = mustPage(PURCHASE_HELP, 'purchase-orders');
const purchaseCn = mustPage(PURCHASE_HELP, 'purchase-credit-notes');
const purchaseDn = mustPage(PURCHASE_HELP, 'purchase-debit-notes');
const gstReturn = mustPage(REPORTS_HELP, 'gst-return');
const books = mustPage(REPORTS_HELP, 'books-report');
const insights = mustPage(REPORTS_HELP, 'insights');
const missing = mustPage(REPORTS_HELP, 'missing-documents');
const inventoryReports = mustPage(REPORTS_HELP, 'inventory-reports');
const mfg = mustPage(MORE_HELP, 'manufacturing');
const payroll = mustPage(MORE_HELP, 'payroll');
const crm = mustPage(MORE_HELP, 'crm');
const bankRecon = mustPage(PAYMENTS_HELP, 'bank-reconciliation');

/** Per-screen articles. Shared family pages stay as list/hub copy only. */
export const SCREEN_VARIANTS: ContextHelpPage[] = [
  helpVariant(salesOrders, 'sales-order-editor', {
    title: ['New / edit sales order', 'नया / संपादित बिक्री ऑर्डर'],
    summary: [
      'This form creates or edits one sales order. Confirm here to reserve stock. Completing an invoice or challan from this order later consumes or releases that reserve.',
      'यह फ़ॉर्म एक सेल्स ऑर्डर बनाता/बदलता है। यहाँ कन्फर्म से स्टॉक रिज़र्व होता है। बाद में इनवॉइस/चालान Complete रिज़र्व खपाता या छोड़ता है।',
    ],
    howItWorks: [
      ['Fill customer, godown and lines, then confirm. Convert copies all lines — split or reduce first for a part shipment.', 'ग्राहक, गोदाम, लाइनें भरें, कन्फर्म करें। कन्वर्ट सारी लाइनें कॉपी करता है — आंशिक के लिए पहले बाँटें।'],
      ['Saving a draft order does not reserve. Convert-to-invoice while still draft also does not release a reserve that was never created.', 'ड्राफ्ट ऑर्डर रिज़र्व नहीं करता। बिना कन्फर्म कन्वर्ट से रिज़र्व नहीं छूटता।'],
    ],
    relatedPages: [
      { path: '/sales/orders', labelKey: 'nav.salesOrders' },
      { path: '/sales/new', labelKey: 'nav.newInvoice' },
      { path: '/inventory/stock', labelKey: 'nav.currentStock' },
    ],
    nextActions: [
      ['Confirm to reserve, then convert to challan or invoice when you ship or bill.', 'रिज़र्व के लिए कन्फर्म करें, शिप/बिल पर चालान या इनवॉइस बनाएँ।'],
    ],
  }),

  helpVariant(challans, 'delivery-challan-editor', {
    title: ['New / edit delivery challan', 'नया / संपादित डिलीवरी चालान'],
    summary: [
      'This form is one dispatch note. Stock still moves when the invoice Completes unless the Owner turned on stock-on-challan — then Complete on this challan posts the sale movement.',
      'यह फ़ॉर्म एक डिस्पैच नोट है। स्टॉक इनवॉइस Complete पर कटता है, जब तक ओनर ने चालान-पर-स्टॉक न चालू किया हो।',
    ],
    howItWorks: [
      ['One challan per sales order. Convert this challan to an invoice once. e-Way needs transport distance (km) on this challan’s e-Way panel.', 'एक ऑर्डर पर एक चालान। इनवॉइस एक बार। e-Way के लिए इसी पैनल पर किमी।'],
    ],
    relatedPages: [
      { path: '/sales/delivery-challans', labelKey: 'nav.deliveryChallans' },
      { path: '/sales/orders', labelKey: 'nav.salesOrders' },
      { path: '/sales/new', labelKey: 'nav.newInvoice' },
    ],
    nextActions: [
      ['After dispatch, convert to invoice if the customer needs a tax bill, then Complete that invoice.', 'डिस्पैच बाद टैक्स बिल हो तो इनवॉइस बनाकर Complete करें।'],
    ],
  }),

  helpVariant(salesCn, 'sales-credit-note-editor', {
    title: ['New / edit sales credit note', 'नया / संपादित बिक्री क्रेडिट नोट'],
    summary: [
      'This form reduces one completed tax invoice (return, post-sale discount, deficiency). After Complete, do not rewrite lines — reverse with a debit note if needed.',
      'यह फ़ॉर्म एक पूर्ण टैक्स इनवॉइस घटाता है। Complete बाद लाइनें न लिखें — ज़रूरत हो तो डेबिट नोट।',
    ],
    howItWorks: [
      ['Link the original GST invoice on this form. Prefer this over editing a completed bill.', 'यहाँ मूल GST बिल लिंक करें। पूर्ण बिल एडिट करने से यही बेहतर है।'],
    ],
    relatedPages: [
      { path: '/sales/credit-notes', labelKey: 'nav.creditNotes' },
      { path: '/sales/history', labelKey: 'nav.salesHistory' },
      { path: '/sales/debit-notes', labelKey: 'nav.debitNotes' },
    ],
    nextActions: [
      ['Link the invoice, pick the reason, Complete, then check customer outstanding.', 'बिल लिंक करें, कारण चुनें, Complete करें, बकाया देखें।'],
    ],
  }),

  helpVariant(salesDn, 'sales-debit-note-editor', {
    title: ['New / edit sales debit note', 'नया / संपादित बिक्री डेबिट नोट'],
    summary: [
      'This form increases what the customer owes after one completed invoice. It does not issue stock. After Complete, reverse a mistake with a credit note.',
      'यह फ़ॉर्म पूर्ण बिल के बाद बकाया बढ़ाता है। स्टॉक नहीं काटता। गलती पर क्रेडिट नोट।',
    ],
    howItWorks: [
      ['Use this when you under-billed this supply. A new invoice is only for a new supply.', 'कम बिल हो तो यही। नई सप्लाई हो तो नया इनवॉइस।'],
    ],
    relatedPages: [
      { path: '/sales/debit-notes', labelKey: 'nav.debitNotes' },
      { path: '/sales/credit-notes', labelKey: 'nav.creditNotes' },
      { path: '/sales/history', labelKey: 'nav.salesHistory' },
    ],
    nextActions: [
      ['Complete this note, then collect the extra via a receipt allocation.', 'नोट Complete करें, रसीद आवंटन से राशि लें।'],
    ],
  }),

  helpVariant(purchaseOrders, 'purchase-order-editor', {
    title: ['New / edit purchase order', 'नया / संपादित खरीद ऑर्डर'],
    summary: [
      'This form is the supplier order. It does not put stock in or raise payables. Completing a purchase bill when goods arrive is the inward.',
      'यह फ़ॉर्म सप्लायर ऑर्डर है। स्टॉक या देनदारी नहीं। माल आने पर खरीद बिल Complete इनवार्ड है।',
    ],
    howItWorks: [
      ['Fill supplier and lines, send the order, then enter the supplier bill on New Purchase when goods and rates match.', 'सप्लायर/लाइनें भरें, ऑर्डर भेजें, माल मिलने पर नई खरीद पर बिल दर्ज करें।'],
    ],
    relatedPages: [
      { path: '/purchases/orders', labelKey: 'nav.purchaseOrders' },
      { path: '/purchases/new', labelKey: 'nav.newPurchase' },
      { path: '/purchases/suppliers', labelKey: 'nav.suppliers' },
    ],
    nextActions: [
      ['When the supplier bill arrives, create a purchase and Complete it — do not treat this PO as stock.', 'सप्लायर बिल आए तो खरीद Complete करें — PO को स्टॉक न समझें।'],
    ],
  }),

  helpVariant(purchaseCn, 'purchase-credit-note-editor', {
    title: ['New / edit purchase credit note', 'नया / संपादित खरीद क्रेडिट नोट'],
    summary: [
      'This form must point at the original completed purchase so ITC reversal and GSTR stay tied to that bill.',
      'यह फ़ॉर्म मूल पूर्ण खरीद से जुड़ना चाहिए ताकि ITC उलटाव उसी बिल से बँधे।',
    ],
    howItWorks: [
      ['Complete the purchase first, then fill this note and Complete it. Lines are not edited after Complete.', 'पहले खरीद Complete करें, फिर यह नोट Complete करें। बाद में लाइनें एडिट नहीं।'],
    ],
    relatedPages: [
      { path: '/purchases/credit-notes', labelKey: 'nav.purchaseCreditNotes' },
      { path: '/purchases/history', labelKey: 'nav.purchaseHistory' },
      { path: '/purchases/debit-notes', labelKey: 'nav.purchaseDebitNotes' },
    ],
    nextActions: [
      ['Link the purchase, Complete, then review ITC on 2B / 3B worksheets.', 'खरीद लिंक कर Complete करें, फिर 2B/3B पर ITC देखें।'],
    ],
  }),

  helpVariant(purchaseDn, 'purchase-debit-note-editor', {
    title: ['New / edit purchase debit note', 'नया / संपादित खरीद डेबिट नोट'],
    summary: [
      'This form increases what you owe on an existing completed purchase (extra charge). Additional goods that arrived need a new purchase bill so stock posts.',
      'मौजूदा पूर्ण खरीद पर देनदारी बढ़ाता है। अतिरिक्त माल नई खरीद से — ताकि स्टॉक लगे।',
    ],
    howItWorks: [
      ['Complete this note for value-only extras. It hits payables and GST worksheets; it does not by itself add stock.', 'केवल मूल्य के लिए Complete करें। देनदारी/GST में जाता है, स्टॉक नहीं बढ़ाता।'],
    ],
    relatedPages: [
      { path: '/purchases/debit-notes', labelKey: 'nav.purchaseDebitNotes' },
      { path: '/purchases/new', labelKey: 'nav.newPurchase' },
      { path: '/purchases/history', labelKey: 'nav.purchaseHistory' },
    ],
    nextActions: [
      ['If extra goods arrived, leave this form and Complete a new purchase instead.', 'अतिरिक्त माल हो तो नई खरीद Complete करें।'],
    ],
  }),

  helpVariant(gstReturn, 'gstr-1', {
    title: ['GSTR-1 worksheet', 'GSTR-1 वर्कशीट'],
    summary: [
      'Offline outward-supplies worksheet (and optional JSON) for one GSTIN and tax period. It does not file on the GST portal.',
      'एक GSTIN और पीरियड की आउटवर्ड वर्कशीट (वैकल्पिक JSON)। पोर्टल पर फाइल नहीं करता।',
    ],
    howItWorks: [
      ['Pick filing GSTIN and period. Only completed GST/TAX sales in that GSTIN appear. Composition companies use CMP-08 / GSTR-4, not this GSTR-1.', 'फाइलिंग GSTIN और पीरियड चुनें। उसी GSTIN की पूर्ण बिक्री। Composition पर CMP-08/GSTR-4।'],
    ],
    relatedPages: [
      { path: '/sales/history', labelKey: 'nav.salesHistory' },
      { path: '/reports/gstr3b', labelKey: 'nav.gstr3b' },
      { path: '/settings/gst', labelKey: 'nav.gst' },
    ],
    nextActions: [
      ['Review rows against sales history, export JSON if your CA uses the offline tool, then file on gst.gov.in.', 'बिक्री इतिहास से मिलाएँ, JSON निर्यात करें, gst.gov.in पर फाइल करें।'],
    ],
  }),

  helpVariant(gstReturn, 'gstr-3b', {
    title: ['GSTR-3B worksheet', 'GSTR-3B वर्कशीट'],
    summary: [
      'Offline GSTR-3B summary worksheet. Table 4A follows IMS/2B review — there is no auto-accept. Books stay the source of truth. Does not file.',
      'ऑफ़लाइन GSTR-3B सारांश। टेबल 4A IMS/2B से — ऑटो-एक्सेप्ट नहीं। फाइल नहीं करता।',
    ],
    howItWorks: [
      ['Pick GSTIN and period. Finish 2B Accept/Reject/Park before trusting ITC cells. You still file on the portal.', 'GSTIN/पीरियड। ITC से पहले 2B तय करें। फाइलिंग पोर्टल पर।'],
    ],
    relatedPages: [
      { path: '/reports/gstr2b', labelKey: 'nav.gstr2b' },
      { path: '/reports/gstr1', labelKey: 'nav.gstr1' },
      { path: '/purchases/history', labelKey: 'nav.purchaseHistory' },
    ],
    nextActions: [
      ['Reconcile 2B, then use this worksheet with your CA and file on gst.gov.in.', '2B मिलाएँ, CA के साथ वर्कशीट देखें, पोर्टल पर फाइल करें।'],
    ],
  }),

  helpVariant(gstReturn, 'gstr-4', {
    title: ['GSTR-4 worksheet', 'GSTR-4 वर्कशीट'],
    summary: [
      'Composition annual aid — an offline worksheet, not a filing engine. Regular GSTR-1/3B do not apply here.',
      'Composition वार्षिक सहायता — ऑफ़लाइन वर्कशीट, फाइलिंग इंजन नहीं।',
    ],
    howItWorks: [
      ['Use only when the company is composition. Pick GSTIN/period as shown, then file on the portal with your CA.', 'केवल Composition कंपनी पर। GSTIN/पीरियड चुनें, पोर्टल पर फाइल करें।'],
    ],
    relatedPages: [
      { path: '/reports/cmp08', labelKey: 'nav.cmp08' },
      { path: '/settings/gst', labelKey: 'nav.gst' },
    ],
    nextActions: [
      ['Confirm registration type in GST settings before treating these totals as composition tax.', 'इन योगों से पहले GST सेटिंग में रजिस्ट्रेशन प्रकार देखें।'],
    ],
  }),

  helpVariant(gstReturn, 'cmp-08', {
    title: ['CMP-08 worksheet', 'CMP-08 वर्कशीट'],
    summary: [
      'Composition quarterly payment aid. Offline worksheet only — it does not pay or file on the portal.',
      'Composition तिमाही भुगतान सहायता। केवल ऑफ़लाइन — पोर्टल पर भुगतान/फाइल नहीं।',
    ],
    howItWorks: [
      ['Composition companies use this instead of regular GSTR-1/3B. Totals still come from completed books.', 'Composition पर GSTR-1/3B की जगह। योग पूर्ण किताबों से।'],
    ],
    relatedPages: [
      { path: '/reports/gstr4', labelKey: 'nav.gstr4' },
      { path: '/settings/gst', labelKey: 'nav.gst' },
    ],
    nextActions: [
      ['Review with your CA, then pay/file on gst.gov.in — Completing a bill here is not that payment.', 'CA के साथ देखें, gst.gov.in पर भुगतान/फाइल करें।'],
    ],
  }),

  helpVariant(gstReturn, 'gstr-6', {
    title: ['GSTR-6 (honesty stub)', 'GSTR-6 (स्टब)'],
    summary: [
      'Honesty stub for ISD, not a filing engine. Bizboard does not prepare or submit GSTR-6.',
      'ISD के लिए स्टब, फाइलिंग इंजन नहीं। बिज़बोर्ड GSTR-6 नहीं भेजता।',
    ],
    howItWorks: [
      ['Read the on-screen notice. File ISD returns on the GST portal outside this product.', 'स्क्रीन का नोटिस पढ़ें। ISD रिटर्न पोर्टल पर अलग से।'],
    ],
    relatedPages: [
      { path: '/reports/gstr1', labelKey: 'nav.gstr1' },
      { path: '/help', labelKey: 'nav.help' },
    ],
    nextActions: [
      ['Do not export this screen as a filed return. Use gst.gov.in for GSTR-6.', 'इसे फाइल न समझें। GSTR-6 gst.gov.in पर।'],
    ],
  }),

  helpVariant(gstReturn, 'gstr-7', {
    title: ['GSTR-7 (honesty stub)', 'GSTR-7 (स्टब)'],
    summary: [
      'Honesty stub for GST TDS, not a filing engine. TDS/TCS worksheets elsewhere are also not the portal filing.',
      'GST TDS स्टब, फाइलिंग इंजन नहीं।',
    ],
    howItWorks: [
      ['Use the TDS/TCS worksheets for books, then file GSTR-7 on the portal if you are a deductor.', 'किताबों के लिए TDS/TCS वर्कशीट, फाइलिंग पोर्टल पर।'],
    ],
    relatedPages: [
      { path: '/reports/tds-tcs', labelKey: 'nav.tdsTcs' },
      { path: '/help', labelKey: 'nav.help' },
    ],
    nextActions: [
      ['Do not treat this stub as a submitted GSTR-7.', 'इसे जमा GSTR-7 न समझें।'],
    ],
  }),

  helpVariant(gstReturn, 'gstr-8', {
    title: ['GSTR-8 (honesty stub)', 'GSTR-8 (स्टब)'],
    summary: [
      'Honesty stub for GST TCS (e-commerce operator), not a filing engine.',
      'ई-कॉमर्स GST TCS स्टब, फाइलिंग इंजन नहीं।',
    ],
    howItWorks: [
      ['Bizboard does not file GSTR-8. Operators file on the GST portal.', 'बिज़बोर्ड GSTR-8 नहीं फाइल करता। पोर्टल पर फाइल करें।'],
    ],
    relatedPages: [
      { path: '/reports/tds-tcs', labelKey: 'nav.tdsTcs' },
      { path: '/help', labelKey: 'nav.help' },
    ],
    nextActions: [
      ['Use gst.gov.in for GSTR-8. This page is a notice, not a return.', 'GSTR-8 gst.gov.in पर। यह नोटिस है, रिटर्न नहीं।'],
    ],
  }),

  helpVariant(gstReturn, 'gstr-9', {
    title: ['GSTR-9 outward FY aid', 'GSTR-9 आउटवर्ड वार्षिक सहायता'],
    summary: [
      'Offline annual outward aid for the FY. Not the annual return filing and not a substitute for GSTR-1/3B already filed.',
      'वित्तीय वर्ष की ऑफ़लाइन आउटवर्ड सहायता। वार्षिक रिटर्न फाइलिंग नहीं।',
    ],
    howItWorks: [
      ['Pick GSTIN and FY as offered. Only completed books feed this aid. File GSTR-9 on the portal with your CA.', 'GSTIN और FY चुनें। पूर्ण किताबें। फाइलिंग पोर्टल पर CA के साथ।'],
    ],
    relatedPages: [
      { path: '/reports/gstr1', labelKey: 'nav.gstr1' },
      { path: '/reports/gstr3b', labelKey: 'nav.gstr3b' },
    ],
    nextActions: [
      ['Reconcile to GSTR-1/3B worksheets, then file the annual return on gst.gov.in.', 'GSTR-1/3B से मिलाएँ, वार्षिक रिटर्न पोर्टल पर फाइल करें।'],
    ],
  }),

  helpVariant(gstReturn, 'gst-health', {
    title: ['GST Health', 'GST हेल्थ'],
    summary: [
      'Diagnostic scores and gaps for GST hygiene. It is not a filing confirmation and does not change bills.',
      'GST स्वच्छता का निदान। फाइलिंग पुष्टि नहीं, बिल नहीं बदलता।',
    ],
    howItWorks: [
      ['Read the flags, then open the invoice, 2B row or setting they point to. Completing or filing still happens there.', 'फ़्लैग पढ़ें, फिर बिल/2B/सेटिंग खोलें। Complete/फाइल वहीं।'],
    ],
    relatedPages: [
      { path: '/reports/gstr1', labelKey: 'nav.gstr1' },
      { path: '/reports/gstr2b', labelKey: 'nav.gstr2b' },
      { path: '/attention', labelKey: 'nav.attention' },
    ],
    nextActions: [
      ['Fix the source document or 2B review; do not file from this dashboard.', 'स्रोत बिल या 2B ठीक करें; यहाँ से फाइल न करें।'],
    ],
  }),

  helpVariant(gstReturn, 'gst-rate-exposure', {
    title: ['GST rate back-scan', 'GST दर बैक-स्कैन'],
    summary: [
      'Looks back at rates used on completed bills. It does not re-rate stock or file a return.',
      'पूर्ण बिलों की दरें देखता है। स्टॉक री-रेट या रिटर्न फाइल नहीं।',
    ],
    howItWorks: [
      ['Scan the list, then open the invoice and issue a credit/debit note if a rate was wrong after Complete.', 'सूची देखें, गलत दर हो तो बिल खोलकर क्रेडिट/डेबिट नोट।'],
    ],
    relatedPages: [
      { path: '/sales/history', labelKey: 'nav.salesHistory' },
      { path: '/sales/credit-notes', labelKey: 'nav.creditNotes' },
    ],
    nextActions: [
      ['Correct with a note on the completed bill — do not rewrite posted lines.', 'पूर्ण बिल पर नोट से ठीक करें — पोस्टेड लाइनें न लिखें।'],
    ],
  }),

  helpVariant(missing, 'ca-needs', {
    title: ['What my CA needs', 'CA को क्या चाहिए'],
    summary: [
      'Friendlier view of IMS/2B bills you have not booked yet. Same gap list as Missing bills — it does not file GST or auto-create purchases.',
      'IMS/2B के अनबुक बिलों का सरल दृश्य। गायब बिल वाली वही सूची। GST फाइल या खरीद ऑटो नहीं।',
    ],
    howItWorks: [
      ['Request or import the supplier bill, then Complete a real purchase so 2B can match.', 'बिल माँगें/इम्पोर्ट करें, असली खरीद Complete करें।'],
    ],
    relatedPages: [
      { path: '/reports/missing-documents', labelKey: 'nav.missingDocuments' },
      { path: '/purchases/new', labelKey: 'nav.newPurchase' },
      { path: '/reports/gstr2b', labelKey: 'nav.gstr2b' },
    ],
    nextActions: [
      ['Book the missing purchase, Complete it, then return to 2B.', 'गायब खरीद Complete करें, फिर 2B पर जाएँ।'],
    ],
  }),

  helpVariant(inventoryReports, 'stock-valuation', {
    title: ['Stock valuation', 'स्टॉक वैल्यूएशन'],
    summary: [
      'Value of on-hand stock using the company’s costing method. It is not the movement report and it does not adjust stock.',
      'कंपनी की कॉस्टिंग से स्टॉक मूल्य। मूवमेंट रिपोर्ट नहीं, एडजस्टमेंट नहीं।',
    ],
    howItWorks: [
      ['Pick godown/period as offered. Draft purchases are not in valuation; posted counts and completed bills are.', 'गोदाम/पीरियड चुनें। ड्राफ्ट खरीद नहीं; गिनती और पूर्ण बिल हैं।'],
    ],
    relatedPages: [
      { path: '/inventory/stock', labelKey: 'nav.currentStock' },
      { path: '/reports/inventory', labelKey: 'nav.inventoryReports' },
    ],
    nextActions: [
      ['If value looks wrong, check costing method, then the last completed purchase or count for that item.', 'मूल्य गलत लगे तो कॉस्टिंग, फिर अंतिम पूर्ण खरीद/गिनती देखें।'],
    ],
  }),

  helpVariant(books, 'trial-balance', {
    title: ['Trial balance', 'ट्रायल बैलेंस'],
    summary: [
      'Lists posted GL balances so debits equal credits. Needs accounting enabled. Opening this report never reopens a closed period.',
      'पोस्टेड GL बैलेंस। लेखांकन चालू चाहिए। रिपोर्ट पीरियड नहीं खोलती।',
    ],
    howItWorks: [
      ['Invoice Complete posts to GL when books are on. Drill to journals, then the source invoice or payment.', 'खाते हों तो Complete GL पर। जर्नल, फिर स्रोत बिल।'],
    ],
    relatedPages: [
      { path: '/accounting/journals', labelKey: 'nav.journals' },
      { path: '/reports/profit-and-loss', labelKey: 'nav.profitAndLoss' },
      { path: '/accounting/periods', labelKey: 'nav.accountingPeriods' },
    ],
    nextActions: [
      ['If a line is off, open that account’s journals, then fix with a note or reversing journal — not by typing the report.', 'लाइन गलत हो तो जर्नल खोलें, नोट/रिवर्स जर्नल से ठीक करें।'],
    ],
  }),

  helpVariant(books, 'profit-and-loss', {
    title: ['Profit & Loss', 'लाभ और हानि'],
    summary: [
      'P&L from posted journals for the period. Not a GST filing and not cash in the drawer.',
      'पीरियड के पोस्टेड जर्नल से P&L। GST फाइलिंग या दराज का नकद नहीं।',
    ],
    howItWorks: [
      ['Revenue and expense follow completed documents and journals. Closed period still shows history; it blocks money amends.', 'आय/खर्च पूर्ण दस्तावेज़ से। बंद पीरियड इतिहास दिखाता है, संशोधन रोकता है।'],
    ],
    relatedPages: [
      { path: '/reports/trial-balance', labelKey: 'nav.trialBalance' },
      { path: '/reports/cash-book', labelKey: 'nav.cashBook' },
      { path: '/reports/gstr3b', labelKey: 'nav.gstr3b' },
    ],
    nextActions: [
      ['Do not match this line-by-line to GSTR-3B without your CA — different bases.', 'बिना CA P&L को GSTR-3B से लाइन-बाय-लाइन न मिलाएँ।'],
    ],
  }),

  helpVariant(books, 'balance-sheet', {
    title: ['Balance sheet', 'बैलेंस शीट'],
    summary: [
      'Assets, liabilities and equity from posted GL. Needs accounting. It does not file GST or show unallocated cash as “bank truth” by itself.',
      'पोस्टेड GL से संपत्ति/देनदारी। GST फाइल नहीं।',
    ],
    howItWorks: [
      ['Receivables and payables follow completed bills and allocations. Stock value follows inventory costing, not this report’s edit box — there isn’t one.', 'प्राप्य/देय पूर्ण बिल और आवंटन से। स्टॉक वैल्यूएशन इन्वेंटरी कॉस्टिंग से।'],
    ],
    relatedPages: [
      { path: '/reports/trial-balance', labelKey: 'nav.trialBalance' },
      { path: '/reports/stock-valuation', labelKey: 'nav.stockValuation' },
      { path: '/accounting/periods', labelKey: 'nav.accountingPeriods' },
    ],
    nextActions: [
      ['Trace a balance to journals, then the source invoice, payment or stock move.', 'बैलेंस जर्नल से, फिर बिल/भुगतान/स्टॉक से मिलाएँ।'],
    ],
  }),

  helpVariant(books, 'books-health', {
    title: ['Books health', 'बुक्स हेल्थ'],
    summary: [
      'Checks that posted books look consistent (unbalanced journals, mapping gaps). It does not close the year or file GST.',
      'पोस्टेड किताबों की जाँच। वर्ष क्लोज़ या GST फाइल नहीं।',
    ],
    howItWorks: [
      ['Read each flag, then open journals or chart of accounts. Fix at the source, then refresh.', 'फ़्लैग पढ़ें, जर्नल/खाता खोलें, स्रोत पर ठीक करें।'],
    ],
    relatedPages: [
      { path: '/accounting/journals', labelKey: 'nav.journals' },
      { path: '/accounting/accounts', labelKey: 'nav.chartOfAccounts' },
      { path: '/reports/trial-balance', labelKey: 'nav.trialBalance' },
    ],
    nextActions: [
      ['Clear unbalanced journals before month close. Opening this page does not reopen a period.', 'महीना क्लोज़ से पहले असंतुलित जर्नल ठीक करें।'],
    ],
  }),

  helpVariant(insights, 'insights-alerts', {
    title: ['Business alerts', 'बिज़नेस अलर्ट'],
    summary: [
      'Alert list from books (overdue, stock, GST hygiene). An alert is a pointer — it does not Complete, allocate, or file.',
      'किताबों से अलर्ट सूची। संकेत है — Complete/आवंटन/फाइल नहीं।',
    ],
    howItWorks: [
      ['Open the document the alert names, then apply the same Complete/allocate rules as on that page.', 'अलर्ट वाला दस्तावेज़ खोलें, वहीं के नियम लगाएँ।'],
    ],
    relatedPages: [
      { path: '/insights', labelKey: 'nav.insightsHub' },
      { path: '/attention', labelKey: 'nav.attention' },
      { path: '/help', labelKey: 'nav.help' },
    ],
    nextActions: [
      ['Treat each alert as a to-do on the source bill or 2B row, not as already filed GST.', 'अलर्ट को स्रोत बिल/2B का काम समझें, फाइलिंग नहीं।'],
    ],
  }),

  helpVariant(insights, 'insights-health', {
    title: ['Business health', 'बिज़नेस हेल्थ'],
    summary: [
      'Health scores over completed activity. Fully returned sales are not live sales. This is not tax or bank truth.',
      'पूर्ण गतिविधि के स्कोर। पूरी वापसी चालू बिक्री नहीं। टैक्स/बैंक सत्य नहीं।',
    ],
    howItWorks: [
      ['Read the score, then open sales history, stock or cash book to act.', 'स्कोर पढ़ें, फिर इतिहास/स्टॉक/कैश बुक खोलें।'],
    ],
    relatedPages: [
      { path: '/insights', labelKey: 'nav.insightsHub' },
      { path: '/reports/cash-book', labelKey: 'nav.cashBook' },
      { path: '/sales/history', labelKey: 'nav.salesHistory' },
    ],
    nextActions: [
      ['Post the real bill, receipt or adjustment — this page only reads.', 'असली बिल/रसीद/एडजस्टमेंट पोस्ट करें — यह पेज केवल पढ़ता है।'],
    ],
  }),

  helpVariant(insights, 'insights-cashflow', {
    title: ['Cashflow forecast', 'कैशफ्लो पूर्वानुमान'],
    summary: [
      'Forward-looking cash view. It is not the cash book (daily galla) and not a bank statement.',
      'आगे का कैश नज़रिया। कैश बुक या बैंक स्टेटमेंट नहीं।',
    ],
    howItWorks: [
      ['Use it for planning. Record actual cash on receipts, supplier payments and the cash book.', 'योजना के लिए। असल नकद रसीद/भुगतान/कैश बुक पर।'],
    ],
    relatedPages: [
      { path: '/reports/cash-book', labelKey: 'nav.cashBook' },
      { path: '/sales/receipts', labelKey: 'nav.receipts' },
      { path: '/insights', labelKey: 'nav.insightsHub' },
    ],
    nextActions: [
      ['Reconcile today’s drawer on Cash book; do not file GST or pay suppliers from this forecast.', 'आज की दराज कैश बुक पर मिलाएँ।'],
    ],
  }),

  helpVariant(insights, 'insights-assistant', {
    title: ['Insights assistant', 'इनसाइट असिस्टेंट'],
    summary: [
      'Optional Q&A over your books. It will not replace page Help for why Complete is blocked, and it does not Complete or file GST.',
      'किताबों पर वैकल्पिक प्रश्न। Complete क्यों रुका — पेज सहायता देखें। Complete/फाइल नहीं करता।',
    ],
    howItWorks: [
      ['Ask for a pointer, then open the document. Model answers are not journals.', 'संकेत पूछें, दस्तावेज़ खोलें। मॉडल जवाब जर्नल नहीं।'],
    ],
    relatedPages: [
      { path: '/help', labelKey: 'nav.help' },
      { path: '/insights', labelKey: 'nav.insightsHub' },
      { path: '/settings/ai', labelKey: 'nav.aiSettings' },
    ],
    nextActions: [
      ['If Complete is blocked, use the page ? Help or Help & FAQ — not this assistant as the source of truth.', 'Complete रुके तो पेज सहायता या FAQ — असिस्टेंट को सत्य न मानें।'],
    ],
  }),

  helpVariant(mfg, 'manufacturing-boms', {
    title: ['Bills of material', 'सामग्री सूची (BOM)'],
    summary: [
      'Defines finished goods and components. Saving a BOM does not consume stock or create a GST invoice.',
      'तैयार माल और घटक। BOM सेव स्टॉक नहीं काटता, GST बिल नहीं।',
    ],
    howItWorks: [
      ['Create an active BOM, then raise work orders from it. Sell FG on a normal sales invoice after stock is produced.', 'सक्रिय BOM, फिर वर्क ऑर्डर। स्टॉक आने पर सामान्य बिक्री बिल।'],
    ],
    relatedPages: [
      { path: '/manufacturing/work-orders', labelKey: 'nav.workOrders' },
      { path: '/inventory/products', labelKey: 'nav.products' },
      { path: '/inventory/stock', labelKey: 'nav.currentStock' },
    ],
    nextActions: [
      ['Keep the BOM accurate before completing work orders, or component consumption will be wrong.', 'वर्क ऑर्डर से पहले BOM सही रखें।'],
    ],
  }),

  helpVariant(mfg, 'manufacturing-work-orders', {
    title: ['Work orders', 'वर्क ऑर्डर'],
    summary: [
      'Completing a work order consumes components and can produce finished-goods stock. It is not a GST invoice.',
      'वर्क ऑर्डर Complete घटक काटता और तैयार माल बढ़ा सकता है — GST इनवॉइस नहीं।',
    ],
    howItWorks: [
      ['Pick an active BOM, complete the order, then bill the customer on New Invoice.', 'सक्रिय BOM चुनें, Complete करें, फिर नया इनवॉइस।'],
    ],
    relatedPages: [
      { path: '/manufacturing/boms', labelKey: 'nav.boms' },
      { path: '/inventory/stock', labelKey: 'nav.currentStock' },
      { path: '/sales/new', labelKey: 'nav.newInvoice' },
    ],
    nextActions: [
      ['Complete the work order, check current stock, then raise the tax invoice.', 'वर्क ऑर्डर Complete करें, स्टॉक देखें, टैक्स बिल बनाएँ।'],
    ],
  }),

  helpVariant(payroll, 'payroll-employees', {
    title: ['Employees', 'कर्मचारी'],
    summary: [
      'Employee master for payroll. Saving an employee does not post salary, a supplier bill, or a GST invoice.',
      'पेरोल मास्टर। कर्मचारी सेव सैलरी, खरीद या GST बिल नहीं पोस्ट करता।',
    ],
    howItWorks: [
      ['Maintain people here, then post a pay run on Pay runs. Closed period can still block posting.', 'यहाँ लोग रखें, पे रन पर पोस्ट करें। बंद पीरियड रोक सकता है।'],
    ],
    relatedPages: [
      { path: '/payroll/pay-runs', labelKey: 'nav.payRuns' },
      { path: '/accounting/journals', labelKey: 'nav.journals' },
    ],
    nextActions: [
      ['Add employees before the first pay run. Do not book salary as a GST purchase to a dummy supplier.', 'पहले पे रन से पहले कर्मचारी जोड़ें। सैलरी को GST खरीद न बनाएँ।'],
    ],
  }),

  helpVariant(payroll, 'payroll-pay-runs', {
    title: ['Pay runs', 'पे रन'],
    summary: [
      'A pay run is not a supplier bill and not a GST invoice. When accounting is on, posting hits books — it does not create GSTR-1 rows.',
      'पे रन सप्लायर बिल या GST इनवॉइस नहीं। खाते हों तो किताबें; GSTR-1 नहीं।',
    ],
    howItWorks: [
      ['Create the run for a calendar month as the page allows, then pay via the path your CA uses.', 'कैलेंडर महीने का रन बनाएँ, CA वाले पथ से भुगतान।'],
    ],
    relatedPages: [
      { path: '/payroll/employees', labelKey: 'nav.employees' },
      { path: '/accounting/journals', labelKey: 'nav.journals' },
      { path: '/purchases/payments', labelKey: 'nav.supplierPayments' },
    ],
    nextActions: [
      ['Post the run, then pay. Closed period can block posting into a locked month.', 'रन पोस्ट करें, फिर भुगतान। बंद पीरियड रोक सकता है।'],
    ],
  }),

  helpVariant(crm, 'crm-leads', {
    title: ['Leads', 'लीड'],
    summary: [
      'Capture leads before they are customers. Saving a lead does not Complete a tax invoice or reserve stock.',
      'ग्राहक बनने से पहले लीड। सेव से टैक्स इनवॉइस Complete या स्टॉक रिज़र्व नहीं।',
    ],
    howItWorks: [
      ['Add the lead, then progress an opportunity. Create a quotation or invoice in Sales when the deal is real.', 'लीड जोड़ें, अवसर बढ़ाएँ, डील पक्की हो तो सेल्स में कोटेशन/बिल।'],
    ],
    relatedPages: [
      { path: '/crm/opportunities', labelKey: 'nav.opportunities' },
      { path: '/sales/customers', labelKey: 'nav.customers' },
      { path: '/sales/quotations', labelKey: 'nav.quotations' },
    ],
    nextActions: [
      ['Convert to a customer only when you are ready to quote or bill — GST still needs a completed invoice.', 'कोट/बिल के लिए ग्राहक बनाएँ — GST पूर्ण इनवॉइस से।'],
    ],
  }),

  helpVariant(crm, 'crm-opportunities', {
    title: ['Opportunities', 'अवसर'],
    summary: [
      'Pipeline only. A won opportunity is not billed until you Complete a sales invoice (or convert a quotation and Complete).',
      'पाइपलाइन। जीता अवसर तब तक बिल नहीं जब तक इनवॉइस Complete न हो।',
    ],
    howItWorks: [
      ['Move the stage, then create a quotation or invoice in Sales. No stock or GST until that document Completes.', 'स्टेज बदलें, सेल्स में कोटेशन/बिल। Complete तक स्टॉक/GST नहीं।'],
    ],
    relatedPages: [
      { path: '/crm/leads', labelKey: 'nav.leads' },
      { path: '/sales/quotations', labelKey: 'nav.quotations' },
      { path: '/sales/new', labelKey: 'nav.newInvoice' },
    ],
    nextActions: [
      ['When the deal is real, create a quotation or invoice and Complete it.', 'डील पक्की हो तो कोटेशन/इनवॉइस Complete करें।'],
    ],
  }),

  helpVariant(bankRecon, 'accounting-bank-reconciliation', {
    title: ['Accounting bank reconciliation', 'लेखांकन बैंक मिलान'],
    summary: [
      'Clears GL bank lines when accounting is on. Statement upload still lives under Payments. Ambiguous matches are never auto-applied.',
      'खाते चालू हों तो GL बैंक पंक्तियाँ। स्टेटमेंट अपलोड पेमेंट्स में। ऑटो-मैच नहीं।',
    ],
    howItWorks: [
      ['Confirm a match only after party and amount check. This does not file GST or change invoice tax.', 'पार्टी/राशि जाँचकर मैच। GST फाइल या बिल टैक्स नहीं।'],
    ],
    relatedPages: [
      { path: '/payments/reconciliation', labelKey: 'nav.bankReconciliation' },
      { path: '/payments/statements', labelKey: 'nav.bankStatements' },
      { path: '/accounting/journals', labelKey: 'nav.journals' },
    ],
    nextActions: [
      ['Commit statements on the payments side, then clear GL lines here.', 'पेमेंट्स पर स्टेटमेंट कमिट करें, यहाँ GL मिलाएँ।'],
    ],
  }),
];
