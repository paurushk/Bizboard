import { helpPage } from '../buildPage';
import type { ContextHelpPage } from '../types';

export const REPORTS_HELP: ContextHelpPage[] = [
  helpPage('sales-reports', {
    title: ['Sales reports', 'बिक्री रिपोर्ट'],
    summary: [
      'Reads completed sales (and related notes). It does not change bills. Drafts are not revenue.',
      'पूर्ण बिक्री (और नोट) पढ़ती है। बिल नहीं बदलती। ड्राफ्ट राजस्व नहीं।',
    ],
    howItWorks: [
      ['Filter period and export if you have export permission. Totals follow completed documents plus credit/debit notes.', 'पीरियड फ़िल्टर; एक्सपोर्ट अनुमति हो तो निर्यात। योग पूर्ण दस्तावेज़ + क्रेडिट/डेबिट नोट।'],
    ],
    businessImpact: [
      ['A return or credit note after month-end will change this report for that period on the next open.', 'महीने बाद रिटर्न/क्रेडिट नोट अगली बार उसी पीरियड की रिपोर्ट बदलता है।'],
    ],
    keyRules: [
      ['Needs view-financial-reports. This is not a GST filing.', 'वित्तीय रिपोर्ट अनुमति। GST फाइलिंग नहीं।'],
    ],
    commonMistakes: [
      ['Comparing this to GSTR-1 without picking the same GSTIN and tax period.', 'इसे GSTR-1 से बिना उसी GSTIN/पीरियड के तुलना।'],
    ],
    relatedPages: [
      { path: '/sales/history', labelKey: 'nav.salesHistory' },
      { path: '/reports/gstr1', labelKey: 'nav.gstr1' },
    ],
    nextActions: [
      ['If a number looks wrong, open the invoice and check Complete, return and credit notes.', 'संख्या गलत लगे तो बिल खोलकर Complete, रिटर्न और क्रेडिट नोट देखें।'],
    ],
  }),

  helpPage('purchase-reports', {
    title: ['Purchase reports', 'खरीद रिपोर्ट'],
    summary: [
      'Reads completed purchases and notes. Unreviewed ITC is still in this spend picture if the bill is completed — claim status is separate.',
      'पूर्ण खरीद और नोट पढ़ती है। बिल पूर्ण हो तो Unreviewed ITC भी खर्च में दिख सकता है — क्लेम स्थिति अलग है।',
    ],
    howItWorks: [
      ['Filter period. Export needs permission.', 'पीरियड फ़िल्टर। एक्सपोर्ट को अनुमति।'],
    ],
    businessImpact: [
      ['Purchase returns/credit notes reduce what this report shows for the original period.', 'खरीद रिटर्न/क्रेडिट नोट मूल पीरियड की दिखावट घटाते हैं।'],
    ],
    keyRules: [
      ['Not a substitute for GSTR-2B / 3B worksheets.', 'GSTR-2B/3B की जगह नहीं।'],
    ],
    commonMistakes: [
      ['Using this as claimed ITC.', 'इसे क्लेम्ड ITC समझना।'],
    ],
    relatedPages: [
      { path: '/purchases/history', labelKey: 'nav.purchaseHistory' },
      { path: '/reports/gstr2b', labelKey: 'nav.gstr2b' },
    ],
    nextActions: [
      ['Tie large numbers back to purchase history, then to 2B if you are preparing ITC.', 'बड़ी संख्या खरीद इतिहास से मिलाएँ; ITC हो तो 2B देखें।'],
    ],
  }),

  helpPage('inventory-reports', {
    title: ['Inventory reports', 'इन्वेंटरी रिपोर्ट'],
    summary: [
      'Stock movement and valuation readers. They do not adjust stock.',
      'स्टॉक मूवमेंट/वैल्यूएशन पढ़ती हैं। स्टॉक एडजस्ट नहीं करतीं।',
    ],
    howItWorks: [
      ['Pick period/godown as offered on the page. Valuation follows the company’s costing method.', 'पेज पर पीरियड/गोदाम चुनें। वैल्यूएशन कंपनी की कॉस्टिंग विधि से।'],
    ],
    businessImpact: [
      ['A posted count or adjustment yesterday is in today’s report; a draft purchase is not.', 'कल की गिनती/एडजस्टमेंट आज की रिपोर्ट में; ड्राफ्ट खरीद नहीं।'],
    ],
    keyRules: [
      ['Available vs on-hand: reports may show either — read the column header.', 'उपलब्ध बनाम हाथ में — कॉलम हेडर पढ़ें।'],
    ],
    commonMistakes: [
      ['Expecting draft bills to appear as reserved here. Reservations come from confirmed orders/drafts as implemented on stock, not always on every report column.', 'ड्राफ्ट बिल को यहाँ रिज़र्व समझना। रिज़र्व स्टॉक स्क्रीन पर ऑर्डर से आता है।'],
    ],
    relatedPages: [
      { path: '/inventory/stock', labelKey: 'nav.currentStock' },
      { path: '/reports/stock-valuation', labelKey: 'nav.stockValuation' },
    ],
    nextActions: [
      ['If valuation looks off, check godown, batches and last count date.', 'वैल्यूएशन गलत लगे तो गोदाम, बैच और आखिरी गिनती देखें।'],
    ],
  }),

  helpPage('customer-ledger', {
    title: ['Customer ledger', 'ग्राहक लेजर'],
    summary: [
      'Not a table you type into. It is built from completed invoices, credit/debit notes and receipt allocations. Missing allocation makes outstanding look unpaid.',
      'टाइप करने की टेबल नहीं। पूर्ण बिल, क्रेडिट/डेबिट नोट और रसीद आवंटन से बनता है। बिना आवंटन बकाया unpaid दिखता है।',
    ],
    howItWorks: [
      ['When accounting books are on and outstanding basis is GL, receivables can follow GL accounts instead of document math.', 'खाते चालू और outstanding GL हो तो प्राप्य GL से आ सकते हैं, दस्तावेज़ गणित से नहीं।'],
    ],
    businessImpact: [
      ['This is what you show a customer for statement purposes, together with the invoice PDFs.', 'ग्राहक स्टेटमेंट के लिए यह, साथ में बिल PDF।'],
    ],
    keyRules: [
      ['Unallocated receipts sit as advances.', 'बिना आवंटन रसीदें अग्रिम रहती हैं।'],
    ],
    commonMistakes: [
      ['Editing a completed invoice to “fix” the ledger. Allocate or issue a note instead.', 'लेजर ठीक करने के लिए पूर्ण बिल एडिट — आवंटित करें या नोट बनाएँ।'],
    ],
    relatedPages: [
      { path: '/sales/receipts', labelKey: 'nav.receipts' },
      { path: '/sales/history', labelKey: 'nav.salesHistory' },
    ],
    nextActions: [
      ['Pick the customer, scan allocations, then take or allocate a receipt if they still owe.', 'ग्राहक चुनें, आवंटन देखें, बकाया हो तो रसीद लें/आवंटित करें।'],
    ],
  }),

  helpPage('supplier-ledger', {
    title: ['Supplier ledger', 'सप्लायर लेजर'],
    summary: [
      'Built from completed purchases, purchase notes and payment allocations — not a manual ledger.',
      'पूर्ण खरीद, खरीद नोट और भुगतान आवंटन से — मैनुअल लेजर नहीं।',
    ],
    howItWorks: [
      ['Open a supplier and read bills vs payments. Unallocated payments are advances.', 'सप्लायर खोलें, बिल बनाम भुगतान। बिना आवंटन अग्रिम।'],
    ],
    businessImpact: [
      ['Payables KPIs and ageing follow this same math.', 'देनदारी KPI और एजिंग यही गणित।'],
    ],
    keyRules: [
      ['Books-on GL outstanding can differ from a simple bill list.', 'खाते चालू हों तो GL बकाया सरल बिल सूची से भिन्न हो सकता है।'],
    ],
    commonMistakes: [
      ['Paying without allocating, then trusting the KPI as settled.', 'बिना आवंटन भुगतान कर KPI चुकता मानना।'],
    ],
    relatedPages: [
      { path: '/purchases/payments', labelKey: 'nav.supplierPayments' },
      { path: '/purchases/history', labelKey: 'nav.purchaseHistory' },
    ],
    nextActions: [
      ['Allocate open payments, then re-open this ledger.', 'खुले भुगतान आवंटित करें, फिर लेजर खोलें।'],
    ],
  }),

  helpPage('cash-book', {
    title: ['Cash book', 'कैश बुक'],
    summary: [
      'Actual receipts and payments (the day’s galla). Insights cashflow is a forecast and is not tax or bank truth.',
      'वास्तविक रसीदें और भुगतान (गल्ला)। Insights कैशफ्लो पूर्वानुमान है — टैक्स/बैंक सत्य नहीं।',
    ],
    howItWorks: [
      ['Filter the day/period. Modes follow how you recorded the receipt or payment.', 'दिन/पीरियड फ़िल्टर। मोड रसीद/भुगतान जैसे दर्ज हुए।'],
    ],
    businessImpact: [
      ['This is cash control, not GST output.', 'यह कैश नियंत्रण है, GST आउटपुट नहीं।'],
    ],
    keyRules: [
      ['Needs view-financial-reports.', 'वित्तीय रिपोर्ट अनुमति।'],
    ],
    commonMistakes: [
      ['Reconciling Insights cashflow to the bank.', 'Insights कैशफ्लो को बैंक से मिलाना।'],
    ],
    relatedPages: [
      { path: '/sales/receipts', labelKey: 'nav.receipts' },
      { path: '/purchases/payments', labelKey: 'nav.supplierPayments' },
    ],
    nextActions: [
      ['Compare today’s cash mode total to the drawer, then record missing receipts.', 'आज के नकद योग को दराज से मिलाएँ, छूटी रसीदें दर्ज करें।'],
    ],
  }),

  helpPage('gst-return', {
    title: ['GST worksheets', 'GST वर्कशीट'],
    summary: [
      'GSTR-1, GSTR-3B, GSTR-9, 2B/IMS, CMP-08 and GSTR-4 here are **offline worksheets** (and optional JSON). They do **not** file on the GST portal.',
      'GSTR-1, 3B, 9, 2B/IMS, CMP-08, GSTR-4 **ऑफ़लाइन वर्कशीट** (और वैकल्पिक JSON) हैं। GST पोर्टल पर फाइल **नहीं** करते।',
    ],
    howItWorks: [
      [
        'With more than one GSTIN, pick the filing GSTIN at the top. Each GSTIN has its own worksheet. Composition companies use CMP-08 / GSTR-4 aids, not regular GSTR-1/3B.',
        'एक से ज्यादा GSTIN हो तो ऊपर फाइलिंग GSTIN चुनें। Composition पर CMP-08/GSTR-4, नियमित GSTR-1/3B नहीं।',
      ],
      [
        'GSTR-3B Table 4A follows IMS/2B review. There is no auto-accept. Books stay the source of truth.',
        'GSTR-3B टेबल 4A IMS/2B समीक्षा से। ऑटो-एक्सेप्ट नहीं। किताबें स्रोत हैं।',
      ],
    ],
    businessImpact: [
      [
        'Only **completed** GST/TAX documents in that period and GSTIN appear. Drafts and the other GSTIN will look like “missing sales”.',
        'उस पीरियड और GSTIN के **पूर्ण** GST/TAX दस्तावेज़ दिखते हैं। ड्राफ्ट और दूसरा GSTIN “गायब बिक्री” जैसा लगता है।',
      ],
    ],
    keyRules: [
      [
        'You or your CA still file on gst.gov.in. GSTR-6/7/8 screens are honesty stubs, not filing engines. Live e-Invoice/e-Way to NIC is fail-closed until GSP is certified.',
        'फाइलिंग gst.gov.in पर आप/CA करते हैं। GSTR-6/7/8 स्टब हैं। NIC पर लाइव e-Invoice/e-Way GSP प्रमाण तक बंद।',
      ],
    ],
    commonMistakes: [
      ['Treating a successful Complete as already filed. Completing a bill is books, not the portal.', 'Complete को फाइलिंग समझना। Complete किताबें हैं, पोर्टल नहीं।'],
      ['Leaving the wrong GSTIN selected and exporting empty JSON.', 'गलत GSTIN चुनकर खाली JSON।'],
    ],
    relatedPages: [
      { path: '/sales/history', labelKey: 'nav.salesHistory' },
      { path: '/purchases/history', labelKey: 'nav.purchaseHistory' },
      { path: '/settings/gst', labelKey: 'nav.gst' },
    ],
    nextActions: [
      ['Pick GSTIN and period, review rows against sales/purchase history, export JSON if your CA uses the offline tool, then file on the portal.', 'GSTIN और पीरियड चुनें, इतिहास से पंक्तियाँ मिलाएँ, JSON निर्यात करें, पोर्टल पर फाइल करें।'],
    ],
  }),

  helpPage('gstr-2b', {
    title: ['GSTR-2B / IMS', 'GSTR-2B / IMS'],
    summary: [
      'Ingest 2B/IMS rows, then Accept, Reject (remark required) or Park. Do not auto-claim. Soft-closing a GST period can deemed-accept remaining IMS — Owner only.',
      '2B/IMS पंक्तियाँ लें, Accept/Reject (टिप्पणी) या Park। ऑटो-क्लेम नहीं। GST पीरियड सॉफ्ट-क्लोज बाकी IMS deemed-accept कर सकता है — केवल ओनर।',
    ],
    howItWorks: [
      ['Match to purchases before marking ITC Claimable when 2B data exists.', '2B हो तो ITC Claimable से पहले खरीद से मैच करें।'],
    ],
    businessImpact: [
      ['This review feeds GSTR-3B ITC worksheets. Books remain the source of truth.', 'यह समीक्षा GSTR-3B ITC वर्कशीट में जाती है। किताबें स्रोत रहती हैं।'],
    ],
    keyRules: [
      ['Reject needs a remark. Park is not a claim.', 'Reject पर टिप्पणी। Park क्लेम नहीं।'],
    ],
    commonMistakes: [
      ['Marking everything Claimable without a 2B match when 2B rows exist.', '2B पंक्तियाँ हों बिना मैच सब Claimable करना।'],
    ],
    relatedPages: [
      { path: '/purchases/history', labelKey: 'nav.purchaseHistory' },
      { path: '/reports/gstr3b', labelKey: 'nav.gstr3b' },
      { path: '/reports/missing-documents', labelKey: 'nav.missingDocuments' },
    ],
    nextActions: [
      ['Ingest the period, accept/reject/park each row, then open GSTR-3B as a worksheet only.', 'पीरियड इनजेस्ट करें, पंक्तियाँ तय करें, फिर GSTR-3B केवल वर्कशीट के रूप में खोलें।'],
    ],
  }),

  helpPage('missing-documents', {
    title: ['Missing bills', 'गायब बिल'],
    summary: [
      'Bills seen in IMS/2B that you have not booked yet (and the friendlier “What my CA needs” view). It does not file GST.',
      'IMS/2B में दिखे जो आपने अभी बुक नहीं किए (“CA को क्या चाहिए” वही)। GST फाइल नहीं करता।',
    ],
    howItWorks: [
      ['Request a bill or attach a photo into import where the page offers it. Then Complete a real purchase.', 'पेज दे तो बिल माँगें या फोटो इम्पोर्ट करें। फिर असली खरीद Complete करें।'],
    ],
    businessImpact: [
      ['Unbooked 2B rows mean you may under-claim ITC if you file without them.', 'अनबुक 2B पंक्तियाँ बिना उन्हें फाइल करने पर ITC कम क्लेम।'],
    ],
    keyRules: [
      ['This is a gap list, not auto-create of purchases.', 'यह गैप सूची है, खरीद ऑटो-क्रिएट नहीं।'],
    ],
    commonMistakes: [
      ['Ignoring the list until after filing.', 'फाइलिंग बाद सूची देखना।'],
    ],
    relatedPages: [
      { path: '/purchases/new', labelKey: 'nav.newPurchase' },
      { path: '/reports/gstr2b', labelKey: 'nav.gstr2b' },
    ],
    nextActions: [
      ['Book or import the missing purchase, Complete it, then return to 2B.', 'गायब खरीद बुक/इम्पोर्ट कर Complete करें, फिर 2B पर लौटें।'],
    ],
  }),

  helpPage('statutory-events', {
    title: ['Statutory events', 'वैधानिक घटनाएँ'],
    summary: [
      'GST and compliance dates for the company. A reminder aid, not a filing confirmation from the portal.',
      'कंपनी की GST/कंप्लायंस तिथियाँ। याद दिलाना है, पोर्टल की फाइलिंग पुष्टि नहीं।',
    ],
    howItWorks: [
      ['Scan upcoming dates. Completing work still happens on invoices, 2B and the GST portal.', 'आने वाली तिथियाँ देखें। काम बिल, 2B और पोर्टल पर ही होता है।'],
    ],
    businessImpact: [
      ['Missing a date here does not by itself block Complete; period lock does.', 'यहाँ तिथि चूकने से Complete नहीं रुकता; पीरियड लॉक रोकता है।'],
    ],
    keyRules: [
      ['Not proof that a return was filed.', 'रिटर्न फाइल होने का प्रमाण नहीं।'],
    ],
    commonMistakes: [
      ['Treating a green date as “already filed”.', 'हरी तिथि को फाइल हो चुका समझना।'],
    ],
    relatedPages: [
      { path: '/reports/gstr1', labelKey: 'nav.gstr1' },
      { path: '/accounting/periods', labelKey: 'nav.accountingPeriods' },
    ],
    nextActions: [
      ['Before a due date, close Completes for that period and review worksheets with your CA.', 'नियत तिथि से पहले उस पीरियड के Complete बंद करें और CA के साथ वर्कशीट देखें।'],
    ],
  }),

  helpPage('books-report', {
    title: ['Accounting reports', 'लेखांकन रिपोर्ट'],
    summary: [
      'Trial balance, P&L, balance sheet and books health read posted journals. They need accounting enabled. They do not file GST.',
      'ट्रायल बैलेंस, P&L, बैलेंस शीट, बुक्स हेल्थ पोस्टेड जर्नल पढ़ते हैं। लेखांकन चालू चाहिए। GST फाइल नहीं।',
    ],
    howItWorks: [
      ['Invoice Complete posts to GL when books are on. Manual journals are extra and must balance.', 'खाते चालू हों तो बिल Complete GL पर पोस्ट। मैनुअल जर्नल बैलेंस होने चाहिए।'],
    ],
    businessImpact: [
      ['Wrong tax on a bill is already in GL after Complete; fix with a note, not by typing the report.', 'गलत टैक्स Complete बाद GL में है; रिपोर्ट टाइप न करें — नोट से ठीक करें।'],
    ],
    keyRules: [
      ['Closed periods block money amends. Opening a report never reopens a period.', 'बंद पीरियड पैसे के संशोधन रोकते हैं। रिपोर्ट खोलना पीरियड नहीं खोलता।'],
    ],
    commonMistakes: [
      ['Comparing P&L to GSTR-3B line-by-line without your CA — different bases.', 'बिना CA P&L को GSTR-3B से लाइन-बाय-लाइन मिलाना — आधार अलग।'],
    ],
    relatedPages: [
      { path: '/accounting/journals', labelKey: 'nav.journals' },
      { path: '/accounting/periods', labelKey: 'nav.accountingPeriods' },
    ],
    nextActions: [
      ['If a balance looks wrong, open journals for that account, then the source invoice or payment.', 'बैलेंस गलत लगे तो उस खाते के जर्नल, फिर स्रोत बिल/भुगतान खोलें।'],
    ],
  }),

  helpPage('insights', {
    title: ['Insights', 'इनसाइट्स'],
    summary: [
      'Analytics and alerts. Best-seller style metrics treat a fully returned sale as not a live sale. Forecast cashflow is not the cash book.',
      'एनालिटिक्स और अलर्ट। पूरी वापसी वाली बिक्री को चालू बिक्री नहीं गिनते। कैशफ्लो पूर्वानुमान कैश बुक नहीं।',
    ],
    howItWorks: [
      ['Hub, alerts, health, cashflow and assistant are readers. The assistant will not replace Help for why a Complete is blocked.', 'हब, अलर्ट, हेल्थ, कैशफ्लो, असिस्टेंट पढ़ते हैं। Complete क्यों रुका, यह सहायता का काम है।'],
    ],
    businessImpact: [
      ['Decisions here should still be posted with a real bill, receipt or adjustment.', 'यहाँ का फैसला असली बिल/रसीद/एडजस्टमेंट से ही पोस्ट हो।'],
    ],
    keyRules: [
      ['Needs insights capability. Not tax or bank truth.', 'इनसाइट्स अनुमति। टैक्स/बैंक सत्य नहीं।'],
    ],
    commonMistakes: [
      ['Filing GST from an insights chart.', 'इनसाइट्स चार्ट से GST फाइल करना।'],
    ],
    relatedPages: [
      { path: '/', labelKey: 'nav.dashboard' },
      { path: '/reports/cash-book', labelKey: 'nav.cashBook' },
      { path: '/help', labelKey: 'nav.help' },
    ],
    nextActions: [
      ['Use an alert as a pointer, then open the document and apply the same Complete/allocate rules as elsewhere.', 'अलर्ट को संकेत मानें, दस्तावेज़ खोलकर वही Complete/आवंटन नियम लगाएँ।'],
    ],
  }),
];

