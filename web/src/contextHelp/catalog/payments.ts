import { helpPage } from '../buildPage';
import type { ContextHelpPage } from '../types';

export const PAYMENTS_HELP: ContextHelpPage[] = [
  helpPage('payment-links', {
    title: ['Payment links', 'पेमेंट लिंक'],
    summary: [
      'Create a link on a **completed** invoice, share it, and capture creates a receipt allocated to that bill. You cannot create a link on a draft.',
      '**पूर्ण** बिल पर लिंक बनाएँ, शेयर करें; कैप्चर उस बिल पर आवंटित रसीद बनाता है। ड्राफ्ट पर लिंक नहीं।',
    ],
    howItWorks: [
      [
        'Cancelling the invoice cancels an open link. Cancelling a paid link is blocked. Money captured after a cancel is parked as paid-pending-books and raised on Needs Attention — never silently dropped.',
        'बिल रद्द करने से खुला लिंक रद्द। पेड लिंक रद्द नहीं। रद्द बाद कैप्चर Needs Attention पर पार्क होता है — चुपचाप नहीं छूटता।',
      ],
    ],
    businessImpact: [
      ['Successful capture reduces outstanding the same way as a allocated receipt.', 'सफल कैप्चर आवंटित रसीद की तरह बकाया घटाता है।'],
    ],
    keyRules: [
      ['Gateway receipts are refunded in the gateway, not voided in Bizboard.', 'गेटवे रसीद बिज़बोर्ड में डिलीट नहीं — गेटवे में रिफंड।'],
    ],
    commonMistakes: [
      ['Creating a link then Completing a different draft, so the customer pays the wrong bill.', 'लिंक बनाकर दूसरा ड्राफ्ट Complete करना — ग्राहक गलत बिल चुकाए।'],
    ],
    relatedPages: [
      { path: '/sales/history', labelKey: 'nav.salesHistory' },
      { path: '/sales/receipts', labelKey: 'nav.receipts' },
      { path: '/attention', labelKey: 'nav.attention' },
    ],
    nextActions: [
      ['Complete the invoice first, create the link, share. Watch Needs Attention if capture and cancel race.', 'पहले बिल Complete, लिंक बनाएँ, शेयर करें। कैप्चर/रद्द टकराव पर Attention देखें।'],
    ],
  }),

  helpPage('bank-statements', {
    title: ['Bank statements', 'बैंक स्टेटमेंट'],
    summary: [
      'Upload statement rows, preview, then commit. This does not auto-mark invoices paid.',
      'स्टेटमेंट पंक्तियाँ अपलोड, प्रीव्यू, कमिट। यह इनवॉइस को अपने आप Paid नहीं करता।',
    ],
    howItWorks: [
      ['After commit, confirm matches in bank reconciliation. Ambiguous suggestions are never auto-applied.', 'कमिट बाद बैंक रिकॉन में मैच पुष्टि करें। अस्पष्ट सुझाव ऑटो नहीं लगते।'],
    ],
    businessImpact: [
      ['Committed lines become the bank side of recon. Books still need a matching receipt/payment.', 'कमिट पंक्तियाँ रिकॉन का बैंक पक्ष हैं। किताबों में रसीद/भुगतान अभी भी चाहिए।'],
    ],
    keyRules: [
      ['Preview is not posted. Commit is the write.', 'प्रीव्यू पोस्ट नहीं। कमिट लिखता है।'],
    ],
    commonMistakes: [
      ['Assuming upload allocated customer receipts.', 'अपलोड को ग्राहक रसीद आवंटन समझना।'],
    ],
    relatedPages: [
      { path: '/payments/reconciliation', labelKey: 'nav.bankReconciliation' },
      { path: '/sales/receipts', labelKey: 'nav.receipts' },
    ],
    nextActions: [
      ['Commit the file, then open reconciliation and confirm matches.', 'फाइल कमिट करें, रिकॉन खोलकर मैच पुष्टि करें।'],
    ],
  }),

  helpPage('bank-reconciliation', {
    title: ['Bank reconciliation', 'बैंक मिलान'],
    summary: [
      'Match statement lines to books. Ambiguous suggestions are never auto-applied. Accounting bank recon (when books are on) clears GL bank lines the same way.',
      'स्टेटमेंट पंक्तियों को किताबों से मिलाएँ। अस्पष्ट सुझाव ऑटो नहीं। खाते चालू हों तो GL बैंक पंक्तियाँ उसी तरह।',
    ],
    howItWorks: [
      ['Confirm a suggested match only when you have checked the party and amount.', 'पार्टी और राशि जाँचकर ही सुझाया मैच पुष्टि करें।'],
    ],
    businessImpact: [
      ['Recon status is for cash control. It does not file GST or change invoice tax.', 'रिकॉन कैश नियंत्रण है। GST फाइल या बिल टैक्स नहीं बदलता।'],
    ],
    keyRules: [
      ['No silent auto-match.', 'चुपचाप ऑटो-मैच नहीं।'],
    ],
    commonMistakes: [
      ['Matching a payment to the wrong invoice because the amount coincided.', 'राशि मिलने से गलत बिल से मैच।'],
    ],
    relatedPages: [
      { path: '/payments/statements', labelKey: 'nav.bankStatements' },
      { path: '/reports/cash-book', labelKey: 'nav.cashBook' },
    ],
    nextActions: [
      ['Confirm clear matches; leave ambiguous rows for a person.', 'साफ़ मैच पुष्टि करें; अस्पष्ट पंक्तियाँ व्यक्ति के लिए छोड़ें।'],
    ],
  }),

  helpPage('account-aggregator', {
    title: ['Account aggregator', 'अकाउंट एग्रीगेटर'],
    summary: [
      'Optional bank-data connection. If this screen is visible it is still not a substitute for recording receipts and allocations in Bizboard.',
      'वैकल्पिक बैंक-डेटा कनेक्शन। दिखे तो भी बिज़बोर्ड में रसीद और आवंटन की जगह नहीं।',
    ],
    howItWorks: [
      ['Follow on-screen consent. Fetched lines still need recon/books treatment.', 'स्क्रीन की सहमति। आई पंक्तियों पर फिर रिकॉन/किताब।'],
    ],
    businessImpact: [
      ['Does not Complete invoices or file GST.', 'इनवॉइस Complete या GST फाइल नहीं करता।'],
    ],
    keyRules: [
      ['Treat as a feed, not as posted money, until a receipt/payment exists.', 'रसीद/भुगतान बने बिना इसे पोस्टेड पैसा न मानें।'],
    ],
    commonMistakes: [
      ['Assuming aggregator credit cleared customer outstanding.', 'एग्रीगेटर क्रेडिट को ग्राहक बकाया चुकता समझना।'],
    ],
    relatedPages: [
      { path: '/payments/reconciliation', labelKey: 'nav.bankReconciliation' },
      { path: '/sales/receipts', labelKey: 'nav.receipts' },
    ],
    nextActions: [
      ['Use statements/recon after any feed, and keep recording receipts as usual.', 'फीड बाद स्टेटमेंट/रिकॉन देखें, रसीदें हमेशा दर्ज करें।'],
    ],
  }),

  helpPage('offline-outbox', {
    title: ['Offline outbox', 'ऑफ़लाइन आउटबॉक्स'],
    summary: [
      'POS/offline documents waiting to sync. Until they succeed, the server — and other users — may not see the bill.',
      'सिंक की प्रतीक्षा में POS/ऑफ़लाइन दस्तावेज़। सफल होने तक सर्वर और अन्य यूज़र बिल नहीं देख सकते।',
    ],
    howItWorks: [
      ['Retry failed items after the network is back. Do not Complete the same sale again on another device.', 'नेटवर्क आने पर फेल आइटम फिर कोशिश। दूसरे डिवाइस पर वही बिक्री दोबारा Complete न करें।'],
    ],
    businessImpact: [
      ['Double-complete after a stuck outbox can double stock and GST.', 'अटके आउटबॉक्स बाद दोबारा Complete से स्टॉक और GST दुगने।'],
    ],
    keyRules: [
      ['Read the error on the row; do not delete blindly if the server might already have the document.', 'पंक्ति का एरर पढ़ें; सर्वर पर दस्तावेज़ हो तो अनजान डिलीट न करें।'],
    ],
    commonMistakes: [
      ['Re-entering the bill as a new invoice because the outbox looked empty on another login.', 'दूसरे लॉगिन पर आउटबॉक्स खाली दिखे तो नया बिल दोबारा बनाना।'],
    ],
    relatedPages: [
      { path: '/pos', labelKey: 'nav.pos' },
      { path: '/sales/history', labelKey: 'nav.salesHistory' },
    ],
    nextActions: [
      ['Sync or retry, then confirm the bill in sales history once.', 'सिंक/रिट्राई करें, फिर बिक्री इतिहास में एक बार बिल देखें।'],
    ],
  }),
];
