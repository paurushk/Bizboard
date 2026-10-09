import { helpPage } from '../buildPage';
import type { ContextHelpPage } from '../types';

export const SALES_HELP: ContextHelpPage[] = [
  helpPage('dashboard', {
    title: ['Dashboard', 'डैशबोर्ड'],
    summary: [
      'A snapshot of today’s sales, this month’s sales and purchases, stock alerts, customer outstanding and supplier payables. It does not file GST or change any bill.',
      'आज की बिक्री, इस महीने की बिक्री/खरीद, स्टॉक अलर्ट, ग्राहक बकाया और सप्लायर देनदारी का सार। यह GST फाइल नहीं करता और कोई बिल नहीं बदलता।',
    ],
    howItWorks: [
      [
        'Totals come from completed documents. Drafts are not in sales or purchase KPIs.',
        'आँकड़े पूरे (Complete) दस्तावेज़ों से आते हैं। ड्राफ्ट बिक्री/खरीद KPI में नहीं गिने जाते।',
      ],
      [
        'Needs Attention is a separate ops queue (gateway holds, GST issues). Open it from the nav, not by editing a KPI.',
        'Needs Attention एक अलग कतार है (गेटवे होल्ड, GST मुद्दे)। KPI एडिट करके नहीं — नेव से खोलें।',
      ],
      [
        'Sales staff without view-financial-reports land on their first operational page instead of this dashboard.',
        'वित्तीय रिपोर्ट की अनुमति न हो तो स्टाफ डैशबोर्ड की जगह अपनी पहली कार्य-पेज पर पहुँचते हैं।',
      ],
    ],
    businessImpact: [
      [
        'Figures here are a read of sales → stock → party balances → reports. Completing or cancelling a bill elsewhere is what moves these numbers.',
        'यहाँ के आँकड़े बिक्री → स्टॉक → पार्टी बैलेंस → रिपोर्ट का पढ़ना हैं। बिल Complete/Cancel करने से ये संख्याएँ चलती हैं।',
      ],
    ],
    keyRules: [
      [
        'This page is view-only. Buttons such as **t:nav.newInvoice** only navigate; they do not post money.',
        'यह पेज केवल देखने के लिए है। **t:nav.newInvoice** जैसे बटन सिर्फ ले जाते हैं — पैसा पोस्ट नहीं करते।',
      ],
    ],
    commonMistakes: [
      [
        'Treating dashboard cash or outstanding as a bank or GST filing figure. Use **t:nav.cashBook** and GSTR worksheets for those jobs.',
        'डैशबोर्ड के कैश/बकाया को बैंक या GST फाइलिंग मत समझें। उसके लिए **t:nav.cashBook** और GSTR वर्कशीट देखें।',
      ],
    ],
    relatedPages: [
      { path: '/attention', labelKey: 'nav.attention' },
      { path: '/sales/new', labelKey: 'nav.newInvoice' },
      { path: '/sales/history', labelKey: 'nav.salesHistory' },
      { path: '/help', labelKey: 'nav.help' },
    ],
    nextActions: [
      ['If a KPI looks wrong, open the related list (sales history, receipts, stock) and check Complete and allocations.', 'KPI गलत लगे तो संबंधित सूची खोलें और Complete व आवंटन जाँचें।'],
      ['Use Needs Attention for items that need a human decision.', 'जिन बातों पर फैसला चाहिए वे Needs Attention में देखें।'],
    ],
  }),

  helpPage('attention', {
    title: ['Needs attention', 'ध्यान दें'],
    summary: [
      'An operations queue for items that need a person: gateway payments parked after a cancel, GST issues, and similar holds. It does not auto-fix or auto-file anything.',
      'ऐसी चीज़ों की कतार जिन्हें व्यक्ति को देखना है: रद्द बिल के बाद गेटवे भुगतान, GST मुद्दे। यह अपने आप ठीक या फाइल नहीं करता।',
    ],
    howItWorks: [
      ['Open a row to go to the related document. Clearing the cause (allocate, cancel IRN, review ITC) removes it from this list.', 'पंक्ति खोलकर संबंधित दस्तावेज़ पर जाएँ। कारण हटने पर पंक्ति सूची से हटती है।'],
    ],
    businessImpact: [
      [
        'Ignoring a gateway “paid, pending books” row leaves customer money unmatched to invoices and reports.',
        'गेटवे की “paid, pending books” पंक्ति छोड़ने से ग्राहक का पैसा बिल से नहीं जुड़ता।',
      ],
    ],
    keyRules: [
      ['This list is a reader of other flows. It never completes or cancels a bill by itself.', 'यह सूची अन्य फ्लो पढ़ती है। यह खुद बिल Complete/Cancel नहीं करती।'],
    ],
    commonMistakes: [
      ['Voiding a gateway receipt to clear a row. Gateway money is refunded in the gateway, not deleted here.', 'पंक्ति साफ़ करने के लिए गेटवे रसीद डिलीट न करें। रिफंड गेटवे में होता है।'],
    ],
    relatedPages: [
      { path: '/payments/links', labelKey: 'nav.paymentLinks' },
      { path: '/sales/receipts', labelKey: 'nav.receipts' },
      { path: '/', labelKey: 'nav.dashboard' },
    ],
    nextActions: [
      ['Work the oldest open row first. Open the document and follow the on-screen error or hold reason.', 'सबसे पुरानी पंक्ति पहले देखें। दस्तावेज़ खोलकर स्क्रीन पर लिखा कारण पढ़ें।'],
    ],
  }),

  helpPage('sales-invoice', {
    title: ['Sales invoice', 'बिक्री इनवॉइस'],
    summary: [
      'Create Sales Invoice. **t:common.draft** keeps a draft. **t:billing.saveAndComplete** assigns the number, moves stock from this **t:inventory.godown**, and posts what the customer owes. A draft does neither.',
      'बिक्री बिल बनाएँ। **t:common.draft** ड्राफ्ट रखता है। **t:billing.saveAndComplete** नंबर देता है, इस **t:inventory.godown** से स्टॉक काटता है, और ग्राहक पर बकाया लगाता है। ड्राफ्ट दोनों नहीं करता।',
    ],
    howItWorks: [
      [
        'Pick a customer or walk-in, place of supply, invoice type, godown, and lines. Same-state sales show **t:billing.cgst**+**t:billing.sgst**; other-state sales show **t:billing.igst**. Place of supply comes from the customer state or GSTIN versus the company.',
        'ग्राहक या वॉक-इन, place of supply, बिल प्रकार, गोदाम और लाइनें चुनें। एक राज्य में **t:billing.cgst**+**t:billing.sgst**, दूसरे राज्य में **t:billing.igst**। Place of supply ग्राहक राज्य/GSTIN बनाम कंपनी से आता है।',
      ],
      [
        'Preview Mode shows the party, the total, the amount in words, and the same tax-invoice PDF you will print. It does not complete the bill. Typing a line amount recalculates the unit price. A line discount you typed stays.',
        'Preview Mode पार्टी, कुल, शब्दों में राशि, और वही टैक्स-इनवॉइस PDF दिखाता है जो छपेगा। इससे बिल Complete नहीं होता। लाइन राशि बदलने पर इकाई मूल्य फिर बनता है। टाइप की छूट रहती है।',
      ],
      [
        'Cash may be more than the bill; the extra is change and the receipt is the bill amount. Card, UPI, bank, and cheque cannot be more than the amount due. Credit posts no receipt. Alt+M fills Amount Received as fully paid.',
        'नकद बिल से ज्यादा हो सकता है; अतिरिक्त बदलाव है और रसीद बिल की राशि की होती है। कार्ड, UPI, बैंक और चेक बकाया से ज्यादा नहीं हो सकते। उधार पर रसीद नहीं बनती। Alt+M पूरी रकम भर देता है।',
      ],
      [
        'Ctrl/Cmd+S saves a draft. Ctrl/Cmd+Enter completes, but not while the cursor is in a field. Ctrl/Cmd+Shift+L and F2 focus item search. **t:nav.uploadSalesBill** on this page starts a photo or PDF draft. Quick settings cover purchase price on the line, party fields, and trading fields such as PO and vehicle.',
        'Ctrl/Cmd+S ड्राफ्ट सेव करता है। Ctrl/Cmd+Enter Complete करता है, पर कर्सर फ़ील्ड में हो तो नहीं। Ctrl/Cmd+Shift+L और F2 आइटम खोज पर जाते हैं। इस पेज का **t:nav.uploadSalesBill** फोटो/PDF ड्राफ्ट शुरू करता है। क्विक सेटिंग में खरीद मूल्य, पार्टी फ़ील्ड, और PO/वाहन जैसे ट्रेडिंग फ़ील्ड हैं।',
      ],
    ],
    businessImpact: [
      [
        'Save & Complete posts stock in this godown, customer outstanding, GST worksheets, and reports. Est. Margin uses the item purchase price or average cost and is a guide. Profit Details after completion is sales amount minus cost minus GST collected — those three stay separate.',
        'Save & Complete इस गोदाम का स्टॉक, ग्राहक बकाया, GST वर्कशीट और रिपोर्ट पोस्ट करता है। Est. Margin आइटम खरीद मूल्य या औसत लागत है, अनुमान है। पूरा होने के बाद Profit Details = बिक्री − लागत − वसूला GST; ये तीन अलग रहते हैं।',
      ],
      [
        'A receipt must be allocated before outstanding falls. With the books off, an unallocated receipt lowers credit exposure. With the books on, only the ledger advance does. After completion, reverse quantity or tax with a return or credit note.',
        'बकाया घटाने के लिए रसीद आवंटित होनी चाहिए। खाते बंद हों तो बिना आवंटन रसीद क्रेडिट एक्सपोज़र घटाती है। खाते चालू हों तो सिर्फ लेजर का अग्रिम घटता है। पूरा होने के बाद मात्रा/टैक्स रिटर्न या क्रेडिट नोट से बदलें।',
      ],
    ],
    keyRules: [
      [
        '**t:billing.saveAndComplete** needs at least one line with quantity greater than 0, place of supply on a GST bill, an active product, and an unblocked customer. Goods that track inventory need stock in this godown. Services, and goods with inventory tracking off, are not stopped for zero stock.',
        '**t:billing.saveAndComplete** के लिए मात्रा > 0 वाली कम से कम एक लाइन, GST बिल पर place of supply, सक्रिय आइटम और अनब्लॉक ग्राहक चाहिए। इन्वेंटरी ट्रैक करने वाले माल को इस गोदाम में स्टॉक चाहिए। सर्विस, और ट्रैकिंग बंद माल, शून्य स्टॉक पर नहीं रुकते।',
      ],
      [
        'A credit limit above zero blocks Complete when open exposure plus this bill exceeds it. Exposure is what is still owed after advances. With accounting books on, the check uses the higher of the ledger and that document figure. A zero or blank limit means no check.',
        'लिमिट > 0 हो और खुला एक्सपोज़र + यह बिल लिमिट से ऊपर हो तो Complete रुकता है। एक्सपोज़र अग्रिम के बाद बची रकम है। खाते चालू हों तो जाँच लेजर और दस्तावेज़ में से बड़ी रकम लेती है। 0 या खाली लिमिट = जाँच नहीं।',
      ],
      [
        'Collection hold, a closed period, a missing company GSTIN on Regular GST sales, unconfirmed sales reverse charge, serials that do not match quantity, or an after-tax discount on a B2B GST bill can also block Complete. Composition and Unregistered companies should use RETAIL or NON_GST, not GST or TAX.',
        'कलेक्शन होल्ड, बंद पीरियड, Regular GST बिक्री पर कंपनी GSTIN न होना, बिना पुष्टि sales RCM, सीरियल संख्या ≠ मात्रा, या B2B GST पर after-tax छूट भी रोक सकती है। Composition और Unregistered कंपनी GST/TAX न लें — RETAIL या NON_GST लें।',
      ],
      [
        'The legal number is assigned on Save & Complete, not on Save draft. After that you cannot rewrite lines. Use a credit note or debit note, or **t:common.cancel** when the bill should never have existed and nothing is allocated. A live IRN also blocks line edit.',
        'कानूनी नंबर Save & Complete पर मिलता है, Save draft पर नहीं। उसके बाद लाइनें नहीं बदलतीं। क्रेडिट/डेबिट नोट लें, या बिल बनना ही नहीं चाहिए था और आवंटन न हो तो **t:common.cancel**। लाइव IRN लाइन एडिट रोकता है।',
      ],
    ],
    commonMistakes: [
      [
        'Completing while Products shows stock, but this bill’s godown is empty. Company-wide available is not this godown.',
        'प्रोडक्ट में स्टॉक दिखे और इस बिल का गोदाम खाली हो — कुल उपलब्ध ≠ इस गोदाम का स्टॉक।',
      ],
      [
        'Reading Est. Margin as final profit, or expecting the public link to show cost. Profit Details is on the signed-in bill only.',
        'Est. Margin को अंतिम लाभ समझना, या पब्लिक लिंक पर लागत की उम्मीद। Profit Details केवल साइन-इन बिल पर है।',
      ],
      [
        'Entering card, UPI, bank, or cheque above the amount due. Only cash can be more, and that extra is change.',
        'कार्ड, UPI, बैंक या चेक बकाया से ज्यादा लिखना। सिर्फ नकद ज्यादा हो सकता है, और वह बदलाव है।',
      ],
    ],
    relatedPages: [
      { path: '/sales/history', labelKey: 'nav.salesHistory' },
      { path: '/sales/receipts', labelKey: 'nav.receipts' },
      { path: '/sales/credit-notes', labelKey: 'nav.creditNotes' },
      { path: '/sales/bill-upload', labelKey: 'nav.uploadSalesBill' },
      { path: '/inventory/stock', labelKey: 'nav.currentStock' },
      { path: '/settings/gst', labelKey: 'nav.gst' },
    ],
    nextActions: [
      ['Read any red message before Save & Complete. **t:help.why** names the rule when Help v2 is on.', 'Save & Complete से पहले लाल संदेश पढ़ें। Help v2 हो तो **t:help.why** नियम बताता है।'],
      ['After it completes you open that invoice: print, share, or record the rest of the payment. Do not complete it again.', 'पूरा होने पर वही बिल खुलता है: प्रिंट, शेयर, या बची रकम दर्ज करें। दोबारा Complete न करें।'],
    ],
  }),

  helpPage('sales-invoice-detail', {
    title: ['Sales invoice detail', 'बिक्री इनवॉइस विवरण'],
    summary: [
      'One bill: status, tax, outstanding, and the actions on a completed invoice — Download PDF, Print, Share, Generate e-Invoice, Generate E-Way Bill, Record Payment, and Profit Details. Opening this page does not change the bill.',
      'एक बिल: स्थिति, टैक्स, बकाया, और पूर्ण बिल की क्रियाएँ — PDF, प्रिंट, शेयर, e-Invoice, E-Way, भुगतान, Profit Details। पेज खोलने से बिल नहीं बदलता।',
    ],
    howItWorks: [
      [
        'Share → WhatsApp opens WhatsApp on this device so you pick the chat. Copy link makes a public page with the customer name, GSTIN, address, and amounts, plus download. It does not show purchase price, margin, or profit. Revoke link stops that page.',
        'शेयर → WhatsApp इस डिवाइस पर खुलता है, चैट आप चुनते हैं। Copy link पब्लिक पेज बनाता है: नाम, GSTIN, पता, राशि, और डाउनलोड। खरीद मूल्य, मार्जिन या लाभ नहीं दिखता। Revoke link वह पेज बंद करता है।',
      ],
      [
        'Generate e-Invoice on a completed B2B GST or TAX bill prepares JSON. **t:einvoice.payloadOnlyHelp** When live submit is on, only the Owner can send it, and a sandbox acknowledgement is not an IRN on the NIC portal.',
        'पूर्ण B2B GST/TAX बिल पर Generate e-Invoice JSON तैयार करता है। **t:einvoice.payloadOnlyHelp** लाइव सबमिट चालू हो तो सिर्फ Owner भेज सकता है, और सैंडबॉक्स पावती NIC पोर्टल का IRN नहीं है।',
      ],
      [
        'Generate E-Way Bill appears when the completed bill is over the company threshold, is not Non-GST, and is not service-only. Distance in kilometres is required. Record Payment applies up to the open balance; a larger amount is refused.',
        'Generate E-Way Bill तब दिखता है जब पूर्ण बिल कंपनी की सीमा से ऊपर हो, Non-GST न हो, और सिर्फ सर्विस न हो। दूरी किलोमीटर में ज़रूरी है। Record Payment खुले बैलेंस तक लगता है; उससे ज्यादा रकम रुक जाती है।',
      ],
    ],
    businessImpact: [
      [
        'Stock, GST, and reports already moved on Save & Complete. This screen collects money, shares the bill, and shows Profit Details: sales amount minus total cost minus GST collected. Item purchase price, estimated cost, and GST collected stay named separately.',
        'स्टॉक, GST और रिपोर्ट Save & Complete पर चल चुके। यह स्क्रीन पैसा लेती है, बिल शेयर करती है, और Profit Details दिखाती है: बिक्री − कुल लागत − वसूला GST। आइटम खरीद मूल्य, अनुमानित लागत और वसूला GST अलग नाम से रहते हैं।',
      ],
      [
        'A partial return leaves the invoice COMPLETED — the customer kept some lines. A full return must not be read as a live sale.',
        'आंशिक रिटर्न पर बिल COMPLETED रहता है — ग्राहक ने कुछ लाइनें रखीं। पूरी वापसी को चालू बिक्री न पढ़ें।',
      ],
    ],
    keyRules: [
      [
        '**t:common.cancel** needs cancel permission, no allocated receipts, and no completed sales return or credit/debit note. Cancel also cancels an open payment link. The public page stays up and can show Cancelled until you Revoke link. A full return removes the public link.',
        '**t:common.cancel** के लिए रद्द अनुमति, बिना आवंटित रसीद, और बिना पूर्ण रिटर्न या क्रेडिट/डेबिट नोट चाहिए। रद्द करने से खुला पेमेंट लिंक रद्द होता है। पब्लिक पेज तब तक रहता है और Cancelled दिखा सकता है जब तक Revoke link न करें। पूरी वापसी पब्लिक लिंक हटा देती है।',
      ],
      [
        'Drafts cannot be downloaded, shared, or paid from this bar. e-Invoice and live e-Way submit are Owner-only when those live switches are on.',
        'ड्राफ्ट इस बार से डाउनलोड, शेयर या भुगतान नहीं हो सकते। लाइव स्विच चालू हों तो e-Invoice और लाइव e-Way सिर्फ Owner भेज सकता है।',
      ],
    ],
    commonMistakes: [
      [
        'Treating a copied link as private. Anyone with the link can see the party and the amounts. Revoke it when you no longer want that.',
        'कॉपी किए लिंक को निजी समझना। लिंक वाला व्यक्ति पार्टी और राशि देख सकता है। ज़रूरत खत्म हो तो Revoke करें।',
      ],
      [
        'Reading Paid on a fully returned invoice as money still collected for goods the customer kept.',
        'पूरी वापसी वाले बिल पर Paid को रखे माल का भुगतान न समझें।',
      ],
    ],
    relatedPages: [
      { path: '/sales/history', labelKey: 'nav.salesHistory' },
      { path: '/sales/receipts', labelKey: 'nav.receipts' },
      { path: '/sales/returns', labelKey: 'nav.salesReturns' },
      { path: '/sales/credit-notes', labelKey: 'nav.creditNotes' },
      { path: '/settings/gst', labelKey: 'nav.gst' },
    ],
    nextActions: [
      ['If money is still due, Record Payment. If goods came back, use a sales return. Share only after you have checked the PDF.', 'रकम बाकी हो तो Record Payment। माल वापस हो तो बिक्री रिटर्न। PDF जाँचकर ही शेयर करें।'],
    ],
  }),

  helpPage('sales-history', {
    title: ['Sales history', 'बिक्री इतिहास'],
    summary: [
      'Every sales invoice for this company. Open a draft to keep editing. Open a completed row for the PDF, share link, e-Invoice, e-Way, payment, and Profit Details. The list does not skip the invoice rules.',
      'कंपनी के सभी बिक्री बिल। ड्राफ्ट खोलकर जारी रखें। पूर्ण पंक्ति पर PDF, शेयर लिंक, e-Invoice, e-Way, भुगतान और Profit Details। सूची इनवॉइस के नियम नहीं छोड़ती।',
    ],
    howItWorks: [
      ['Filter by status, payment, date, and party. Drafts have no legal number until Save & Complete. Payment and return badges are calculated from allocations and returns.', 'स्थिति, भुगतान, तारीख और पार्टी से फ़िल्टर करें। ड्राफ्ट का कानूनी नंबर Save & Complete तक नहीं। भुगतान और रिटर्न बैज आवंटन और रिटर्न से बनते हैं।'],
    ],
    businessImpact: [
      [
        'This list is a reader of invoice status, payment state and return state. Changing a bill on its detail page is what updates the row.',
        'यह सूची बिल की स्थिति/भुगतान/रिटर्न पढ़ती है। डिटेल पेज पर बदलाव से पंक्ति अपडेट होती है।',
      ],
    ],
    keyRules: [
      ['List actions never skip Complete gates (stock, GST, period lock, credit limit).', 'सूची की क्रियाएँ Complete के द्वार (स्टॉक, GST, पीरियड, लिमिट) नहीं छोड़तीं।'],
    ],
    commonMistakes: [
      ['Deleting a completed invoice from the list. Use cancel or a credit note instead.', 'पूर्ण बिल सूची से डिलीट न करें। रद्द या क्रेडिट नोट लें।'],
    ],
    relatedPages: [
      { path: '/sales/new', labelKey: 'nav.newInvoice' },
      { path: '/sales/receipts', labelKey: 'nav.receipts' },
      { path: '/reports/sales', labelKey: 'nav.salesReports' },
    ],
    nextActions: [
      ['Open drafts that should be billed today and press Save & Complete after checking godown and GST.', 'आज के ड्राफ्ट खोलें, गोदाम और GST जाँचकर Save & Complete दबाएँ।'],
    ],
  }),

  helpPage('quotations', {
    title: ['Quotations', 'कोटेशन'],
    summary: [
      'Price offers. Convert remaining quantity to a **draft** invoice or sales order. Conversion does not Complete the invoice and does not take stock.',
      'कीमत का प्रस्ताव। बची मात्रा को **ड्राफ्ट** इनवॉइस या सेल्स ऑर्डर में बदलें। कन्वर्ट से बिल Complete नहीं होता और स्टॉक नहीं कटता।',
    ],
    howItWorks: [
      [
        'Convert only from an allowed quotation status. You can convert part of a line; leftover quantity stays convertible.',
        'अनुमत स्थिति से ही कन्वर्ट करें। लाइन की कुछ मात्रा कन्वर्ट हो सकती है; बाकी बाद में।',
      ],
      [
        'Expired validity needs an explicit confirm. A blocked customer cannot convert.',
        'समाप्त वैधता पर अलग पुष्टि चाहिए। ब्लॉक ग्राहक कन्वर्ट नहीं कर सकता।',
      ],
    ],
    businessImpact: [
      [
        'Stock, GST and customer balance move only when the resulting invoice (or reserved order) is later Completed — not at convert.',
        'स्टॉक, GST और ग्राहक बैलेंस कन्वर्ट पर नहीं, बाद में इनवॉइस/ऑर्डर Complete होने पर चलते हैं।',
      ],
    ],
    keyRules: [
      ['Quotations do not post tax or receivables. Do not treat a converted draft as a tax invoice until Complete.', 'कोटेशन टैक्स या बकाया पोस्ट नहीं करता। कन्वर्टेड ड्राफ्ट Complete तक टैक्स इनवॉइस नहीं है।'],
    ],
    commonMistakes: [
      ['Assuming convert reserved stock. Sales orders reserve on confirm; quotations do not.', 'कन्वर्ट को स्टॉक रिज़र्व न समझें। रिज़र्व सेल्स ऑर्डर कन्फर्म पर होता है।'],
    ],
    relatedPages: [
      { path: '/sales/new', labelKey: 'nav.newInvoice' },
      { path: '/sales/orders', labelKey: 'nav.salesOrders' },
      { path: '/sales/customers', labelKey: 'nav.customers' },
    ],
    nextActions: [
      ['After convert, open the draft invoice or order, check godown and GST, then Complete when ready.', 'कन्वर्ट के बाद ड्राफ्ट खोलें, गोदाम/GST जाँचें, तैयार हों तो Complete करें।'],
    ],
  }),

  helpPage('sales-orders', {
    title: ['Sales orders', 'बिक्री ऑर्डर'],
    summary: [
      'Confirmed orders reserve stock. Available = on hand − reserved. Completing an invoice or delivery challan from the order consumes or releases that reserve.',
      'कन्फर्म ऑर्डर स्टॉक रिज़र्व करता है। उपलब्ध = हाथ में − रिज़र्व। इनवॉइस या चालान Complete करने पर रिज़र्व खपता या छूटता है।',
    ],
    howItWorks: [
      [
        'Converting a sales order or challan currently copies all lines — not a partial dispatch. Split or reduce the order first if you need a part shipment.',
        'ऑर्डर/चालान कन्वर्ट अभी सारी लाइनें कॉपी करता है। आंशिक डिस्पैच के लिए पहले ऑर्डर बाँटें या घटाएँ।',
      ],
      [
        'Converting to a draft invoice does not release reserved stock early. Reservation stays until the invoice or challan Completes, or the order is cancelled.',
        'ड्राफ्ट इनवॉइस बनाने से रिज़र्व जल्दी नहीं छूटता। रिज़र्व इनवॉइस/चालान Complete या ऑर्डर रद्द तक रहता है।',
      ],
    ],
    businessImpact: [
      [
        'Reserved quantity reduces what you can sell on other bills. Low-stock and billing both use available, not raw on-hand.',
        'रिज़र्व अन्य बिलों पर बिक्री कम करता है। लो-स्टॉक और बिलिंग उपलब्ध मात्रा देखती हैं, सिर्फ हाथ में नहीं।',
      ],
    ],
    keyRules: [
      ['Batch items reserve FEFO lots (nearest expiry first).', 'बैच आइटम FEFO लॉट रिज़र्व करते हैं (पहले नज़दीक expiry)।'],
    ],
    commonMistakes: [
      ['Creating a second order for the same stock while the first is still reserved, then wondering why Complete fails.', 'पहले ऑर्डर के रिज़र्व रहते दूसरा ऑर्डर बनाकर Complete फेल होना।'],
    ],
    relatedPages: [
      { path: '/sales/delivery-challans', labelKey: 'nav.deliveryChallans' },
      { path: '/sales/new', labelKey: 'nav.newInvoice' },
      { path: '/inventory/stock', labelKey: 'nav.currentStock' },
    ],
    nextActions: [
      ['Confirm the order to reserve, then convert to challan or invoice when you ship or bill.', 'रिज़र्व के लिए ऑर्डर कन्फर्म करें, फिर शिप/बिल पर चालान या इनवॉइस बनाएँ।'],
    ],
  }),

  helpPage('delivery-challans', {
    title: ['Delivery challans', 'डिलीवरी चालान'],
    summary: [
      'Dispatch notes. By default stock still moves when the **invoice** Completes. If the Owner turns on stock-on-challan, completing the challan posts the sale movement instead.',
      'डिस्पैच नोट। डिफ़ॉल्ट में स्टॉक **इनवॉइस** Complete पर कटता है। ओनर ने चालान पर स्टॉक चालू किया हो तो चालान Complete पर बिक्री मूवमेंट लगता है।',
    ],
    howItWorks: [
      ['One challan per sales order. You can convert a challan to an invoice once.', 'एक सेल्स ऑर्डर पर एक चालान। चालान से इनवॉइस एक बार कन्वर्ट होता है।'],
      ['Challan e-Way needs transport distance (km) on the challan e-Way panel.', 'चालान e-Way के लिए चालान पैनल पर दूरी (किमी) चाहिए।'],
    ],
    businessImpact: [
      [
        'If stock-on-challan is on, Complete here hits stock immediately; the later invoice must not double-issue that stock.',
        'स्टॉक-ऑन-चालान हो तो यहाँ Complete से स्टॉक तुरंत कटता है; बाद का इनवॉइस वही स्टॉक दोबारा न काटे।',
      ],
    ],
    keyRules: [
      ['Cancel rules tighten if stock already posted from the challan.', 'चालान से स्टॉक लग चुका हो तो रद्द नियम सख्त होते हैं।'],
    ],
    commonMistakes: [
      ['Expecting a challan to create GST output. Tax still comes from the invoice (unless your process bills the challan as the tax document — it does not).', 'चालान को GST आउटपुट न समझें। टैक्स इनवॉइस से आता है।'],
    ],
    relatedPages: [
      { path: '/sales/orders', labelKey: 'nav.salesOrders' },
      { path: '/sales/new', labelKey: 'nav.newInvoice' },
      { path: '/inventory/stock', labelKey: 'nav.currentStock' },
    ],
    nextActions: [
      ['After dispatch, convert to invoice if the customer needs a tax bill, then Complete the invoice.', 'डिस्पैच के बाद टैक्स बिल चाहिए तो इनवॉइस में बदलें और Complete करें।'],
    ],
  }),

  helpPage('receipts', {
    title: ['Customer payments', 'ग्राहक भुगतान'],
    summary: [
      'Record money in (cash, UPI, bank, card, cheque) and **allocate** it to completed or returned invoices. An unallocated receipt does not clear a bill. With the books off it lowers credit exposure; with the books on, only the ledger advance does. On the invoice itself, only cash may be more than the amount due.',
      'आने वाला पैसा (नकद, UPI, बैंक, कार्ड, चेक) पूर्ण या लौटे बिलों पर **आवंटित** करें। बिना आवंटन रसीद बिल नहीं घटाती। खाते बंद हों तो क्रेडिट एक्सपोज़र घटता है; खाते चालू हों तो सिर्फ लेजर का अग्रिम। बिल पर सिर्फ नकद बकाया से ज्यादा हो सकता है।',
    ],
    howItWorks: [
      [
        'You cannot allocate more than the receipt’s unallocated amount or the invoice’s open outstanding. Party must match.',
        'रसीद की बची राशि या बिल के बकाया से ज्यादा आवंटन नहीं। पार्टी एक ही होनी चाहिए।',
      ],
      [
        'If require-payment-reference is on, UPI and bank need a UTR; cash does not.',
        'रेफरेंस अनिवार्य हो तो UPI/बैंक पर UTR चाहिए; नकद पर नहीं।',
      ],
    ],
    businessImpact: [
      [
        'Allocation reduces customer outstanding and can free a credit limit so the next invoice can Complete. Ledgers and ageing read allocations, not the mere existence of a receipt.',
        'आवंटन बकाया घटाता है और क्रेडिट लिमिट खोल सकता है। लेजर/एजिंग आवंटन पढ़ते हैं, सिर्फ रसीद होना नहीं।',
      ],
    ],
    keyRules: [
      ['The invoice must be completed or returned. Drafts cannot take allocations.', 'बिल पूर्ण या RETURNED होना चाहिए। ड्राफ्ट पर आवंटन नहीं।'],
      ['Gateway receipts are refunded in the gateway, not voided here.', 'गेटवे रसीद यहाँ डिलीट नहीं — गेटवे में रिफंड।'],
    ],
    commonMistakes: [
      ['Taking a receipt against the wrong customer, then wondering why allocation says party mismatch.', 'गलत ग्राहक पर रसीद लेकर पार्टी मिसमैच।'],
      ['Expecting UPI QR on the invoice to mark the bill paid by itself — still record a receipt or wait for a payment-link capture.', 'इनवॉइस का UPI QR खुद Paid नहीं करता — रसीद दर्ज करें या पेमेंट लिंक का इंतज़ार करें।'],
    ],
    relatedPages: [
      { path: '/sales/history', labelKey: 'nav.salesHistory' },
      { path: '/payments/links', labelKey: 'nav.paymentLinks' },
      { path: '/reports/customer-ledger', labelKey: 'nav.customerLedger' },
    ],
    nextActions: [
      ['After saving a receipt, allocate it to the open invoices on that customer.', 'रसीद सेव के बाद उसी ग्राहक के खुले बिलों पर आवंटित करें।'],
    ],
  }),

  helpPage('customers', {
    title: ['Customers', 'ग्राहक'],
    summary: [
      'Party master for billing: name, state, GSTIN, credit limit, price list, blocked status. Saving a customer does not create a bill.',
      'बिलिंग के लिए पार्टी: नाम, राज्य, GSTIN, क्रेडिट लिमिट, प्राइस लिस्ट, ब्लॉक स्थिति। ग्राहक सेव करने से बिल नहीं बनता।',
    ],
    howItWorks: [
      [
        'State or GSTIN drives place of supply on GST bills. Duplicate GSTINs in the same company are rejected.',
        'राज्य/GSTIN से GST बिल का place of supply आता है। उसी कंपनी में डुप्लिकेट GSTIN नहीं चलता।',
      ],
      [
        'A limit greater than zero blocks Save & Complete when open exposure plus the new bill exceeds it. Exposure is outstanding after advances. With books on, the check uses the higher of the ledger and the document figure. Zero or blank means no check.',
        'लिमिट > 0 हो और खुला एक्सपोज़र + नया बिल लिमिट से ऊपर हो तो Save & Complete रुकता है। एक्सपोज़र अग्रिम के बाद बकाया है। खाते चालू हों तो जाँच लेजर और दस्तावेज़ में से बड़ी रकम लेती है। 0 या खाली = जाँच नहीं।',
      ],
    ],
    businessImpact: [
      [
        'Blocked status stops new invoices and quotation convert. Credit limit and price list affect the next Complete, not past bills.',
        'ब्लॉक स्थिति नया बिल और कोटेशन कन्वर्ट रोकती है। लिमिट/प्राइस लिस्ट अगले Complete पर लगता है, पुराने बिलों पर नहीं।',
      ],
    ],
    keyRules: [
      ['Only the Owner (or granted capability) should block/unblock. This is a credit or compliance hold.', 'ब्लॉक/अनब्लॉक ओनर (या दी गई अनुमति) करें। यह क्रेडिट/कंप्लायंस होल्ड है।'],
    ],
    commonMistakes: [
      ['Creating a second customer for the same GSTIN instead of reusing the party.', 'एक GSTIN पर दूसरा ग्राहक बनाना — पुरानी पार्टी दोबारा इस्तेमाल करें।'],
    ],
    relatedPages: [
      { path: '/sales/new', labelKey: 'nav.newInvoice' },
      { path: '/sales/receipts', labelKey: 'nav.receipts' },
      { path: '/settings/price-lists', labelKey: 'nav.priceLists' },
    ],
    nextActions: [
      ['Fill state and GSTIN before the first GST bill. Set a credit limit only if you want Complete to enforce it.', 'पहले GST बिल से पहले राज्य और GSTIN भरें। लिमिट तभी लगाएँ जब Complete पर लागू करनी हो।'],
    ],
  }),

  helpPage('sales-returns', {
    title: ['Sales returns', 'बिक्री वापसी'],
    summary: [
      'Return goods against a completed sale. Completing the return brings stock back and adjusts the customer. A partial return leaves the original invoice COMPLETED.',
      'पूर्ण बिक्री के विरुद्ध माल वापस। रिटर्न Complete करने से स्टॉक लौटता है और ग्राहक समायोजित होता है। आंशिक रिटर्न पर मूल बिल COMPLETED रहता है।',
    ],
    howItWorks: [
      ['You cannot cancel the original invoice after a completed return exists.', 'पूर्ण रिटर्न के बाद मूल बिल रद्द नहीं होता।'],
    ],
    businessImpact: [
      [
        'Stock in, customer balance down, GST worksheets pick up the return / linked credit note path. Reports must not keep treating a full return as a live sale.',
        'स्टॉक अंदर, ग्राहक बकाया कम, GST वर्कशीट रिटर्न/क्रेडिट नोट देखती हैं। पूरी वापसी को चालू बिक्री न गिनें।',
      ],
    ],
    keyRules: [
      ['Return against a completed sale only. Quantity cannot exceed what remains returnable on each line.', 'केवल पूर्ण बिक्री पर रिटर्न। मात्रा प्रत्येक लाइन की बची वापसी से ज्यादा नहीं।'],
    ],
    commonMistakes: [
      ['Cancelling instead of returning after the customer already booked the invoice.', 'ग्राहक के बुक कर लेने के बाद रद्द करना — रिटर्न/क्रेडिट नोट लें।'],
    ],
    relatedPages: [
      { path: '/sales/history', labelKey: 'nav.salesHistory' },
      { path: '/sales/credit-notes', labelKey: 'nav.creditNotes' },
      { path: '/inventory/stock', labelKey: 'nav.currentStock' },
    ],
    nextActions: [
      ['Complete the return, then check stock and the customer ledger.', 'रिटर्न Complete करें, फिर स्टॉक और ग्राहक लेजर देखें।'],
    ],
  }),

  helpPage('sales-credit-notes', {
    title: ['Sales credit notes', 'बिक्री क्रेडिट नोट'],
    summary: [
      'Legal way to reduce a completed tax invoice (return, post-sale discount, deficiency, correction). Completed notes are not line-edited — reverse with a debit note if needed.',
      'पूर्ण टैक्स इनवॉइस घटाने का कानूनी तरीका (रिटर्न, बाद की छूट, कमी, सुधार)। पूर्ण नोट की लाइनें एडिट नहीं — ज़रूरत हो तो डेबिट नोट।',
    ],
    howItWorks: [
      ['GST credit notes must link the original invoice. Prefer this over rewriting a completed bill.', 'GST क्रेडिट नोट मूल बिल से लिंक होना चाहिए। पूर्ण बिल दोबारा लिखने से यही बेहतर है।'],
    ],
    businessImpact: [
      [
        'Reduces what the customer owes and GST output on worksheets. Stock only moves if the reason/path is a goods return — a pure value credit note does not put stock back.',
        'ग्राहक बकाया और GST आउटपुट घटता है। माल वापसी वाले पथ पर ही स्टॉक लौटता है — केवल मूल्य का क्रेडिट नोट स्टॉक नहीं लाता।',
      ],
    ],
    keyRules: [
      [
        'GST law caps output-tax credit notes at 30 November after the FY (or annual return, whichever is earlier). Bizboard enforces period lock, not that statutory cutoff — your CA must still watch 30 Nov.',
        'GST में आउटपुट टैक्स क्रेडिट नोट की सीमा वित्तीय वर्ष के बाद 30 नवम्बर (या वार्षिक रिटर्न, जो पहले हो)। बिज़बोर्ड पीरियड लॉक लागू करता है, वह कानूनी कटऑफ नहीं — CA 30 नवम्बर देखें।',
      ],
    ],
    commonMistakes: [
      ['Issuing a credit note for a bill that should never have existed and has no allocations — **t:common.cancel** may be the right action instead.', 'जो बिल बनना ही नहीं चाहिए था और आवंटन नहीं — कभी-कभी **t:common.cancel** सही है।'],
    ],
    relatedPages: [
      { path: '/sales/history', labelKey: 'nav.salesHistory' },
      { path: '/sales/debit-notes', labelKey: 'nav.debitNotes' },
      { path: '/sales/returns', labelKey: 'nav.salesReturns' },
    ],
    nextActions: [
      ['Link the original invoice, pick the reason, Complete. Then check the customer outstanding.', 'मूल बिल लिंक करें, कारण चुनें, Complete करें। फिर ग्राहक बकाया देखें।'],
    ],
  }),

  helpPage('sales-debit-notes', {
    title: ['Sales debit notes', 'बिक्री डेबिट नोट'],
    summary: [
      'Increases what the customer owes after a completed invoice (extra charge, under-billing). Does not issue stock.',
      'पूर्ण बिल के बाद ग्राहक का बकाया बढ़ाता है (अतिरिक्त चार्ज, कम बिलिंग)। स्टॉक नहीं काटता।',
    ],
    howItWorks: [
      ['Completed notes are not line-edited. Reverse with a credit note if the extra charge was wrong.', 'पूर्ण नोट की लाइनें एडिट नहीं। गलत अतिरिक्त चार्ज हो तो क्रेडिट नोट।'],
    ],
    businessImpact: [
      ['Raises receivables and GST output on worksheets. Reports and ageing include completed debit notes.', 'प्राप्य और GST आउटपुट बढ़ता है। रिपोर्ट/एजिंग पूर्ण डेबिट नोट गिनती हैं।'],
    ],
    keyRules: [
      ['Use this when you under-billed; use a new invoice only when it is a new supply.', 'कम बिल हो तो यही; नई सप्लाई हो तो नया इनवॉइस।'],
    ],
    commonMistakes: [
      ['Editing the original completed invoice instead of a debit note.', 'मूल पूर्ण बिल एडिट करना — डेबिट नोट लें।'],
    ],
    relatedPages: [
      { path: '/sales/credit-notes', labelKey: 'nav.creditNotes' },
      { path: '/sales/history', labelKey: 'nav.salesHistory' },
    ],
    nextActions: [
      ['Complete the note, then collect the extra amount via a receipt allocation.', 'नोट Complete करें, फिर रसीद आवंटन से अतिरिक्त राशि लें।'],
    ],
  }),

  helpPage('quick-entry', {
    title: ['Quick order entry', 'त्वरित ऑर्डर एंट्री'],
    summary: [
      'A short path to add a customer and lines for a bill. It still uses the same Complete rules as the full invoice editor when you finish the bill.',
      'ग्राहक और लाइनें जोड़ने का छोटा रास्ता। बिल खत्म करते समय पूरे इनवॉइस वाले वही Complete नियम लगते हैं।',
    ],
    howItWorks: [
      ['Pick a recent or searched customer and products. This screen does not bypass stock, GST or credit-limit gates.', 'हाल का/खोजा ग्राहक और आइटम चुनें। यह स्क्रीन स्टॉक/GST/लिमिट के द्वार नहीं छोड़ती।'],
    ],
    businessImpact: [
      ['Once Completed, the bill hits stock, customer balance, GST and reports like any other invoice.', 'Complete के बाद यह बिल किसी भी इनवॉइस की तरह स्टॉक, बकाया, GST और रिपोर्ट में जाता है।'],
    ],
    keyRules: [
      ['Need the create-sales capability. Walk-in / GST rules are the same as New Invoice.', 'सेल्स बनाने की अनुमति चाहिए। वॉक-इन/GST नियम नए इनवॉइस जैसे।'],
    ],
    commonMistakes: [
      ['Using this for a GST B2B bill without customer state/GSTIN, then hitting Complete errors.', 'GST B2B पर राज्य/GSTIN बिना Complete करने पर एरर।'],
    ],
    relatedPages: [
      { path: '/sales/new', labelKey: 'nav.newInvoice' },
      { path: '/sales/history', labelKey: 'nav.salesHistory' },
    ],
    nextActions: [
      ['Finish the bill on this flow or open the full editor if you need tax options, e-Way or multi-godown.', 'यहीं बिल खत्म करें, या टैक्स/e-Way/मल्टी-गोदाम के लिए पूरा एडिटर खोलें।'],
    ],
  }),

  helpPage('recurring-invoices', {
    title: ['Recurring invoices', 'आवर्ती इनवॉइस'],
    summary: [
      'A schedule creates a **draft** invoice unless you tick Complete the invoice. That tick is off by default.',
      'शेड्यूल **ड्राफ्ट** इनवॉइस बनाता है, जब तक आप “चालान पूर्ण करें” न चुनें। यह विकल्प डिफ़ॉल्ट रूप से बंद है।',
    ],
    howItWorks: [
      ['When a draft appears, open it and press **t:common.complete** after checking stock, GSTIN and the customer.', 'ड्राफ्ट दिखे तो खोलें, स्टॉक/GSTIN/ग्राहक जाँचकर **t:common.complete** दबाएँ।'],
    ],
    businessImpact: [
      ['Until you Complete, there is no stock movement, no receivable and no GST row.', 'Complete से पहले न स्टॉक, न बकाया, न GST पंक्ति।'],
    ],
    keyRules: [
      ['This is a convenience for retainers-style billing, not a filing or auto-debit engine.', 'यह सुविधा है, फाइलिंग या ऑटो-डेबिट इंजन नहीं।'],
    ],
    commonMistakes: [
      ['Assuming the schedule already billed the customer.', 'शेड्यूल को ग्राहक पर बिल समझना।'],
    ],
    relatedPages: [
      { path: '/sales/history', labelKey: 'nav.salesHistory' },
      { path: '/sales/new', labelKey: 'nav.newInvoice' },
    ],
    nextActions: [
      ['Open each new draft, review lines, then Complete.', 'हर नया ड्राफ्ट खोलें, लाइनें देखें, Complete करें।'],
    ],
  }),

  helpPage('sales-bill-upload', {
    title: ['Upload sales bill', 'बिक्री बिल अपलोड'],
    summary: [
      'Photo or PDF assist that creates a **draft** invoice for you to check. Open it from Sales or from the link on Create Sales Invoice. It does not invent GST rate or quantity and does not complete the bill.',
      'फोटो/PDF से **ड्राफ्ट** इनवॉइस बनता है। सेल्स से या Create Sales Invoice के लिंक से खोलें। यह GST दर या मात्रा गढ़ता नहीं और बिल पूरा नहीं करता।',
    ],
    howItWorks: [
      ['You need the import capability. After extract, review every line, godown, and GSTIN, then Save & Complete on the invoice editor.', 'इम्पोर्ट अनुमति चाहिए। निकालने के बाद हर लाइन, गोदाम और GSTIN जाँचें, फिर इनवॉइस एडिटर पर Save & Complete करें।'],
    ],
    businessImpact: [
      ['No stock, GST or outstanding until you Complete the resulting draft.', 'ड्राफ्ट Complete होने तक स्टॉक/GST/बकाया नहीं।'],
    ],
    keyRules: [
      ['Treat OCR as aid-only. Wrong HSN or rate on Complete still becomes your books.', 'OCR केवल सहायता है। गलत HSN/दर Complete पर आपकी किताब बन जाती है।'],
    ],
    commonMistakes: [
      ['Completing without checking godown and GSTIN on the draft.', 'ड्राफ्ट पर गोदाम और GSTIN जाँचे बिना Complete।'],
    ],
    relatedPages: [
      { path: '/sales/history', labelKey: 'nav.salesHistory' },
      { path: '/sales/new', labelKey: 'nav.newInvoice' },
    ],
    nextActions: [
      ['Open the draft, fix lines, Complete.', 'ड्राफ्ट खोलें, लाइनें ठीक करें, Complete करें।'],
    ],
  }),

  helpPage('delivery-routes', {
    title: ['Delivery routes', 'डिलीवरी रूट'],
    summary: [
      'Plan a trip over existing sales orders: vehicle, driver, stop order, expected profit. Stock still posts only when you complete a delivery challan — this page does not dispatch goods.',
      'मौजूदा सेल्स ऑर्डर पर यात्रा योजना: वाहन, ड्राइवर, स्टॉप क्रम, अनुमानित लाभ। स्टॉक तब लगता है जब डिलीवरी चालान Complete हो — यह पेज माल नहीं भेजता।',
    ],
    howItWorks: [
      [
        'Create a planned route, add open sales orders as stops, start the trip, then mark stops delivered, failed or returned. You can remove a stop only while the route is still planned.',
        'योजनाबद्ध रूट बनाएँ, खुले सेल्स ऑर्डर स्टॉप जोड़ें, यात्रा शुरू करें, फिर डिलीवर/विफल/वापस चिह्नित करें। स्टॉप केवल योजना अवस्था में हटा सकते हैं।',
      ],
    ],
    businessImpact: [
      [
        'Expected / estimated profit uses current purchase price, not later FIFO invoice profit. Logistics cost is manual until tied to an expense.',
        'अनुमानित लाभ मौजूदा खरीद मूल्य से है, बाद के FIFO इनवॉइस लाभ से नहीं। लॉजिस्टिक्स लागत खर्च से जुड़ने तक मैनुअल है।',
      ],
    ],
    keyRules: [
      ['Sales-order stops only for v1. Completing a route does not complete challans or invoices.', 'v1 में केवल सेल्स-ऑर्डर स्टॉप। रूट Complete चालान या इनवॉइस Complete नहीं करता।'],
    ],
    commonMistakes: [
      ['Treating a planned route as stock already out of the godown.', 'योजनाबद्ध रूट को गोदाम से निकला स्टॉक समझना।'],
    ],
    relatedPages: [
      { path: '/sales/orders', labelKey: 'nav.salesOrders' },
      { path: '/sales/delivery-challans', labelKey: 'nav.deliveryChallans' },
    ],
    nextActions: [
      ['Add open orders while planned, start the trip, then complete or mark failed stops honestly.', 'योजना में खुले ऑर्डर जोड़ें, यात्रा शुरू करें, फिर स्टॉप Complete या विफल सही चिह्नित करें।'],
    ],
  }),
];
