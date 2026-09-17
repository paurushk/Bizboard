import { helpPage } from '../buildPage';
import type { ContextHelpPage } from '../types';

export const MORE_HELP: ContextHelpPage[] = [
  helpPage('setup', {
    title: ['Setup wizard', 'सेटअप विज़ार्ड'],
    summary: [
      'Owner-only first-run: tax → shop → payments → catalog → first bill. You can skip it; the dashboard checklist still shows. Completing the first bill here is a real Complete (stock, GST, receivable).',
      'केवल ओनर: टैक्स → दुकान → भुगतान → कैटलॉग → पहला बिल। छोड़ सकते हैं; डैशबोर्ड चेकलिस्ट रहती है। यहाँ पहला बिल Complete असली Complete है।',
    ],
    howItWorks: [
      ['Each step saves settings or drafts. Only the first-bill Complete posts money/stock.', 'हर चरण सेटिंग/ड्राफ्ट सेव करता है। केवल पहले बिल का Complete पैसा/स्टॉक पोस्ट करता है।'],
    ],
    businessImpact: [
      ['GSTIN and state chosen here drive later invoice tax. Sample products are real SKUs if you add them.', 'यहाँ GSTIN/राज्य बाद के बिल टैक्स चलाते हैं। सैंपल प्रोडक्ट असली SKU हैं।'],
    ],
    keyRules: [
      ['Skipping does not delete the company. You can finish from the dashboard.', 'छोड़ने से कंपनी नहीं मिटती। डैशबोर्ड से पूरा कर सकते हैं।'],
    ],
    commonMistakes: [
      ['Completing a sample bill into a closed period or without a godown, then thinking setup is broken.', 'बंद पीरियड या बिना गोदाम सैंपल बिल Complete कर सेटअप टूटा समझना।'],
    ],
    relatedPages: [
      { path: '/', labelKey: 'nav.dashboard' },
      { path: '/settings/gst', labelKey: 'nav.gst' },
      { path: '/sales/new', labelKey: 'nav.newInvoice' },
    ],
    nextActions: [
      ['Finish GSTIN and shop state, add a few products, then Complete one real bill.', 'GSTIN और राज्य पूरा करें, कुछ प्रोडक्ट जोड़ें, एक असली बिल Complete करें।'],
    ],
  }),

  helpPage('bank-accounts', {
    title: ['Bank accounts', 'बैंक खाते'],
    summary: [
      'Cash boxes and bank instruments used on receipts, payments and reconciliation. Saving an account does not move money.',
      'रसीद, भुगतान और रिकॉन के नकद बॉक्स और बैंक साधन। खाता सेव से पैसा नहीं चलता।',
    ],
    howItWorks: [
      ['Pick these accounts when recording a receipt or payment.', 'रसीद/भुगतान दर्ज करते समय ये खाते चुनें।'],
    ],
    businessImpact: [
      ['Wrong default cash/bank account misfiles the cash book.', 'गलत डिफ़ॉल्ट कैश बुक बिगाड़ता है।'],
    ],
    keyRules: [
      ['Owner-managed. Recon matches against these instruments.', 'ओनर। रिकॉन इन्हीं से मिलता है।'],
    ],
    commonMistakes: [
      ['Creating a new bank account every time instead of recording a payment.', 'हर बार नया बैंक खाता — भुगतान दर्ज करें।'],
    ],
    relatedPages: [
      { path: '/sales/receipts', labelKey: 'nav.receipts' },
      { path: '/payments/reconciliation', labelKey: 'nav.bankReconciliation' },
    ],
    nextActions: [
      ['Add the accounts you actually collect into, then use them on the next receipt.', 'जिन खातों में पैसा आता है वे जोड़ें, अगली रसीद पर इस्तेमाल करें।'],
    ],
  }),

  helpPage('payment-gateway', {
    title: ['Payment gateway', 'पेमेंट गेटवे'],
    summary: [
      'Razorpay is primary; Cashfree and PayU share the same adapter when enabled. This stores credentials and options — it does not charge a customer until you create a payment link on a completed invoice.',
      'Razorpay मुख्य; Cashfree/PayU चालू हों तो वही एडाप्टर। क्रेडेंशियल यहाँ। ग्राहक से चार्ज पेमेंट लिंक (पूर्ण बिल) पर होता है।',
    ],
    howItWorks: [
      ['Owner configures keys. Live charges follow the gateway, then a capture receipt in Bizboard.', 'ओनर कुंजी सेट करते हैं। लाइव चार्ज गेटवे पर, फिर बिज़बोर्ड में कैप्चर रसीद।'],
    ],
    businessImpact: [
      ['A misconfigured gateway fails link capture; Needs Attention holds paid-pending-books if invoice was cancelled.', 'गलत गेटवे लिंक कैप्चर फेल; बिल रद्द हो तो Attention पर paid-pending-books।'],
    ],
    keyRules: [
      ['Refund in the gateway, do not void gateway receipts here.', 'रिफंड गेटवे में; गेटवे रसीद यहाँ डिलीट नहीं।'],
    ],
    commonMistakes: [
      ['Turning live keys on without a completed invoice link test in sandbox first.', 'सैंडबॉक्स टेस्ट बिना लाइव कुंजी।'],
    ],
    relatedPages: [
      { path: '/payments/links', labelKey: 'nav.paymentLinks' },
      { path: '/settings/billing', labelKey: 'nav.billing' },
    ],
    nextActions: [
      ['Save keys, Complete a test invoice, create a link, pay in test mode.', 'कुंजी सेव, टेस्ट बिल Complete, लिंक, टेस्ट भुगतान।'],
    ],
  }),

  helpPage('statutory-licences', {
    title: ['Statutory licences', 'वैधानिक लाइसेंस'],
    summary: [
      'A register of licences (FSSAI, shops act, and similar). Reminder aid — not a filing engine and not GSTIN (GSTIN lives in GST settings).',
      'लाइसेंस रजिस्टर (FSSAI आदि)। याद दिलाना — फाइलिंग इंजन नहीं, GSTIN नहीं (GST सेटिंग में है)।',
    ],
    howItWorks: [
      ['Add numbers and dates. Expiry does not block invoice Complete unless some other gate does.', 'नंबर/तिथि जोड़ें। समाप्ति अकेले बिल Complete नहीं रोकती।'],
    ],
    businessImpact: [
      ['Helps the Owner remember renewals. Does not post accounting.', 'नवीनीकरण याद। लेखांकन पोस्ट नहीं।'],
    ],
    keyRules: [
      ['Do not store GSTIN only here.', 'GSTIN केवल यहीं न रखें।'],
    ],
    commonMistakes: [
      ['Expecting e-Way to read a licence from this list automatically.', 'e-Way का यहाँ से लाइसेंस अपने आप पढ़ना।'],
    ],
    relatedPages: [
      { path: '/settings/gst', labelKey: 'nav.gst' },
      { path: '/reports/statutory-events', labelKey: 'nav.statutoryEvents' },
    ],
    nextActions: [
      ['Record live licences and set a reminder in statutory events.', 'चालू लाइसेंस दर्ज करें, वैधानिक घटनाओं में याद रखें।'],
    ],
  }),

  helpPage('cost-centers', {
    title: ['Cost centers', 'कॉस्ट सेंटर'],
    summary: [
      'Optional P&L dimension when books are on. Tagging does not change GST on the invoice.',
      'किताबें चालू हों तो वैकल्पिक P&L आयाम। टैग से बिल का GST नहीं बदलता।',
    ],
    howItWorks: [
      ['Create centers, then use them on documents that offer the field.', 'सेंटर बनाएँ, जो दस्तावेज़ फ़ील्ड दें उन पर लगाएँ।'],
    ],
    businessImpact: [
      ['Slices P&L. Mis-tagging mis-attributes profit, not tax liability.', 'P&L बाँटता है। गलत टैग मुनाफा बिगाड़ता है, टैक्स देनदारी नहीं।'],
    ],
    keyRules: [
      ['Need accounting enabled.', 'लेखांकन चालू।'],
    ],
    commonMistakes: [
      ['Creating a cost center per GSTIN instead of extra GSTINs in GST settings.', 'GSTIN की जगह कॉस्ट सेंटर — अतिरिक्त GSTIN GST सेटिंग में।'],
    ],
    relatedPages: [
      { path: '/reports/profit-and-loss', labelKey: 'nav.profitAndLoss' },
      { path: '/accounting/journals', labelKey: 'nav.journals' },
    ],
    nextActions: [
      ['Add the few centers your CA asked for, then tag new Completes going forward.', 'CA जितने सेंटर कहें जोड़ें, आगे के Complete पर टैग करें।'],
    ],
  }),

  helpPage('fixed-assets', {
    title: ['Fixed assets', 'स्थायी संपत्ति'],
    summary: [
      'Asset register with SLM depreciation support when that module is on. Buying stock for resale still belongs on a purchase bill, not here.',
      'SLM मूल्यह्रास वाला एसेट रजिस्टर। पुनर्विक्रय स्टॉक खरीद बिल पर है, यहाँ नहीं।',
    ],
    howItWorks: [
      ['Register assets and post depreciation as the page allows. Closed period still applies.', 'एसेट दर्ज करें, पेज दे तो मूल्यह्रास। बंद पीरियड लागू।'],
    ],
    businessImpact: [
      ['Hits GL when books are on. Does not create GST output like a sale.', 'किताबें हों तो GL। बिक्री जैसा GST आउटपुट नहीं।'],
    ],
    keyRules: [
      ['Do not put trading stock here.', 'व्यापार स्टॉक यहाँ न डालें।'],
    ],
    commonMistakes: [
      ['Capitalising a resale item and then also Completing a purchase into stock — double count.', 'पुनर्विक्रय आइटम यहाँ और खरीद Complete — दोहरी गिनती।'],
    ],
    relatedPages: [
      { path: '/purchases/new', labelKey: 'nav.newPurchase' },
      { path: '/accounting/journals', labelKey: 'nav.journals' },
    ],
    nextActions: [
      ['Add only true capital assets with your CA’s codes.', 'केवल पूँजीगत एसेट, CA के कोड से।'],
    ],
  }),

  helpPage('tds-tcs', {
    title: ['TDS / TCS worksheets', 'TDS / TCS वर्कशीट'],
    summary: [
      'Worksheets when TDS/TCS is enabled — not a government filing engine.',
      'TDS/TCS चालू हो तो वर्कशीट — सरकारी फाइलिंग इंजन नहीं।',
    ],
    howItWorks: [
      ['Read deducted/collected amounts from posted documents. You still file on the portal.', 'पोस्टेड दस्तावेज़ों से राशि। फाइलिंग पोर्टल पर।'],
    ],
    businessImpact: [
      ['Wrong TDS on a payment is already in books after post; correct with the payment/note process, not by typing this report.', 'भुगतान पर गलत TDS पोस्ट बाद किताब में; इस रिपोर्ट से नहीं — भुगतान/नोट से ठीक करें।'],
    ],
    keyRules: [
      ['Needs TDS feature and view-financial-reports.', 'TDS फीचर और रिपोर्ट अनुमति।'],
    ],
    commonMistakes: [
      ['Treating this screen as TRACES filing.', 'इसे TRACES फाइलिंग समझना।'],
    ],
    relatedPages: [
      { path: '/purchases/payments', labelKey: 'nav.supplierPayments' },
      { path: '/reports/gstr1', labelKey: 'nav.gstr1' },
    ],
    nextActions: [
      ['Reconcile lines to payments, then file on the government site.', 'पंक्तियाँ भुगतानों से मिलाएँ, सरकारी साइट पर फाइल करें।'],
    ],
  }),

  helpPage('manufacturing', {
    title: ['Manufacturing', 'मैन्युफैक्चरिंग'],
    summary: [
      'BOM and work orders when the module is on. Completing a work order consumes components and can produce finished goods stock — it is not a GST invoice.',
      'मॉड्यूल चालू हो तो BOM और वर्क ऑर्डर। वर्क ऑर्डर Complete घटक काटता और तैयार माल बढ़ा सकता है — GST इनवॉइस नहीं।',
    ],
    howItWorks: [
      ['Define BOM, then complete work orders. Sell finished goods on a normal sales invoice.', 'BOM बनाएँ, वर्क ऑर्डर Complete करें। तैयार माल सामान्य बिक्री बिल से बेचें।'],
    ],
    businessImpact: [
      ['Stock of components down, FG up. GST output still happens on the later sales Complete.', 'घटक स्टॉक कम, तैयार माल ज्यादा। GST आउटपुट बाद की बिक्री Complete पर।'],
    ],
    keyRules: [
      ['Need manufacturing enabled and permission.', 'मैन्युफैक्चरिंग चालू और अनुमति।'],
    ],
    commonMistakes: [
      ['Issuing a GST invoice from the work order screen. Use New Invoice after FG is in stock.', 'वर्क ऑर्डर से GST बिल — स्टॉक आने पर नया इनवॉइस।'],
    ],
    relatedPages: [
      { path: '/inventory/stock', labelKey: 'nav.currentStock' },
      { path: '/sales/new', labelKey: 'nav.newInvoice' },
    ],
    nextActions: [
      ['Complete the work order, check current stock, then bill the customer.', 'वर्क ऑर्डर Complete करें, स्टॉक देखें, फिर ग्राहक को बिल करें।'],
    ],
  }),

  helpPage('payroll', {
    title: ['Payroll', 'पेरोल'],
    summary: [
      'Employees and pay runs when the module is on. A pay run is not a supplier bill and not a GST invoice.',
      'मॉड्यूल चालू हो तो कर्मचारी और पे रन। पे रन सप्लायर बिल या GST इनवॉइस नहीं।',
    ],
    howItWorks: [
      ['Maintain employees, then post a pay run as the page allows. Closed period can still block.', 'कर्मचारी रखें, पे रन पोस्ट करें। बंद पीरियड रोक सकता है।'],
    ],
    businessImpact: [
      ['Hits books when accounting is on. Does not create GSTR-1 rows.', 'खाते हों तो किताबें। GSTR-1 पंक्ति नहीं।'],
    ],
    keyRules: [
      ['Need payroll enabled and permission.', 'पेरोल चालू और अनुमति।'],
    ],
    commonMistakes: [
      ['Booking salary as a GST purchase to a dummy supplier.', 'सैलरी को डमी सप्लायर की GST खरीद बनाना।'],
    ],
    relatedPages: [
      { path: '/accounting/journals', labelKey: 'nav.journals' },
      { path: '/purchases/payments', labelKey: 'nav.supplierPayments' },
    ],
    nextActions: [
      ['Post the run, then pay via the payment path your CA uses.', 'रन पोस्ट करें, फिर CA वाले भुगतान पथ से दें।'],
    ],
  }),

  helpPage('crm', {
    title: ['CRM', 'CRM'],
    summary: [
      'Leads and opportunities when CRM is on. Converting to a customer/quotation does not Complete a tax invoice.',
      'CRM चालू हो तो लीड और अवसर। ग्राहक/कोटेशन बनाना टैक्स इनवॉइस Complete नहीं करता।',
    ],
    howItWorks: [
      ['Capture the lead, progress the opportunity, then create a quotation or invoice in Sales.', 'लीड पकड़ें, अवसर बढ़ाएँ, फिर सेल्स में कोटेशन या इनवॉइस।'],
    ],
    businessImpact: [
      ['No stock or GST until a sales document Completes.', 'सेल्स दस्तावेज़ Complete तक स्टॉक/GST नहीं।'],
    ],
    keyRules: [
      ['Need CRM enabled and permission.', 'CRM चालू और अनुमति।'],
    ],
    commonMistakes: [
      ['Treating a won opportunity as already billed.', 'जीता अवसर को बिल हो चुका समझना।'],
    ],
    relatedPages: [
      { path: '/sales/quotations', labelKey: 'nav.quotations' },
      { path: '/sales/customers', labelKey: 'nav.customers' },
    ],
    nextActions: [
      ['When the deal is real, create a quotation or invoice and Complete it.', 'डील पक्की हो तो कोटेशन/इनवॉइस बनाकर Complete करें।'],
    ],
  }),

  helpPage('ai-settings', {
    title: ['AI & Insights settings', 'AI और इनसाइट सेटिंग'],
    summary: [
      'Owner toggles for insights/assistant. The assistant does not Complete bills or file GST. For why Complete is blocked, use page Help or Help & FAQ.',
      'इनसाइट/असिस्टेंट टॉगल। असिस्टेंट बिल Complete या GST फाइल नहीं करता। Complete क्यों रुका — पेज सहायता या FAQ।',
    ],
    howItWorks: [
      ['Enable only if the company should see insights. Model answers are not books.', 'इनसाइट दिखाने हों तो चालू करें। मॉडल जवाब किताबें नहीं।'],
    ],
    businessImpact: [
      ['No money movement from this screen.', 'इस स्क्रीन से पैसा नहीं चलता।'],
    ],
    keyRules: [
      ['Users-admin / Owner.', 'ओनर/यूज़र-एडमिन।'],
    ],
    commonMistakes: [
      ['Asking the assistant to reverse a completed invoice. Use a credit note.', 'असिस्टेंट से पूर्ण बिल उल्टवाना — क्रेडिट नोट।'],
    ],
    relatedPages: [
      { path: '/insights', labelKey: 'nav.insights' },
      { path: '/help', labelKey: 'nav.help' },
    ],
    nextActions: [
      ['Leave insights on for Owners/Accountants who need alerts; keep Help for GST/stock blocks.', 'अलर्ट वाले ओनर/अकाउंटेंट के लिए इनसाइट; GST/स्टॉक ब्लॉक के लिए सहायता।'],
    ],
  }),
];
