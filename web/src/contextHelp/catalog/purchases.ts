import { helpPage } from '../buildPage';
import type { ContextHelpPage } from '../types';

export const PURCHASE_HELP: ContextHelpPage[] = [
  helpPage('purchase-invoice', {
    title: ['Purchase bill', 'खरीद बिल'],
    summary: [
      'There is no separate goods-received note. **t:common.complete** on a purchase posts stock **and** the supplier payable together.',
      'अलग GRN नहीं है। खरीद पर **t:common.complete** स्टॉक और सप्लायर देनदारी एक साथ लगाता है।',
    ],
    howItWorks: [
      [
        'Supplier, date, lines, GST, then Complete. If goods arrive later than the bill, keep the bill as draft until you can complete both, or use opening stock / a stock adjustment for timing.',
        'सप्लायर, तारीख, लाइनें, GST, फिर Complete। माल बिल से बाद आए तो ड्राफ्ट रखें, या ओपनिंग/स्टॉक एडजस्टमेंट से समय मिलाएँ।',
      ],
      [
        'Unregistered supplier: turn reverse charge on, or explicitly confirm no RCM. Completing without one of those is blocked.',
        'अनरजिस्टर्ड सप्लायर: RCM चालू करें, या साफ़ पुष्टि करें कि RCM नहीं। दोनों में से एक बिना Complete नहीं।',
      ],
    ],
    businessImpact: [
      [
        'Complete fans out: stock in the bill’s godown → supplier outstanding → ITC review (starts Unreviewed) → GST 2B/3B worksheets → purchase reports.',
        'Complete का असर: बिल वाले गोदाम में स्टॉक → सप्लायर बकाया → ITC समीक्षा (Unreviewed से) → 2B/3B वर्कशीट → खरीद रिपोर्ट।',
      ],
    ],
    keyRules: [
      [
        'Same GST/period gates as sales, plus: duplicate supplier bill number needs confirm; foreign/import uses Bill of Entry + NON_GST purchase (do not put customs IGST on a GST purchase invoice).',
        'सेल्स जैसे GST/पीरियड द्वार, साथ में: डुप्लिकेट सप्लायर बिल नंबर पर पुष्टि; आयात पर Bill of Entry + NON_GST खरीद (कस्टम IGST GST खरीद बिल पर न डालें)।',
      ],
      [
        'New purchases start as Unreviewed ITC. Mark Claimable only after review. If GSTR-2B rows exist, Claimable also needs the 2B row matched.',
        'नई खरीद ITC Unreviewed से शुरू। समीक्षा बाद Claimable करें। 2B पंक्तियाँ हों तो मैच भी चाहिए।',
      ],
    ],
    commonMistakes: [
      [
        'Claiming ITC on Complete day without 2B match. Table 4A in GSTR-3B does not auto-accept purchases.',
        'Complete के दिन बिना 2B मैच ITC क्लेम। GSTR-3B टेबल 4A खरीद ऑटो-एक्सेप्ट नहीं करता।',
      ],
      [
        'Putting batch-tracked lines through Complete without a batch number.',
        'बैच ट्रैक लाइनें बिना बैच नंबर Complete करना।',
      ],
    ],
    relatedPages: [
      { path: '/purchases/history', labelKey: 'nav.purchaseHistory' },
      { path: '/purchases/payments', labelKey: 'nav.supplierPayments' },
      { path: '/inventory/stock', labelKey: 'nav.currentStock' },
      { path: '/purchases/suppliers', labelKey: 'nav.suppliers' },
    ],
    nextActions: [
      ['Complete when goods and bill both match. Then record a supplier payment and allocate it.', 'माल और बिल मिलें तब Complete करें। फिर सप्लायर भुगतान दर्ज कर आवंटित करें।'],
    ],
  }),

  helpPage('purchase-invoice-detail', {
    title: ['Purchase bill detail', 'खरीद बिल विवरण'],
    summary: [
      'View one purchase: status, tax, outstanding, ITC state. Opening the page does not post stock or change ITC.',
      'एक खरीद देखें: स्थिति, टैक्स, बकाया, ITC स्थिति। पेज खोलने से स्टॉक या ITC नहीं बदलता।',
    ],
    howItWorks: [
      ['Follow-up actions (payment, debit note, return) live on this bill or the matching purchase lists.', 'भुगतान, डेबिट नोट, रिटर्न इसी बिल या खरीद सूचियों से होते हैं।'],
    ],
    businessImpact: [
      ['Supplier ledger and ITC worksheets read this completed bill. Drafts are not in payables.', 'सप्लायर लेजर और ITC वर्कशीट पूर्ण बिल पढ़ते हैं। ड्राफ्ट देनदारी में नहीं।'],
    ],
    keyRules: [
      ['A completed purchase is not rewritten as a normal edit; use purchase debit/credit notes or cancel when allowed.', 'पूर्ण खरीद सामान्य एडिट से नहीं बदलती; खरीद डेबिट/क्रेडिट नोट या अनुमति पर रद्द।'],
    ],
    commonMistakes: [
      ['Treating Unreviewed ITC as already claimed in GSTR-3B.', 'Unreviewed ITC को GSTR-3B में क्लेम्ड समझना।'],
    ],
    relatedPages: [
      { path: '/purchases/history', labelKey: 'nav.purchaseHistory' },
      { path: '/purchases/payments', labelKey: 'nav.supplierPayments' },
      { path: '/purchases/debit-notes', labelKey: 'nav.purchaseDebitNotes' },
    ],
    nextActions: [
      ['If the bill is unpaid, record a supplier payment. If ITC is ready, review it against 2B.', 'बिल बाकी हो तो सप्लायर भुगतान दर्ज करें। ITC तैयार हो तो 2B से मिलाएँ।'],
    ],
  }),

  helpPage('purchase-history', {
    title: ['Purchase history', 'खरीद इतिहास'],
    summary: [
      'All purchase bills. Open a row to view or continue a draft. List actions use the same Complete and cancel rules as the editor.',
      'सभी खरीद बिल। पंक्ति खोलकर देखें या ड्राफ्ट जारी रखें। सूची की क्रियाएँ एडिटर जैसे नियम मानती हैं।',
    ],
    howItWorks: [
      ['Filter by status and party. Complete from the list still checks GST, RCM and stock rules.', 'स्थिति और पार्टी से फ़िल्टर। सूची से Complete भी GST/RCM/स्टॉक जाँचता है।'],
    ],
    businessImpact: [
      ['This list is a reader of purchase status. Completing a bill is what updates stock and payables.', 'यह सूची खरीद स्थिति पढ़ती है। Complete से स्टॉक और देनदारी अपडेट होती है।'],
    ],
    keyRules: [
      ['Duplicate supplier + bill number is usually a paste error; confirm only if the printer reused numbers.', 'सप्लायर + बिल नंबर दोहराव अक्सर पेस्ट गलती है; प्रिंटर ने नंबर दोहराया हो तभी पुष्टि करें।'],
    ],
    commonMistakes: [
      ['Expecting a GRN step before the bill appears here. Complete on the bill is the inward.', 'यहाँ से पहले GRN ढूँढना। बिल Complete ही इनवार्ड है।'],
    ],
    relatedPages: [
      { path: '/purchases/new', labelKey: 'nav.newPurchase' },
      { path: '/purchases/payments', labelKey: 'nav.supplierPayments' },
    ],
    nextActions: [
      ['Clear drafts that already match goods received.', 'जो माल आ चुका उनके ड्राफ्ट Complete करें।'],
    ],
  }),

  helpPage('purchase-orders', {
    title: ['Purchase orders', 'खरीद ऑर्डर'],
    summary: [
      'Orders to suppliers. Completing a purchase bill against received goods is what posts stock — the PO itself is not the inward.',
      'सप्लायर को ऑर्डर। माल आने पर खरीद बिल Complete करने से स्टॉक लगता है — PO खुद इनवार्ड नहीं है।',
    ],
    howItWorks: [
      ['Create the order, send it, then enter the supplier bill when goods and rates match.', 'ऑर्डर बनाएँ, भेजें, माल और दर मिलने पर सप्लायर बिल दर्ज करें।'],
    ],
    businessImpact: [
      ['A PO does not by itself raise payables or ITC.', 'PO अकेले देनदारी या ITC नहीं बढ़ाता।'],
    ],
    keyRules: [
      ['Do not Complete a purchase bill for goods that never arrived; keep the bill draft.', 'जो माल नहीं आया उसके खरीद बिल Complete न करें; ड्राफ्ट रखें।'],
    ],
    commonMistakes: [
      ['Treating PO Complete as stock in hand.', 'PO Complete को स्टॉक हाथ में समझना।'],
    ],
    relatedPages: [
      { path: '/purchases/new', labelKey: 'nav.newPurchase' },
      { path: '/purchases/suppliers', labelKey: 'nav.suppliers' },
    ],
    nextActions: [
      ['When the supplier bill arrives, create a purchase and Complete it.', 'सप्लायर बिल आए तो खरीद बनाकर Complete करें।'],
    ],
  }),

  helpPage('suppliers', {
    title: ['Suppliers', 'सप्लायर'],
    summary: [
      'Supplier master: name, GSTIN, state. Saving a supplier does not create a bill or ITC.',
      'सप्लायर मास्टर: नाम, GSTIN, राज्य। सेव करने से बिल या ITC नहीं बनता।',
    ],
    howItWorks: [
      ['GSTIN and state drive purchase tax (IGST vs CGST/SGST) and RCM prompts.', 'GSTIN और राज्य खरीद टैक्स (IGST बनाम CGST/SGST) और RCM संकेत चलाते हैं।'],
    ],
    businessImpact: [
      ['Wrong GSTIN here flows into every later purchase and 2B match.', 'गलत GSTIN हर बाद की खरीद और 2B मैच में जाता है।'],
    ],
    keyRules: [
      ['Unregistered suppliers need RCM or an explicit no-RCM confirm on each bill.', 'अनरजिस्टर्ड सप्लायर पर हर बिल में RCM या साफ़ no-RCM पुष्टि।'],
    ],
    commonMistakes: [
      ['Re-creating the same supplier with a slightly different name, splitting payables.', 'थोड़े अलग नाम से वही सप्लायर दोबारा बनाना — देनदारी बँट जाती है।'],
    ],
    relatedPages: [
      { path: '/purchases/new', labelKey: 'nav.newPurchase' },
      { path: '/purchases/payments', labelKey: 'nav.supplierPayments' },
    ],
    nextActions: [
      ['Fill GSTIN before the first GST purchase.', 'पहले GST खरीद से पहले GSTIN भरें।'],
    ],
  }),

  helpPage('supplier-payments', {
    title: ['Supplier payments', 'सप्लायर भुगतान'],
    summary: [
      'Record money out and allocate it to completed purchase bills. Unallocated payments sit as advances and do not clear payables.',
      'जाने वाला पैसा दर्ज करें और पूर्ण खरीद बिलों पर आवंटित करें। बिना आवंटन अग्रिम रहता है।',
    ],
    howItWorks: [
      ['Party must match. You cannot allocate more than the payment’s remainder or the bill’s outstanding.', 'पार्टी मिलनी चाहिए। भुगतान की बाकी या बिल बकाया से ज्यादा आवंटन नहीं।'],
    ],
    businessImpact: [
      ['Allocation reduces supplier outstanding and purchase ageing. Cash book records the payment mode.', 'आवंटन सप्लायर बकाया घटाता है। कैश बुक भुगतान मोड लिखती है।'],
    ],
    keyRules: [
      ['Closed period can block posting a payment into a locked month.', 'बंद पीरियड में उस महीने का भुगतान रुक सकता है।'],
    ],
    commonMistakes: [
      ['Paying the wrong supplier, then failing allocation with party mismatch.', 'गलत सप्लायर को भुगतान — पार्टी मिसमैच।'],
    ],
    relatedPages: [
      { path: '/purchases/history', labelKey: 'nav.purchaseHistory' },
      { path: '/reports/supplier-ledger', labelKey: 'nav.supplierLedger' },
    ],
    nextActions: [
      ['Allocate every payment to the bills it belongs to before trusting payables KPIs.', 'देनदारी KPI पर भरोसा करने से पहले हर भुगतान बिलों पर आवंटित करें।'],
    ],
  }),

  helpPage('purchase-returns', {
    title: ['Purchase returns', 'खरीद वापसी'],
    summary: [
      'Return goods to a supplier against a completed purchase. Completing the return takes stock out and adjusts the supplier.',
      'पूर्ण खरीद के विरुद्ध सप्लायर को माल लौटाएँ। Complete पर स्टॉक निकलता है और सप्लायर समायोजित होता है।',
    ],
    howItWorks: [
      ['Quantity cannot exceed what remains returnable on the original bill.', 'मात्रा मूल बिल की बची वापसी से ज्यादा नहीं।'],
    ],
    businessImpact: [
      ['Stock down, payables down, ITC may need reversal via the linked purchase credit note path.', 'स्टॉक कम, देनदारी कम; ITC उलटने के लिए खरीद क्रेडिट नोट पथ देखें।'],
    ],
    keyRules: [
      ['Do not cancel the original purchase if goods were accepted and then returned — use a return / credit note.', 'माल स्वीकार कर लौटाया हो तो मूल खरीद रद्द न करें — रिटर्न/क्रेडिट नोट।'],
    ],
    commonMistakes: [
      ['Returning more than was purchased on a line.', 'लाइन पर खरीदी से ज्यादा वापसी।'],
    ],
    relatedPages: [
      { path: '/purchases/history', labelKey: 'nav.purchaseHistory' },
      { path: '/purchases/credit-notes', labelKey: 'nav.purchaseCreditNotes' },
    ],
    nextActions: [
      ['Complete the return, then check stock and the supplier ledger.', 'रिटर्न Complete करें, स्टॉक और सप्लायर लेजर देखें।'],
    ],
  }),

  helpPage('purchase-credit-notes', {
    title: ['Purchase credit notes', 'खरीद क्रेडिट नोट'],
    summary: [
      'GST purchase credit notes must point at the original purchase so ITC reversal and GSTR worksheets stay tied to a real bill.',
      'GST खरीद क्रेडिट नोट मूल खरीद से जुड़ना चाहिए ताकि ITC उलटाव और GSTR किसी असली बिल से बँधे।',
    ],
    howItWorks: [
      ['Create and Complete the purchase first, then add the credit note.', 'पहले खरीद Complete करें, फिर क्रेडिट नोट जोड़ें।'],
    ],
    businessImpact: [
      ['Reduces supplier outstanding and claimable ITC on worksheets.', 'सप्लायर बकाया और क्लेम योग्य ITC घटता है।'],
    ],
    keyRules: [
      ['Completed notes are not line-edited.', 'पूर्ण नोट की लाइनें एडिट नहीं।'],
    ],
    commonMistakes: [
      ['Booking a floating credit note with no original purchase.', 'बिना मूल खरीद के तैरता क्रेडिट नोट।'],
    ],
    relatedPages: [
      { path: '/purchases/history', labelKey: 'nav.purchaseHistory' },
      { path: '/purchases/debit-notes', labelKey: 'nav.purchaseDebitNotes' },
    ],
    nextActions: [
      ['Link the purchase, Complete, then review ITC.', 'खरीद लिंक करें, Complete करें, ITC समीक्षा करें।'],
    ],
  }),

  helpPage('purchase-debit-notes', {
    title: ['Purchase debit notes', 'खरीद डेबिट नोट'],
    summary: [
      'Increases what you owe the supplier after a completed purchase (extra charge, under-billed by them).',
      'पूर्ण खरीद के बाद सप्लायर को देनदारी बढ़ाता है (अतिरिक्त चार्ज, उनका कम बिल)।',
    ],
    howItWorks: [
      ['Complete the note; it hits payables and GST worksheets. It does not by itself add stock.', 'नोट Complete करें; देनदारी और GST में जाता है। अकेले स्टॉक नहीं बढ़ाता।'],
    ],
    businessImpact: [
      ['Payables and, where tax applies, ITC/expense treatment follow the note — check the tax on the lines.', 'देनदारी और टैक्स लागू हो तो ITC/खर्च नोट की लाइनों से।'],
    ],
    keyRules: [
      ['Use a new purchase bill if additional goods arrived; use a debit note for value-only extras on an existing bill.', 'अतिरिक्त माल आया हो तो नई खरीद; मौजूदा बिल पर केवल मूल्य हो तो डेबिट नोट।'],
    ],
    commonMistakes: [
      ['Using a debit note when goods arrived — that would skip stock.', 'माल आने पर डेबिट नोट — स्टॉक छूट जाएगा।'],
    ],
    relatedPages: [
      { path: '/purchases/history', labelKey: 'nav.purchaseHistory' },
      { path: '/purchases/new', labelKey: 'nav.newPurchase' },
    ],
    nextActions: [
      ['Complete the note, then pay and allocate if you owe the extra.', 'नोट Complete करें, अतिरिक्त देन हो तो भुगतान आवंटित करें।'],
    ],
  }),

  helpPage('bills-of-entry', {
    title: ['Bills of Entry', 'बिल ऑफ एंट्री'],
    summary: [
      'Customs IGST/cess for imports. Then book landed goods as a NON_GST purchase for that supplier and link the completed BoE. Do not put customs IGST on a GST purchase invoice.',
      'आयात का कस्टम IGST/सेस। फिर उसी सप्लायर पर NON_GST खरीद से लैंडेड माल जोड़ें और पूर्ण BoE लिंक करें। कस्टम IGST GST खरीद बिल पर न डालें।',
    ],
    howItWorks: [
      ['Complete the BoE first, then the NON_GST purchase that carries the goods into stock.', 'पहले BoE Complete करें, फिर NON_GST खरीद से माल स्टॉक में लाएँ।'],
    ],
    businessImpact: [
      ['Customs tax and stock follow two documents on purpose so GST purchase invoices stay domestic.', 'कस्टम टैक्स और स्टॉक दो दस्तावेज़ों पर हैं ताकि GST खरीद बिल घरेलू रहें।'],
    ],
    keyRules: [
      ['This module may be dark unless enabled for the company. If the page is available, still follow NON_GST + BoE link.', 'मॉड्यूल कंपनी पर बंद हो सकता है। पेज दिखे तो भी NON_GST + BoE लिंक अपनाएँ।'],
    ],
    commonMistakes: [
      ['Entering customs IGST as a normal GST purchase line.', 'कस्टम IGST को सामान्य GST खरीद लाइन बनाना।'],
    ],
    relatedPages: [
      { path: '/purchases/new', labelKey: 'nav.newPurchase' },
      { path: '/purchases/suppliers', labelKey: 'nav.suppliers' },
    ],
    nextActions: [
      ['Complete BoE, then create the linked NON_GST purchase.', 'BoE Complete करें, फिर लिंक की NON_GST खरीद बनाएँ।'],
    ],
  }),

  helpPage('purchase-bill-upload', {
    title: ['Upload purchase bill', 'खरीद बिल अपलोड'],
    summary: [
      'Photo or PDF extract → a draft purchase. It will not invent GST rate or quantity. You still Complete after checking HSN and GSTIN.',
      'फोटो/PDF से ड्राफ्ट खरीद। GST दर या मात्रा नहीं गढ़ता। HSN/GSTIN जाँचकर Complete आप करते हैं।',
    ],
    howItWorks: [
      ['Needs import capability. Review every line before Complete.', 'इम्पोर्ट अनुमति चाहिए। Complete से पहले हर लाइन जाँचें।'],
    ],
    businessImpact: [
      ['No stock or payable until Complete.', 'Complete तक स्टॉक या देनदारी नहीं।'],
    ],
    keyRules: [
      ['OCR is aid-only.', 'OCR केवल सहायता है।'],
    ],
    commonMistakes: [
      ['Completing an extract that used the wrong supplier GSTIN.', 'गलत सप्लायर GSTIN वाले निकाल पर Complete।'],
    ],
    relatedPages: [
      { path: '/purchases/history', labelKey: 'nav.purchaseHistory' },
      { path: '/purchases/new', labelKey: 'nav.newPurchase' },
    ],
    nextActions: [
      ['Open the draft, fix supplier and lines, Complete.', 'ड्राफ्ट खोलें, सप्लायर/लाइनें ठीक करें, Complete करें।'],
    ],
  }),
];