export const SETTINGS_HELP: ContextHelpPage[] = [
  helpPage('company-settings', {
    title: ['Company settings', 'कंपनी सेटिंग'],
    summary: [
      'Shop identity, state, UPI VPA, optional dunning. State here drives default GST split on bills. Saving settings does not Complete any document.',
      'दुकान, राज्य, UPI VPA, वैकल्पिक डनिंग। राज्य बिलों पर GST स्प्लिट चलाता है। सेटिंग सेव कोई दस्तावेज़ Complete नहीं करता।',
    ],
    howItWorks: [
      ['Owner-managed. UPI QR on POS/invoices uses the VPA saved here.', 'ओनर। POS/बिल का UPI QR यहीं के VPA से।'],
    ],
    businessImpact: [
      ['Wrong state → wrong CGST/SGST vs IGST on later Completes.', 'गलत राज्य → बाद के Complete पर गलत CGST/SGST बनाम IGST।'],
    ],
    keyRules: [
      ['Dunning is opt-in (WhatsApp/SMS, quiet hours). Gateway-captured invoices are skipped.', 'डनिंग ऑप्ट-इन। गेटवे-कैप्चर्ड बिल छूटते हैं।'],
    ],
    commonMistakes: [
      ['Changing state after a year of bills without talking to your CA.', 'साल भर बिल बाद राज्य बदलना बिना CA।'],
    ],
    relatedPages: [
      { path: '/settings/gst', labelKey: 'nav.gst' },
      { path: '/pos', labelKey: 'nav.pos' },
    ],
    nextActions: [
      ['Confirm legal name, state and UPI before the first GST bill.', 'पहले GST बिल से पहले नाम, राज्य, UPI पक्का करें।'],
    ],
  }),

  helpPage('gst-settings', {
    title: ['GST settings', 'GST सेटिंग'],
    summary: [
      'Registration type, GSTIN(s), e-Invoice/e-Way toggles. Tax bills need a GSTIN so the tax office can match the sale. Only the Owner can change GSTIN.',
      'रजिस्ट्रेशन प्रकार, GSTIN, e-Invoice/e-Way। टैक्स बिल के लिए GSTIN। GSTIN केवल ओनर बदलते हैं।',
    ],
    howItWorks: [
      [
        'If you have more than one GSTIN, pick the right one on the bill before Complete. Invoice numbers are keyed by GSTIN and the April–March year when any GSTIN exists.',
        'एक से ज्यादा GSTIN हो तो Complete से पहले बिल पर सही चुनें। नंबर GSTIN और अप्रैल–मार्च वर्ष से जुड़ते हैं।',
      ],
    ],
    businessImpact: [
      ['Wrong registration type blocks GST/TAX Completes (composition/unregistered). Live NIC e-Invoice stays fail-closed until GSP is certified.', 'गलत रजिस्ट्रेशन GST/TAX Complete रोकता है। लाइव NIC e-Invoice GSP तक बंद।'],
    ],
    keyRules: [
      ['Godown ≠ GST branch. Add extra GSTINs here, not as warehouses.', 'गोदाम ≠ GST शाखा। अतिरिक्त GSTIN यहीं, गोदाम में नहीं।'],
    ],
    commonMistakes: [
      ['Completing with the wrong GSTIN selected on a multi-GSTIN company, then wondering why GSTR-1 is empty.', 'मल्टी-GSTIN पर गलत GSTIN से Complete — GSTR-1 खाली।'],
    ],
    relatedPages: [
      { path: '/sales/new', labelKey: 'nav.newInvoice' },
      { path: '/reports/gstr1', labelKey: 'nav.gstr1' },
    ],
    nextActions: [
      ['Add the 15-character GSTIN, set primary, then Complete a test draft only after place of supply is known.', '15 अक्षर GSTIN जोड़ें, प्राइमरी सेट करें, place of supply पता हो तब ड्राफ्ट Complete करें।'],
    ],
  }),

  helpPage('users-settings', {
    title: ['Users', 'उपयोगकर्ता'],
    summary: [
      'Owner, sales staff, accountant, viewer. Extra capabilities are per person. Only the Owner invites. You cannot invite another Owner.',
      'ओनर, सेल्स स्टाफ, अकाउंटेंट, व्यूअर। अतिरिक्त क्षमता व्यक्ति पर। आमंत्रण केवल ओनर। दूसरा ओनर आमंत्रित नहीं।',
    ],
    howItWorks: [
      ['Invite by email, optional password, or they set one at /invite.', 'ईमेल से आमंत्रण, वैकल्पिक पासवर्ड, या /invite पर सेट।'],
    ],
    businessImpact: [
      ['A viewer cannot Complete. A sales login without create-purchases cannot enter supplier bills.', 'व्यूअर Complete नहीं कर सकता। बिना खरीद अनुमति सेल्स लॉगिन सप्लायर बिल नहीं डालता।'],
    ],
    keyRules: [
      ['“Login cannot do this” is a role/capability gate, not a GST error.', '“लॉगिन यह नहीं कर सकता” भूमिका द्वार है, GST एरर नहीं।'],
    ],
    commonMistakes: [
      ['Sharing the Owner password instead of inviting a role.', 'भूमिका आमंत्रित करने की जगह ओनर पासवर्ड बाँटना।'],
    ],
    relatedPages: [
      { path: '/help', labelKey: 'nav.help' },
    ],
    nextActions: [
      ['Invite the smallest role that can do the job, then grant extra flags only if needed.', 'काम लायक सबसे छोटी भूमिका आमंत्रित करें, झंडे ज़रूरत पर।'],
    ],
  }),

  helpPage('import-data', {
    title: ['Import', 'इम्पोर्ट'],
    summary: [
      'Excel/CSV/Tally-style import. Red rows must be fixed before commit. Commit is the write; preview is not.',
      'Excel/CSV/Tally जैसा इम्पोर्ट। लाल पंक्तियाँ कमिट से पहले ठीक करें। कमिट लिखता है; प्रीव्यू नहीं।',
    ],
    howItWorks: [
      ['Needs import capability. Period lock still applies to money rows.', 'इम्पोर्ट अनुमति। पैसे की पंक्तियों पर पीरियड लॉक लगता है।'],
    ],
    businessImpact: [
      ['A committed import can create stock, parties and bills — same fan-out as typing them.', 'कमिटेड इम्पोर्ट स्टॉक, पार्टी, बिल बना सकता है — टाइप करने जैसा असर।'],
    ],
    keyRules: [
      ['Do not invent GST rates in the sheet. Commit blocked until errors clear.', 'शीट में GST दर न गढ़ें। एरर साफ़ होने तक कमिट बंद।'],
    ],
    commonMistakes: [
      ['Committing a preview that used the wrong GSTIN or godown for every row.', 'हर पंक्ति पर गलत GSTIN/गोदाम वाले प्रीव्यू को कमिट।'],
    ],
    relatedPages: [
      { path: '/inventory/products', labelKey: 'nav.products' },
      { path: '/settings/tally', labelKey: 'nav.tallyMigration' },
    ],
    nextActions: [
      ['Fix red rows, re-preview, commit, then spot-check a bill and stock.', 'लाल पंक्तियाँ ठीक करें, प्रीव्यू, कमिट, फिर एक बिल और स्टॉक जाँचें।'],
    ],
  }),

  helpPage('tally-migration', {
    title: ['Tally migration', 'टैली माइग्रेशन'],
    summary: [
      'Guided import from Tally. Same commit discipline as other imports: preview, fix, then commit. Not a live two-way sync.',
      'टैली से गाइडेड इम्पोर्ट। प्रीव्यू, ठीक, कमिट। लाइव दो-तरफ़ा सिंक नहीं।',
    ],
    howItWorks: [
      ['Follow the page steps. Masters first, then openings, then documents as the wizard allows.', 'पेज के चरण। पहले मास्टर, फिर ओपनिंग, फिर दस्तावेज़।'],
    ],
    businessImpact: [
      ['Committed Tally bills become Bizboard bills with the same Complete fan-out.', 'कमिटेड टैली बिल बिज़बोर्ड बिल बनते हैं — वही Complete असर।'],
    ],
    keyRules: [
      ['Needs Tally feature and import permission.', 'टैली फीचर और इम्पोर्ट अनुमति।'],
    ],
    commonMistakes: [
      ['Running migration twice and duplicating parties.', 'माइग्रेशन दो बार चलाकर पार्टी डुप्लिकेट।'],
    ],
    relatedPages: [
      { path: '/settings/import', labelKey: 'nav.importData' },
      { path: '/sales/history', labelKey: 'nav.salesHistory' },
    ],
    nextActions: [
      ['Finish one company file, verify ledgers, then train users on Complete vs draft.', 'एक कंपनी फाइल खत्म करें, लेजर जाँचें, फिर Complete बनाम ड्राफ्ट सिखाएँ।'],
    ],
  }),

  helpPage('backup-export', {
    title: ['Backup / export', 'बैकअप / निर्यात'],
    summary: [
      'Download company data you are allowed to export. Export does not change bills, stock or GST.',
      'अनुमति वाला कंपनी डेटा डाउनलोड। निर्यात बिल/स्टॉक/GST नहीं बदलता।',
    ],
    howItWorks: [
      ['Owner or export capability. Use for CA packs or your own archive.', 'ओनर या निर्यात अनुमति। CA पैक या संग्रह।'],
    ],
    businessImpact: [
      ['A file on disk is not a filing. You still Complete and file as usual.', 'डिस्क की फाइल फाइलिंग नहीं। Complete और पोर्टल अलग।'],
    ],
    keyRules: [
      ['Do not email exports with customer GSTIN to the public internet casually.', 'ग्राहक GSTIN वाली फाइलें लापरवाही से ईमेल न करें।'],
    ],
    commonMistakes: [
      ['Treating export as “the GST return was sent”.', 'निर्यात को GST रिटर्न भेजना समझना।'],
    ],
    relatedPages: [
      { path: '/reports/gstr1', labelKey: 'nav.gstr1' },
      { path: '/settings/import', labelKey: 'nav.importData' },
    ],
    nextActions: [
      ['Export after month Completes are done, then hand the file to your CA if that is your process.', 'महीने के Complete बाद निर्यात करें, प्रक्रिया हो तो CA को दें।'],
    ],
  }),

  helpPage('subscription-billing', {
    title: ['Workspace billing', 'वर्कस्पेस बिलिंग'],
    summary: [
      'Your Bizboard subscription. If writes are blocked, Complete/save stay disabled until billing is active — documents are not deleted.',
      'बिज़बोर्ड सब्सक्रिप्शन। लेखन ब्लॉक हो तो Complete/सेव बंद जब तक बिलिंग सक्रिय — दस्तावेज़ मिटते नहीं।',
    ],
    howItWorks: [
      ['Owner completes checkout. This is unrelated to customer GST invoices.', 'ओनर चेकआउट। यह ग्राहक GST बिल से अलग है।'],
    ],
    businessImpact: [
      ['A lapsed plan blocks new money documents until reactivated.', 'समाप्त प्लान नए पैसे के दस्तावेज़ रोकता है।'],
    ],
    keyRules: [
      ['Staff cannot change the plan.', 'स्टाफ प्लान नहीं बदलता।'],
    ],
    commonMistakes: [
      ['Thinking a blocked Complete is a GST error during a lapsed trial.', 'ट्रायल खत्म पर रुका Complete को GST एरर समझना।'],
    ],
    relatedPages: [
      { path: '/help', labelKey: 'nav.help' },
    ],
    nextActions: [
      ['Owner: renew or checkout, then retry the document. Do not recreate the bill twice.', 'ओनर: नवीनीकरण/चेकआउट, फिर दस्तावेज़ कोशिश। बिल दो बार न बनाएँ।'],
    ],
  }),

  helpPage('series-settings', {
    title: ['Document series', 'दस्तावेज़ सीरीज़'],
    summary: [
      'Prefixes, padding and next numbers. Drafts do not consume numbers. With any GSTIN, series are keyed by GSTIN and April–March year.',
      'प्रिफ़िक्स, पैडिंग, अगला नंबर। ड्राफ्ट नंबर नहीं खाते। GSTIN हो तो सीरीज़ GSTIN और अप्रैल–मार्च वर्ष से।',
    ],
    howItWorks: [
      ['Preview can differ from the number saved on Complete if GSTIN/year series applies.', 'GSTIN/वर्ष सीरीज़ हो तो प्रीव्यू Complete पर मिले नंबर से भिन्न हो सकता है।'],
    ],
    businessImpact: [
      ['Gaps in numbers are a CA/GST conversation. Do not reuse a number by editing this after Completes exist without advice.', 'नंबर गैप CA/GST विषय। Complete बाद बिना सलाह नंबर दोबारा न चलाएँ।'],
    ],
    keyRules: [
      ['Owner-only. Concurrency-safe increment happens on Complete.', 'केवल ओनर। Complete पर सुरक्षित अगला नंबर।'],
    ],
    commonMistakes: [
      ['Raising next-number to skip a bill that was only a draft — drafts never took that number.', 'ड्राफ्ट छोड़ने के लिए नेक्स्ट नंबर बढ़ाना — ड्राफ्ट ने नंबर लिया ही नहीं।'],
    ],
    relatedPages: [
      { path: '/sales/new', labelKey: 'nav.newInvoice' },
      { path: '/settings/gst', labelKey: 'nav.gst' },
    ],
    nextActions: [
      ['Set prefix before go-live. After go-live, change only with your CA.', 'गो-लाइव से पहले प्रिफ़िक्स। बाद में केवल CA के साथ बदलें।'],
    ],
  }),

  helpPage('units-settings', {
    title: ['Units', 'यूनिट'],
    summary: [
      'Unit of measure list used on products. Conversion rate on the product is how many base units sit in one alternate unit, and must be > 0.',
      'प्रोडक्ट की माप इकाइयाँ। प्रोडक्ट पर रूपांतरण = एक वैकल्पिक में कितनी बेस, और > 0 होना चाहिए।',
    ],
    howItWorks: [
      ['Stock stays in base unit. Billing in alternate multiplies qty × rate for stock.', 'स्टॉक बेस में। वैकल्पिक बिलिंग मात्रा × दर से स्टॉक।'],
    ],
    businessImpact: [
      ['Wrong conversion misstates on-hand and COGS on every later Complete.', 'गलत रूपांतरण हर Complete पर हाथ और लागत बिगाड़ता है।'],
    ],
    keyRules: [
      ['Base unit locks after the first stock movement on that item.', 'आइटम की पहली मूवमेंट बाद बेस यूनिट लॉक।'],
    ],
    commonMistakes: [
      ['Setting carton as base then wondering why on-hand is 7.34 cartons.', 'कार्टन को बेस बनाकर हाथ में 7.34 कार्टन देखना।'],
    ],
    relatedPages: [
      { path: '/inventory/products', labelKey: 'nav.products' },
    ],
    nextActions: [
      ['Pick the smallest count unit as base (PCS), carton as alternate with rate 50, then save the product.', 'बेस सबसे छोटी इकाई (PCS), कार्टन वैकल्पिक दर 50, प्रोडक्ट सेव करें।'],
    ],
  }),

  helpPage('item-settings', {
    title: ['Item settings', 'आइटम सेटिंग'],
    summary: [
      'Custom fields and item options. They do not change GST calculation unless a field is used only for display.',
      'कस्टम फ़ील्ड और आइटम विकल्प। केवल दिखाने वाले फ़ील्ड GST गणना नहीं बदलते।',
    ],
    howItWorks: [
      ['Define keys/labels. They appear on product forms and some lists when the feature is on.', 'कुंजी/लेबल। फीचर चालू हो तो प्रोडक्ट फॉर्म और कुछ सूचियों पर।'],
    ],
    businessImpact: [
      ['Bad keys break imports. They do not post tax.', 'गलत कुंजी इम्पोर्ट तोड़ती है। टैक्स पोस्ट नहीं।'],
    ],
    keyRules: [
      ['Do not store GSTIN or rates only in a custom field — use the real GST fields.', 'GSTIN/दर केवल कस्टम फ़ील्ड में न रखें — असली GST फ़ील्ड।'],
    ],
    commonMistakes: [
      ['Renaming a key after import mappings exist.', 'इम्पोर्ट मैपिंग बाद कुंजी का नाम बदलना।'],
    ],
    relatedPages: [
      { path: '/inventory/products', labelKey: 'nav.products' },
    ],
    nextActions: [
      ['Add only fields the shop will fill, then edit a product to verify.', 'दुकान भरेगी वही फ़ील्ड जोड़ें, प्रोडक्ट पर जाँचें।'],
    ],
  }),

  helpPage('invoice-templates', {
    title: ['Invoice terms & footer', 'इनवॉइस शर्तें और फुटर'],
    summary: [
      'Terms/footer for the fixed GST tax invoice layout. This page does not pick among multiple templates.',
      'तय GST टैक्स इनवॉइस लेआउट की शर्तें/फुटर। कई टेम्पलेट चुनना यहाँ नहीं है।',
    ],
    howItWorks: [
      ['Saved text prints on PDFs after you save. It does not change tax math.', 'सेव टेक्स्ट PDF पर छपता है। टैक्स गणित नहीं बदलता।'],
    ],
    businessImpact: [
      ['Customers see this as part of the legal invoice copy.', 'ग्राहक इसे कानूनी बिल कॉपी का हिस्सा देखते हैं।'],
    ],
    keyRules: [
      ['Do not put a second GSTIN only in the footer; use GST settings.', 'दूसरा GSTIN केवल फुटर में न लिखें — GST सेटिंग।'],
    ],
    commonMistakes: [
      ['Expecting this screen to switch to a retail vs tax layout. Invoice type on the bill does that.', 'रिटेल बनाम टैक्स लेआउट यहीं से — बिल का प्रकार करता है।'],
    ],
    relatedPages: [
      { path: '/sales/new', labelKey: 'nav.newInvoice' },
      { path: '/settings/gst', labelKey: 'nav.gst' },
    ],
    nextActions: [
      ['Save terms, Complete a draft, print PDF to verify.', 'शर्तें सेव करें, ड्राफ्ट Complete कर PDF देखें।'],
    ],
  }),

  helpPage('price-lists', {
    title: ['Price lists', 'प्राइस लिस्ट'],
    summary: [
      'Named rate cards attached to a customer. New invoice lines pick that selling price instead of the product default. Owner-managed.',
      'ग्राहक से जुड़ी दर सूची। नई बिल लाइनें प्रोडक्ट डिफ़ॉल्ट की जगह यह कीमत लेती हैं। ओनर।',
    ],
    howItWorks: [
      ['Create the list, assign to the customer, then make a new bill.', 'सूची बनाएँ, ग्राहक पर लगाएँ, नया बिल बनाएँ।'],
    ],
    businessImpact: [
      ['Does not rewrite old completed invoices.', 'पुराने पूर्ण बिल नहीं बदलती।'],
    ],
    keyRules: [
      ['GST still applies on the price that lands on the line.', 'लाइन पर आई कीमत पर ही GST।'],
    ],
    commonMistakes: [
      ['Expecting a price list to change a bill already Completed.', 'पूर्ण बिल पर प्राइस लिस्ट लगना।'],
    ],
    relatedPages: [
      { path: '/sales/customers', labelKey: 'nav.customers' },
      { path: '/sales/new', labelKey: 'nav.newInvoice' },
    ],
    nextActions: [
      ['Assign the list to the customer, then open New Invoice and check the line price.', 'सूची ग्राहक पर लगाएँ, नया बिल खोलकर लाइन कीमत देखें।'],
    ],
  }),

  helpPage('accounting-settings', {
    title: ['Accounting settings', 'लेखांकन सेटिंग'],
    summary: [
      'Turns books on and related posting options. When enabled, Complete posts to GL. Reports then need accounting enabled and view-financial-reports.',
      'किताबें और पोस्टिंग विकल्प। चालू हो तो Complete GL पर पोस्ट। रिपोर्ट को लेखांकन और अनुमति चाहिए।',
    ],
    howItWorks: [
      ['Owner/users-admin. Flipping books on does not rewrite history until backfill/jobs the product provides.', 'ओनर। किताबें चालू करना इतिहास तभी लिखता है जब उत्पाद का बैकफ़िल हो।'],
    ],
    businessImpact: [
      ['Every later Complete/allocate hits GL. Period close then protects those postings.', 'बाद का हर Complete/आवंटन GL में। पीरियड क्लोज़ उन्हें बचाता है।'],
    ],
    keyRules: [
      ['Do not enable books mid-season without your CA.', 'सीज़न बीच बिना CA किताबें न चालू करें।'],
    ],
    commonMistakes: [
      ['Expecting P&L to match GSTR-3B automatically after the toggle.', 'टॉगल बाद P&L का GSTR-3B से अपने आप मिलना।'],
    ],
    relatedPages: [
      { path: '/accounting/journals', labelKey: 'nav.journals' },
      { path: '/accounting/periods', labelKey: 'nav.accountingPeriods' },
    ],
    nextActions: [
      ['Enable only after chart of accounts is reviewed, then Complete a test bill and open trial balance.', 'खातों का चार्ट देखने बाद चालू करें, टेस्ट बिल Complete कर ट्रायल बैलेंस खोलें।'],
    ],
  }),

  helpPage('journals', {
    title: ['Journals', 'जर्नल'],
    summary: [
      'Manual GL entries when books are on. They must balance. They are not a shortcut to fix GST on a completed invoice — use a credit/debit note.',
      'किताबें चालू हों तो मैनुअल GL। बैलेंस होना चाहिए। पूर्ण बिल का GST ठीक करने का शॉर्टकट नहीं — क्रेडिट/डेबिट नोट।',
    ],
    howItWorks: [
      ['Post when allowed. Closed period blocks money journals.', 'अनुमति पर पोस्ट। बंद पीरियड पैसे के जर्नल रोकता है।'],
    ],
    businessImpact: [
      ['Posted journals move trial balance, P&L and balance sheet immediately.', 'पोस्टेड जर्नल ट्रायल बैलेंस/P&L/बैलेंस शीट तुरंत चलाते हैं।'],
    ],
    keyRules: [
      ['Need post-journals capability. Invoice Completes already create system journals — do not duplicate them.', 'जर्नल अनुमति। बिल Complete सिस्टम जर्नल बनाता है — दोहराएँ नहीं।'],
    ],
    commonMistakes: [
      ['Booking GST output in a journal because the invoice tax looked wrong. Amend via note instead.', 'बिल टैक्स गलत लगने पर जर्नल में GST — नोट से सुधारें।'],
    ],
    relatedPages: [
      { path: '/reports/trial-balance', labelKey: 'nav.trialBalance' },
      { path: '/sales/credit-notes', labelKey: 'nav.creditNotes' },
    ],
    nextActions: [
      ['If the source is a bill, open the bill first. Use a journal only for true GL-only adjustments your CA asked for.', 'स्रोत बिल हो तो पहले बिल खोलें। जर्नल केवल CA वाले GL समायोजन के लिए।'],
    ],
  }),

  helpPage('accounting-periods', {
    title: ['Accounting periods', 'लेखांकन पीरियड'],
    summary: [
      'Hard-closed GST or accounting periods block new money documents. Soft-close of a GST period warns on Complete but still hard-blocks later money amends.',
      'हार्ड-क्लोज GST/खाता पीरियड नए पैसे के दस्तावेज़ रोकते हैं। GST सॉफ्ट-क्लोज Complete पर चेतावनी, बाद के पैसे संशोधन फिर भी हार्ड-ब्लॉक।',
    ],
    howItWorks: [
      ['Owner reopens or posts into an open month. Completing into a closed month fails on purpose.', 'ओनर खोलें या खुले महीने में पोस्ट। बंद महीने में Complete जानबूझकर फेल।'],
    ],
    businessImpact: [
      ['Protects filed GST and signed books. Credit notes in an open month are the usual correction path.', 'फाइल GST और दस्तखत किताबें बचाता है। सुधार अक्सर खुले महीने के क्रेडिट नोट से।'],
    ],
    keyRules: [
      ['Opening Help or a report never bypasses this gate.', 'सहायता या रिपोर्ट यह द्वार नहीं छोड़ती।'],
    ],
    commonMistakes: [
      ['Forcing Complete with a backdated closed date instead of a note in the open month.', 'बंद तारीख पर Complete ज़बरदस्ती — खुले महीने में नोट करें।'],
    ],
    relatedPages: [
      { path: '/sales/credit-notes', labelKey: 'nav.creditNotes' },
      { path: '/settings/gst', labelKey: 'nav.gst' },
    ],
    nextActions: [
      ['If Complete names a closed period, ask the Owner to reopen or use an open-month note.', 'Complete बंद पीरियड कहे तो ओनर से खोलें या खुले महीने का नोट लें।'],
    ],
  }),

  helpPage('chart-of-accounts', {
    title: ['Chart of accounts', 'खातों का चार्ट'],
    summary: [
      'GL accounts when books are on. System accounts used by invoice Complete should not be casually deleted.',
      'किताबें चालू हों तो GL खाते। बिल Complete वाले सिस्टम खाते लापरवाही से न मिटाएँ।',
    ],
    howItWorks: [
      ['Add accounts your CA asked for. Posting still happens from documents and journals.', 'CA वाले खाते जोड़ें। पोस्टिंग दस्तावेज़ और जर्नल से ही।'],
    ],
    businessImpact: [
      ['Wrong mapping here misfiles every later Complete into P&L vs balance sheet.', 'गलत मैपिंग बाद के हर Complete को P&L बनाम बैलेंस शीट में गलत डालती है।'],
    ],
    keyRules: [
      ['Need accounting enabled.', 'लेखांकन चालू चाहिए।'],
    ],
    commonMistakes: [
      ['Creating a second “GST output” account and posting journals while invoices still hit the system account.', 'दूसरा GST आउटपुट खाता बनाकर जर्नल, जबकि बिल सिस्टम खाते पर जाएँ।'],
    ],
    relatedPages: [
      { path: '/accounting/journals', labelKey: 'nav.journals' },
      { path: '/reports/trial-balance', labelKey: 'nav.trialBalance' },
    ],
    nextActions: [
      ['Review with your CA before the first month close.', 'पहले महीने के क्लोज़ से पहले CA के साथ देखें।'],
    ],
  }),
];
