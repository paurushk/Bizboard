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
      'Every sales invoice for this company. Find a bill, see what is still due, collect it, reprint it, or cancel it. Open a completed row for the PDF, share link, e-Invoice, e-Way, payment, and Profit Details. The list follows the same invoice rules as the invoice screen.',
      'कंपनी के सभी बिक्री बिल। बिल ढूँढें, बकाया देखें, भुगतान दर्ज करें, दोबारा प्रिंट करें या रद्द करें। पूर्ण पंक्ति पर PDF, शेयर लिंक, e-Invoice, e-Way, भुगतान और Profit Details मिलते हैं। सूची पर भी इनवॉइस स्क्रीन वाले नियम लागू होते हैं।',
    ],
    howItWorks: [
      [
        'Search matches the bill number, customer name, or phone. The customer box needs at least 2 letters. Status chips, date presets (This FY, quarters, Custom) and the sort are kept in the address bar, so Back and a copied link return to the same view.',
        'खोज बिल नंबर, ग्राहक के नाम या फ़ोन से मिलती है। ग्राहक बॉक्स में कम से कम 2 अक्षर लिखें। स्थिति, तारीख (This FY, तिमाही, Custom) और क्रम पता-पट्टी में रहते हैं, इसलिए Back और कॉपी किया लिंक वही सूची खोलते हैं।',
      ],
      [
        'Paid means nothing is due. Partial means a receipt, credit note, or settlement discount is applied and money is still due. Unpaid means the full amount is due. Overdue adds completed bills past their due date with money still due. The chips count bills and amounts for your current filters.',
        'Paid का मतलब कुछ बकाया नहीं। Partial का मतलब रसीद, क्रेडिट नोट या सेटलमेंट छूट लगी है और पैसा अभी बाकी है। Unpaid का मतलब पूरी रकम बाकी है। Overdue में वे पूर्ण बिल आते हैं जिनकी देय तारीख निकल गई और पैसा बाकी है। चिप्स आपके फ़िल्टर के हिसाब से बिल और रकम गिनते हैं।',
      ],
      [
        'Sort by newest, oldest, total, or due from the Sort box or the Date, Total, and Due headers. Export CSV downloads up to 5,000 rows with the same filters and sort.',
        'Sort बॉक्स या Date, Total, Due शीर्षक से नए, पुराने, कुल या बकाया के क्रम में लगाएँ। Export CSV उन्हीं फ़िल्टर और क्रम के साथ 5,000 पंक्तियों तक डाउनलोड करता है।',
      ],
      [
        'Tick up to 100 bills and use Download PDFs (zip). Drafts and cancelled bills are skipped and named. Only the person who made the ZIP can download it, and it is removed after 7 days.',
        '100 बिल तक चुनें और Download PDFs (zip) दबाएँ। ड्राफ्ट और रद्द बिल छोड़े जाते हैं और उनके नंबर संदेश में आते हैं। ZIP सिर्फ़ बनाने वाला डाउनलोड कर सकता है और 7 दिन बाद हट जाती है।',
      ],
      [
        'The row menu shows what the bill and your role allow: Edit, Complete, and Delete for drafts; Print, Download, 80 mm and 58 mm receipts, Share, Record payment, Sales return, Profit Details, and Cancel for completed bills. Amend is for the Owner.',
        'पंक्ति मेनू वही दिखाता है जो बिल और आपकी भूमिका अनुमति देती है: ड्राफ्ट पर Edit, Complete, Delete; पूर्ण बिल पर Print, Download, 80 mm और 58 mm रसीद, Share, Record payment, Sales return, Profit Details और Cancel। Amend सिर्फ़ Owner के लिए है।',
      ],
    ],
    businessImpact: [
      [
        'This list reads invoice status, payment state, and return state. Completing a draft here assigns the number and posts stock and the ledger with the full amount due. Record payment moves the bill to Partial or Paid at once.',
        'यह सूची बिल की स्थिति, भुगतान और रिटर्न पढ़ती है। यहाँ ड्राफ्ट Complete करने पर नंबर मिलता है, स्टॉक और लेजर पोस्ट होते हैं और पूरी रकम बकाया रहती है। Record payment से बिल तुरंत Partial या Paid हो जाता है।',
      ],
      [
        'Cancelling reverses the ledger and restores stock. The reason you type is kept on the bill and appears in the CSV export.',
        'रद्द करने से लेजर उलटता है और स्टॉक वापस आता है। आपका लिखा कारण बिल पर रहता है और CSV में दिखता है।',
      ],
    ],
    keyRules: [
      ['List actions follow every Complete check: stock, GST, period lock, and credit limit.', 'सूची की क्रियाओं पर Complete की हर जाँच लागू होती है: स्टॉक, GST, पीरियड लॉक और क्रेडिट लिमिट।'],
      [
        'Cancel needs a reason and cancel permission. A second Owner must approve it unless you are the only Owner; until then the row shows Cancel pending and the bill stays completed. After approval, choose Cancel again. A request lasts 72 hours.',
        'Cancel के लिए कारण और रद्द करने की अनुमति चाहिए। अगर आप अकेले Owner नहीं हैं, तो दूसरे Owner की मंज़ूरी चाहिए; तब तक पंक्ति पर Cancel pending दिखता है और बिल पूर्ण रहता है। मंज़ूरी के बाद Cancel फिर से चुनें। अनुरोध 72 घंटे तक मान्य रहता है।',
      ],
      [
        'Cancel is refused while a receipt is allocated, an IRN or e-way bill is live, or a return or credit/debit note is on the bill.',
        'रसीद आवंटित हो, IRN या ई-वे बिल चालू हो, या बिल पर रिटर्न या क्रेडिट/डेबिट नोट हो, तो Cancel मना होता है।',
      ],
      [
        'Only drafts can be deleted. Amend on a completed bill changes prices, discounts, charges, and dates; lines, quantities, GST rates, and the customer stay as issued.',
        'सिर्फ़ ड्राफ्ट डिलीट होते हैं। पूर्ण बिल पर Amend से कीमत, छूट, चार्ज और तारीख बदलती है; लाइनें, मात्रा, GST दर और ग्राहक वही रहते हैं।',
      ],
    ],
    commonMistakes: [
      ['Deleting or cancelling a completed bill to fix a quantity. Use a sales return or a credit note for the part being taken back.', 'मात्रा ठीक करने के लिए पूर्ण बिल डिलीट या रद्द करना। वापस ली गई मात्रा के लिए सेल्स रिटर्न या क्रेडिट नोट बनाएँ।'],
      ['Looking for an old bill with the date range still on This Month. Widen the date range and clear the status and payment chips first.', 'तारीख This Month पर छोड़कर पुराना बिल ढूँढना। पहले तारीख की सीमा बढ़ाएँ और स्थिति व भुगतान चिप्स हटाएँ।'],
      ['Recording the same payment again on Money in after recording it here. Each receipt counts once against the bill.', 'यहाँ भुगतान दर्ज करने के बाद Money in पर वही भुगतान दोबारा दर्ज करना। हर रसीद बिल पर एक बार गिनी जाती है।'],
    ],
    relatedPages: [
      { path: '/sales/new', labelKey: 'nav.newInvoice' },
      { path: '/sales/receipts', labelKey: 'nav.receipts' },
      { path: '/sales/returns', labelKey: 'nav.salesReturns' },
      { path: '/reports/sales', labelKey: 'nav.salesReports' },
    ],
    nextActions: [
      ['Open drafts that should be billed today and press Complete after checking godown and GST.', 'आज के ड्राफ्ट खोलें, गोदाम और GST जाँचकर Complete दबाएँ।'],
      ['Pick Unpaid and Overdue, sort by Highest due, and call those customers first.', 'Unpaid और Overdue चुनें, Highest due से क्रम लगाएँ और पहले उन ग्राहकों से बात करें।'],
    ],
  }),

  helpPage('quotations', {
    title: ['Quotations', 'कोटेशन'],
    summary: [
      'Price offers. Create and edit them on a full page, share a PDF link, then convert the remaining quantity to a **draft** invoice or sales order. Conversion does not Complete the invoice and does not take stock.',
      'कीमत का प्रस्ताव। पूरे पेज पर बनाएँ और बदलें, PDF लिंक भेजें, फिर बची मात्रा को **ड्राफ्ट** इनवॉइस या सेल्स ऑर्डर में बदलें। कन्वर्ट से बिल Complete नहीं होता और स्टॉक नहीं कटता।',
    ],
    howItWorks: [
      [
        'Convert only from an allowed quotation status. You can convert part of a line; leftover quantity stays convertible.',
        'अनुमत स्थिति से ही कन्वर्ट करें। लाइन की कुछ मात्रा कन्वर्ट हो सकती है; बाकी बाद में।',
      ],
      [
        'When a quotation is converted in parts, additional charges and the invoice discount are shared across the documents by value, so together they add up to the quotation.',
        'कोटेशन कई हिस्सों में कन्वर्ट हो तो अतिरिक्त शुल्क और इनवॉइस डिस्काउंट मूल्य के अनुसार बँटते हैं, ताकि कुल कोटेशन के बराबर रहें।',
      ],
      [
        'Row menu: **Share** makes a public PDF link (and a WhatsApp message), **Duplicate** copies it into a new draft and leaves the original unchanged, **Close remaining** drops the unconverted quantity with a reason, and the owner can reopen it.',
        'रो मेन्यू: **Share** से PDF लिंक/WhatsApp, **Duplicate** से नया ड्राफ्ट (मूल अपरिवर्तित), **Close remaining** से बची मात्रा कारण सहित बंद; मालिक दोबारा खोल सकता है।',
      ],
      [
        'If your company has turned on the quotation lifecycle, a shared quotation becomes Sent and can be marked Accepted or Rejected. Editing a Sent quotation sends it back to Draft.',
        'कंपनी में कोटेशन लाइफसाइकल चालू हो तो शेयर करने पर कोटेशन Sent बनता है और Accepted/Rejected चिह्नित हो सकता है। Sent को बदलने पर वह Draft हो जाता है।',
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
      [
        'Deleting or cancelling the draft order or invoice gives the converted quantity back to the quotation. An expired quotation that gets its quantity back returns to Draft.',
        'ड्राफ्ट ऑर्डर/इनवॉइस हटाने या रद्द करने पर कन्वर्ट की गई मात्रा कोटेशन को वापस मिलती है। समाप्त कोटेशन वापस Draft हो जाता है।',
      ],
    ],
    keyRules: [
      ['Quotations do not post tax or receivables. Do not treat a converted draft as a tax invoice until Complete.', 'कोटेशन टैक्स या बकाया पोस्ट नहीं करता। कन्वर्टेड ड्राफ्ट Complete तक टैक्स इनवॉइस नहीं है।'],
      ['A partly converted quotation cannot be cancelled; use Close remaining. A quotation takes its number when created, so deleting a draft leaves a gap.', 'आंशिक कन्वर्ट कोटेशन रद्द नहीं होता; Close remaining उपयोग करें। नंबर बनाते समय मिलता है, इसलिए ड्राफ्ट हटाने पर नंबर में खाली जगह रहती है।'],
      ['The public link shows an expired quotation as expired, and stops working once revoked, cancelled or rejected. GST is worked out per invoice, so split documents can differ from the quotation by a paisa.', 'पब्लिक लिंक समाप्त कोटेशन को समाप्त दिखाता है; रद्द/अस्वीकृत/वापस लेने पर बंद हो जाता है। GST हर इनवॉइस पर अलग निकलता है, इसलिए एक पैसे का अंतर हो सकता है।'],
    ],
    commonMistakes: [
      ['Assuming convert reserved stock. Sales orders reserve on confirm; quotations do not.', 'कन्वर्ट को स्टॉक रिज़र्व न समझें। रिज़र्व सेल्स ऑर्डर कन्फर्म पर होता है।'],
      ['Leaving the editor with unsaved changes. Save first, or confirm when asked.', 'बिना सेव किए एडिटर छोड़ना। पहले सेव करें, या पूछे जाने पर पुष्टि करें।'],
    ],
    relatedPages: [
      { path: '/sales/new', labelKey: 'nav.newInvoice' },
      { path: '/sales/orders', labelKey: 'nav.salesOrders' },
      { path: '/sales/customers', labelKey: 'nav.customers' },
    ],
    nextActions: [
      ['After convert, open the draft invoice or order, check godown and GST, then Complete when ready.', 'कन्वर्ट के बाद ड्राफ्ट खोलें, गोदाम/GST जाँचें, तैयार हों तो Complete करें।'],
      ['Chase quotations nearing their validity date, or Close remaining on ones that will not convert.', 'वैधता खत्म होने वाले कोटेशन पर फॉलो-अप करें, या न बदलने वालों पर Close remaining करें।'],
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
      [
        'UPI, bank and card money must name the bank account it landed in; the default is filled in. CREDIT is not a way of being paid: leave the bill unpaid instead.',
        'UPI, बैंक और कार्ड की रकम में वह बैंक खाता बताना ज़रूरी है जिसमें पैसा आया; डिफ़ॉल्ट भर जाता है। उधार (CREDIT) भुगतान का तरीका नहीं है: बिल को बकाया रहने दें।',
      ],
      [
        '**Cheques.** A cheque counts as received the moment it is entered and can be applied to a bill. If your company holds cheques as advances until they clear (Payment settings), the cheque stays an advance until you mark it cleared; what you chose is then applied. A bounced cheque is voided and its bills reopen.',
        '**चेक।** चेक दर्ज होते ही प्राप्त माना जाता है और बिल पर लग सकता है। यदि आपकी कंपनी चेक को क्लियर होने तक अग्रिम रखती है (पेमेंट सेटिंग्स), तो क्लियर चिह्नित करने तक वह अग्रिम रहता है; फिर आपका चुनाव लागू होता है। बाउंस चेक रद्द होता है और उसके बिल फिर खुल जाते हैं।',
      ],
      [
        '**TDS deducted by the customer.** Under More options, enter the tax the customer deducted (and the section). The bill is settled for the amount received plus the TDS; the TDS waits as a receivable until the certificate arrives. A receipt with TDS cannot be refunded as an advance.',
        '**ग्राहक द्वारा काटा गया TDS।** और विकल्प में ग्राहक द्वारा काटा गया कर (और धारा) लिखें। बिल मिली राशि और TDS के जोड़ से चुकता होता है; प्रमाणपत्र आने तक TDS प्राप्य रहता है। TDS वाली रसीद अग्रिम के रूप में वापस नहीं हो सकती।',
      ],
      [
        '**Refund an advance** gives back money that was never applied to a bill, in cash, UPI or bank transfer, with a reason; the receipt stays on record. Void the refund first if the receipt itself must be voided.',
        '**अग्रिम लौटाएँ** उस रकम को लौटाता है जो किसी बिल पर नहीं लगी, नकद, UPI या बैंक ट्रांसफर से, कारण के साथ; रसीद रिकॉर्ड में रहती है। रसीद ही रद्द करनी हो तो पहले वापसी रद्द करें।',
      ],
      [
        '**Settlement discount.** An early-payment discount you allow is entered with the receipt and only counts once the receipt is applied to a bill. It is spread over the bills in proportion to the cash applied, so the bill clears for cash plus discount.',
        '**सेटलमेंट डिस्काउंट।** जल्दी भुगतान पर दी गई छूट रसीद के साथ लिखी जाती है और रसीद बिल पर लगने पर ही गिनी जाती है। यह लगाई गई नकद के अनुपात में बिलों पर बँटती है, इसलिए बिल नकद और छूट के जोड़ से चुकता होता है।',
      ],
      [
        '**Find and sort.** Search by receipt number, customer name, phone, UTR or reference (at least 3 characters). Click a column heading to sort, filter by date, mode, status or bank match, and use **Export CSV** if you have export permission. Totals above the list follow your filters.',
        '**खोजें और क्रमबद्ध करें।** रसीद नंबर, ग्राहक का नाम, फ़ोन, UTR या संदर्भ से खोजें (कम से कम 3 अक्षर)। कॉलम शीर्षक दबाकर क्रम बदलें, तारीख, मोड, स्थिति या बैंक मिलान से छाँटें, और निर्यात अनुमति हो तो **Export CSV** लें। सूची के ऊपर के योग आपके फ़िल्टर के अनुसार होते हैं।',
      ],
      [
        '**Apply to oldest bills.** Tick several advances and apply each to its own customer’s oldest open bills in one go. A receipt that fails never stops the others, and running it twice does not apply twice.',
        '**सबसे पुराने बिलों पर लगाएँ।** कई अग्रिम चुनकर हर एक को उसी ग्राहक के सबसे पुराने खुले बिलों पर एक साथ लगाएँ। जो रसीद न लगे वह बाकी को नहीं रोकती, और दोबारा चलाने पर दो बार नहीं लगती।',
      ],
      [
        '**Send the voucher.** Open the voucher to download it in English or Hindi, or use **Send** to share it by WhatsApp or email. Without the customer’s WhatsApp opt-in you get a link to send from your own phone, and nothing is recorded as delivered.',
        '**वाउचर भेजें।** वाउचर खोलकर अंग्रेज़ी या हिंदी में डाउनलोड करें, या **Send** से WhatsApp या ईमेल पर भेजें। ग्राहक की WhatsApp सहमति न हो तो अपने फ़ोन से भेजने का लिंक मिलता है, और डिलीवर हुआ दर्ज नहीं होता।',
      ],
      [
        '**Walk-in money.** The walk-in account cannot keep an advance, so the receipt must be applied to bills in full. If money landed there by mistake, use **Move to customer** to transfer it to whoever paid; a dated entry is posted and the change is recorded.',
        '**वॉक-इन की रकम।** वॉक-इन खाता अग्रिम नहीं रख सकता, इसलिए रसीद पूरी तरह बिलों पर लगनी चाहिए। रकम गलती से वहाँ आ गई हो तो **Move to customer** से उसे भुगतान करने वाले ग्राहक पर भेजें; तारीख वाली एंट्री बनती है और बदलाव दर्ज होता है।',
      ],
      [
        '**No connection.** A cash or cheque receipt is saved on this device and sent when you are back online. Open **Receipts waiting to send** to send now, discard, or see one that could not be recorded and why.',
        '**कनेक्शन न होने पर।** नकद या चेक रसीद इसी डिवाइस पर सेव होती है और ऑनलाइन आने पर भेजी जाती है। **Receipts waiting to send** में तुरंत भेजें, हटाएँ, या देखें कि कोई रसीद क्यों दर्ज नहीं हो पाई।',
      ],
      [
        'Edit changes only notes, reference, UTR and (for bank money not matched to a bank line) the bank account. Customer, amount, mode and date need a void and a new receipt.',
        'संपादन से सिर्फ टिप्पणी, संदर्भ, UTR और (बैंक से न मिलाई गई बैंक रकम के लिए) बैंक खाता बदलता है। ग्राहक, राशि, मोड और तारीख के लिए रद्द करके नई रसीद बनाएँ।',
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
      [
        'Cash of ₹2,00,000 or more from one person in a day is not allowed (Section 269ST). You see a warning, or the receipt is refused if your company chose to block.',
        'एक व्यक्ति से एक दिन में ₹2,00,000 या अधिक नकद लेना मना है (धारा 269ST)। चेतावनी दिखती है, या कंपनी ने रोकना चुना हो तो रसीद नहीं बनती।',
      ],
      [
        'Voiding a receipt needs a reason, reverses its books entry and reopens the bills it paid. It is refused while an advance refund is live (void the refund first) or while the receipt is matched to a bank line (unmatch it in Bank reconciliation).',
        'रसीद रद्द करने के लिए कारण चाहिए; इससे उसकी बही एंट्री उलटती है और उसके बिल फिर खुल जाते हैं। अग्रिम वापसी चालू हो (पहले वापसी रद्द करें) या रसीद बैंक लाइन से मिली हो (बैंक मिलान में अनमैच करें) तो रद्द नहीं होती।',
      ],
      [
        'The same UTR on two receipts is flagged as a possible duplicate. If it is genuine, dismiss the alert and say why.',
        'दो रसीदों पर एक ही UTR हो तो संभावित डुप्लिकेट का निशान लगता है। यदि वह सही है तो अलर्ट हटाएँ और कारण लिखें।',
      ],
      [
        'A cash receipt counted in a closed till is corrected by a manager with Correct closed till; the till’s counted figures stay and the correction shows on its report.',
        'बंद गल्ले में गिनी गई नकद रसीद को मैनेजर "बंद गल्ला सुधारें" से ठीक करता है; गल्ले की गिनी हुई रकम वैसी रहती है और सुधार उसकी रिपोर्ट में दिखता है।',
      ],
    ],
    commonMistakes: [
      ['Taking a receipt against the wrong customer, then wondering why allocation says party mismatch.', 'गलत ग्राहक पर रसीद लेकर पार्टी मिसमैच।'],
      ['Entering the TDS as a settlement discount. TDS is tax the customer deducted and is claimed later; a discount is something you gave away.', 'TDS को सेटलमेंट डिस्काउंट की तरह लिखना। TDS ग्राहक द्वारा काटा गया कर है जो बाद में दावा होता है; डिस्काउंट आप खुद छोड़ते हैं।'],
      ['Voiding a receipt to change its amount or customer. Void it with a reason and enter a new one, or use Move to customer for walk-in money.', 'राशि या ग्राहक बदलने के लिए रसीद रद्द करना। कारण के साथ रद्द करके नई रसीद बनाएँ, या वॉक-इन की रकम के लिए Move to customer लें।'],
      ['Expecting UPI QR on the invoice to mark the bill paid by itself — still record a receipt or wait for a payment-link capture.', 'इनवॉइस का UPI QR खुद Paid नहीं करता — रसीद दर्ज करें या पेमेंट लिंक का इंतज़ार करें।'],
    ],
    relatedPages: [
      { path: '/sales/history', labelKey: 'nav.salesHistory' },
      { path: '/payments/links', labelKey: 'nav.paymentLinks' },
      { path: '/reports/customer-ledger', labelKey: 'nav.customerLedger' },
      { path: '/reports/tds-receivable', labelKey: 'nav.tdsReceivable' },
    ],
    nextActions: [
      ['After saving a receipt, allocate it to the open invoices on that customer.', 'रसीद सेव के बाद उसी ग्राहक के खुले बिलों पर आवंटित करें।'],
    ],
  }),

  helpPage('customers', {
    title: ['Customers', 'ग्राहक'],
    summary: [
      'The party master for customers: name, phone, GSTIN, state, tax class, credit terms, addresses, price list, and status. Saving a customer does not create a bill. The cards above the list show active customers, what is outstanding, advances held, and how many are over their limit or blocked.',
      'ग्राहकों की पार्टी सूची: नाम, फ़ोन, GSTIN, राज्य, कर वर्ग, क्रेडिट शर्तें, पते, प्राइस लिस्ट और स्थिति। ग्राहक सेव करने से बिल नहीं बनता। सूची के ऊपर के कार्ड सक्रिय ग्राहक, बकाया, जमा अग्रिम और सीमा पार या ब्लॉक ग्राहकों की गिनती दिखाते हैं।',
    ],
    howItWorks: [
      [
        'Type the GSTIN and the state and PAN fill in from it. Press Verify & autofill to look it up first. Without a live GSTIN service the check only confirms the format, so the status stays Unverified. Changing or clearing a GSTIN clears its old verification.',
        'GSTIN लिखें तो राज्य और PAN उसी से भर जाते हैं। पहले Verify & autofill दबाकर जाँच सकते हैं। GSTIN की लाइव सेवा चालू न हो तो सिर्फ़ फ़ॉर्मैट जाँचा जाता है और स्थिति Unverified रहती है। GSTIN बदलने या हटाने पर पुराना सत्यापन हट जाता है।',
      ],
      [
        'State or GSTIN drives place of supply on GST bills. A state that disagrees with the GSTIN is refused; a blank state is filled from the GSTIN. Two customers in one company cannot share a GSTIN, and the message names the customer that already has it.',
        'राज्य या GSTIN से GST बिल का place of supply तय होता है। GSTIN से मेल न खाने वाला राज्य मना होता है; खाली राज्य GSTIN से भर जाता है। एक कंपनी में दो ग्राहकों का GSTIN एक नहीं हो सकता, और संदेश में उस ग्राहक का नाम आता है जिसके पास वह है।',
      ],
      [
        'A limit greater than zero blocks Complete when open exposure plus the new bill exceeds it. Exposure is outstanding after advances. With books on, the check uses the higher of the ledger and the document figure. Zero or blank means no check. Only an owner or manager can change the credit limit and credit days.',
        'लिमिट > 0 हो और खुला एक्सपोज़र + नया बिल लिमिट से ऊपर हो तो Complete रुकता है। एक्सपोज़र अग्रिम के बाद बकाया है। खाते चालू हों तो जाँच लेजर और दस्तावेज़ में से बड़ी रकम लेती है। 0 या खाली = जाँच नहीं। क्रेडिट लिमिट और क्रेडिट दिन सिर्फ़ ओनर या मैनेजर बदल सकते हैं।',
      ],
      [
        'The row buttons are Edit, Block, and a More menu (Archive, Set as POS walk-in, Verify GSTIN on a phone). Tick rows that have a GSTIN and press Verify selected to check up to 10 at once. Click a customer name to open the Customer Snapshot.',
        'पंक्ति के बटन: Edit, Block और More मेनू (Archive, Set as POS walk-in, फ़ोन पर Verify GSTIN)। GSTIN वाली पंक्तियाँ चुनकर Verify selected दबाएँ — एक बार में 10 तक। ग्राहक के नाम पर क्लिक करके Customer Snapshot खोलें।',
      ],
      [
        'Export CSV downloads the customers your search and status filter match, in your chosen sort. It needs the financial-reports and export permissions, is limited to 20,000 rows, and each export is recorded.',
        'Export CSV आपकी खोज और स्थिति के फ़िल्टर से मिले ग्राहकों को चुने क्रम में डाउनलोड करता है। इसके लिए वित्तीय रिपोर्ट और एक्सपोर्ट की अनुमति चाहिए, सीमा 20,000 पंक्तियाँ है, और हर एक्सपोर्ट दर्ज होता है।',
      ],
    ],
    businessImpact: [
      [
        'A blocked or archived customer cannot get a new invoice, quotation, order, delivery challan, or quotation conversion. A draft they already have can still be saved or cancelled, but not completed. Receipts and credit notes still work, and recurring invoices skip them until they are active again.',
        'ब्लॉक या संग्रहित ग्राहक पर नया बिल, कोटेशन, ऑर्डर, डिलीवरी चालान या कोटेशन कन्वर्ट नहीं बनता। उनका पहले से बना ड्राफ्ट सेव या रद्द हो सकता है, पर Complete नहीं। रसीद और क्रेडिट नोट चलते रहते हैं, और आवर्ती बिल उनके सक्रिय होने तक छूट जाते हैं।',
      ],
      [
        'State, GSTIN and tax class decide CGST+SGST or IGST and the GSTR-1 table a bill lands in. Credit limit and price list apply from the next Complete, not to past bills.',
        'राज्य, GSTIN और कर वर्ग से CGST+SGST या IGST और GSTR-1 की तालिका तय होती है। क्रेडिट लिमिट और प्राइस लिस्ट अगले Complete से लगती हैं, पुराने बिलों पर नहीं।',
      ],
    ],
    keyRules: [
      [
        'Anyone who can create sales may Block. Unblock, Activate, Archive, and credit terms are for an owner or manager. This is a credit or compliance hold, not a software error.',
        'Block कोई भी कर सकता है जो बिल बना सकता है। Unblock, Activate, Archive और क्रेडिट शर्तें ओनर या मैनेजर के लिए हैं। यह क्रेडिट या कंप्लायंस होल्ड है, सॉफ़्टवेयर की गलती नहीं।',
      ],
      [
        'Archive is refused while the customer owes money or holds an unallocated advance: settle or allocate first. A customer nothing refers to is deleted; one with bills, receipts, contracts or similar is marked Inactive instead, and its recurring schedules pause.',
        'ग्राहक पर बकाया हो या अनावंटित अग्रिम हो तो Archive मना है: पहले निपटाएँ या आवंटित करें। जिस ग्राहक का कहीं उपयोग नहीं हुआ वह हट जाता है; जिसके बिल, रसीद, अनुबंध आदि हैं वह Inactive चिह्नित होता है और उसके आवर्ती शेड्यूल रुक जाते हैं।',
      ],
      [
        'The POS walk-in customer cannot have a GSTIN or a credit limit, cannot be blocked, and cannot be archived or deleted. An owner can make another active customer the walk-in from the More menu.',
        'POS वॉक-इन ग्राहक में GSTIN या क्रेडिट लिमिट नहीं हो सकती, उसे ब्लॉक, संग्रहित या डिलीट नहीं कर सकते। ओनर More मेनू से किसी दूसरे सक्रिय ग्राहक को वॉक-इन बना सकता है।',
      ],
      [
        'A phone number is a 10-digit Indian mobile starting 6 to 9, with an optional +91, 91 or 0 in front. If the form says someone else changed the customer, press Reload latest: what you typed is kept.',
        'फ़ोन 6 से 9 से शुरू होने वाला 10 अंकों का भारतीय मोबाइल है, आगे वैकल्पिक +91, 91 या 0। फ़ॉर्म कहे कि किसी और ने ग्राहक बदल दिया, तो Reload latest दबाएँ: आपका लिखा बना रहता है।',
      ],
    ],
    commonMistakes: [
      ['Creating a second customer for the same GSTIN instead of reusing the party.', 'एक GSTIN पर दूसरा ग्राहक बनाना — पुरानी पार्टी दोबारा इस्तेमाल करें।'],
      ['Choosing a state by hand that disagrees with the GSTIN. Let the GSTIN fill it, or fix the GSTIN.', 'GSTIN से मेल न खाने वाला राज्य हाथ से चुनना। राज्य GSTIN से भरने दें, या GSTIN सुधारें।'],
      ['Archiving a customer to hide a balance. Archive only after the balance is settled; use Block to stop new bills.', 'बकाया छिपाने के लिए ग्राहक को Archive करना। बकाया निपटने के बाद ही Archive करें; नए बिल रोकने के लिए Block करें।'],
      ['Expecting a Verified status after editing a GSTIN. Edit clears the old status, so press Verify again.', 'GSTIN बदलने के बाद Verified स्थिति की उम्मीद करना। बदलाव से पुरानी स्थिति हट जाती है, इसलिए फिर Verify दबाएँ।'],
    ],
    relatedPages: [
      { path: '/sales/new', labelKey: 'nav.newInvoice' },
      { path: '/sales/receipts', labelKey: 'nav.receipts' },
      { path: '/reports/customer-ledger', labelKey: 'nav.customerLedger' },
      { path: '/settings/price-lists', labelKey: 'nav.priceLists' },
    ],
    nextActions: [
      ['Fill state and GSTIN before the first GST bill, then verify it. Set a credit limit only if you want Complete to enforce it.', 'पहले GST बिल से पहले राज्य और GSTIN भरें और उसे Verify करें। लिमिट तभी लगाएँ जब Complete पर लागू करनी हो।'],
      ['Sort by Net Balance and open the top names in the Customer Snapshot to plan this week’s collection calls.', 'Net Balance से क्रम लगाएँ और इस हफ़्ते की वसूली के कॉल तय करने के लिए ऊपर के नाम Customer Snapshot में खोलें।'],
    ],
  }),

  helpPage('customer-360', {
    title: ['Customer Snapshot', 'ग्राहक स्नैपशॉट'],
    summary: [
      'One page per customer: what they buy, what they owe and how old it is, promises to pay, and a way to bill or edit them. Complaints, tickets, contracts and referrals show up here when your company uses those modules.',
      'हर ग्राहक का एक पेज: वे क्या खरीदते हैं, कितना बकाया है और कितना पुराना, भुगतान के वादे, और बिल बनाने या बदलने का रास्ता। कंपनी में शिकायत, टिकट, अनुबंध और रेफ़रल के मॉड्यूल चालू हों तो वे भी यहाँ दिखते हैं।',
    ],
    howItWorks: [
      [
        'Open it by clicking a customer name on the Customers screen. New bill starts an invoice for this customer, Money in opens receipts, and Repeat last invoice makes a new draft copy of their latest bill.',
        'Customers स्क्रीन पर ग्राहक के नाम पर क्लिक करके खोलें। New bill इसी ग्राहक का बिल शुरू करता है, Money in रसीदों के पेज पर ले जाता है, और Repeat last invoice उनके पिछले बिल की नई ड्राफ़्ट कॉपी बनाता है।',
      ],
      [
        'Edit customer opens the same form as the Customers screen, in place. When you save, this page and every invoice or receipt picker show the new details.',
        'Edit customer वही फ़ॉर्म खोलता है जो Customers स्क्रीन पर है, इसी पेज पर। सेव करने पर यह पेज और बिल व रसीद के पिकर नई जानकारी दिखाते हैं।',
      ],
      [
        'Dues shows what is outstanding with aging buckets (not yet due, 1–30, 31–60, 61–90, over 90 days) and any cheques counted as received but not cleared. Log a promise to pay records a date and amount; press Mark as resolved when the money arrives.',
        'Dues में बकाया और उम्र के खाने (देय नहीं, 1–30, 31–60, 61–90, 90 से ऊपर) और वे चेक दिखते हैं जो मिले माने गए पर क्लियर नहीं हुए। Log a promise to pay तारीख और रकम दर्ज करता है; पैसा आने पर Mark as resolved दबाएँ।',
      ],
      [
        'History lists who changed the customer and what: name, GSTIN, state, status, credit limit and days. Phone, email and PAN are shown masked.',
        'History बताती है कि ग्राहक में किसने क्या बदला: नाम, GSTIN, राज्य, स्थिति, क्रेडिट लिमिट और दिन। फ़ोन, ईमेल और PAN छिपे हुए दिखते हैं।',
      ],
    ],
    businessImpact: [
      [
        'Repeat last invoice creates a draft only. Stock, GST and the balance move when you Complete it. Logging a promise changes no money; it is a reminder for you and your team.',
        'Repeat last invoice सिर्फ़ ड्राफ़्ट बनाता है। स्टॉक, GST और बकाया Complete करने पर चलते हैं। वादा दर्ज करने से पैसे में कुछ नहीं बदलता; यह आपके और आपकी टीम के लिए याद दिलाने वाला नोट है।',
      ],
    ],
    keyRules: [
      [
        'Money, profit, aging and History need the financial-reports permission; without it you see the sales pattern and products only.',
        'पैसा, मुनाफ़ा, aging और History के लिए वित्तीय रिपोर्ट की अनुमति चाहिए; उसके बिना सिर्फ़ बिक्री का पैटर्न और उत्पाद दिखते हैं।',
      ],
      [
        'Edit needs permission to create sales. Credit limit and credit days are changed only by an owner or manager. If the form says someone else changed the customer, press Reload latest and keep what you typed.',
        'Edit के लिए बिल बनाने की अनुमति चाहिए। क्रेडिट लिमिट और क्रेडिट दिन सिर्फ़ ओनर या मैनेजर बदलते हैं। फ़ॉर्म कहे कि किसी और ने ग्राहक बदल दिया, तो Reload latest दबाएँ; आपका लिखा बना रहता है।',
      ],
    ],
    commonMistakes: [
      ['Treating a logged promise as a payment. Record the money on Money in; the promise is only a reminder.', 'दर्ज वादे को भुगतान मान लेना। पैसा Money in पर दर्ज करें; वादा सिर्फ़ याद दिलाने के लिए है।'],
      ['Editing the customer here while someone else edits it elsewhere, then closing the form. Use Reload latest instead of retyping.', 'यहाँ ग्राहक बदलते समय कोई और दूसरी जगह बदल रहा हो और फ़ॉर्म बंद कर देना। दोबारा लिखने के बजाय Reload latest इस्तेमाल करें।'],
    ],
    relatedPages: [
      { path: '/sales/customers', labelKey: 'nav.customers' },
      { path: '/sales/receipts', labelKey: 'nav.receipts' },
      { path: '/sales/new', labelKey: 'nav.newInvoice' },
      { path: '/reports/customer-ledger', labelKey: 'nav.customerLedger' },
    ],
    nextActions: [
      ['Check Dues first. For anything over 30 days, call and log a promise to pay with a date.', 'पहले Dues देखें। 30 दिन से ऊपर के हर बकाया पर कॉल करें और तारीख के साथ भुगतान का वादा दर्ज करें।'],
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
      [
        'Start from **Return goods** on the invoice (it opens this screen with the invoice filled in). For a price or discount change with no goods coming back, use a new credit note instead.',
        'बिल पर **Return goods** से शुरू करें (यह इसी स्क्रीन को बिल भरकर खोलता है)। माल वापस न आए और केवल दाम/छूट बदलनी हो तो नया क्रेडिट नोट बनाएँ।',
      ],
      [
        'Tick the lines coming back. For serial-tracked items, tap the serials that were sold; the quantity follows your picks and serials already returned are not offered.',
        'वापस आ रही पंक्तियाँ चुनें। सीरियल वाले सामान में बिके हुए सीरियल चुनें; मात्रा आपके चुनाव के अनुसार बनती है और लौट चुके सीरियल नहीं दिखते।',
      ],
      [
        'The total shown is exact: it is the credit note this return will issue, including your share of the invoice discount, charges and TCS.',
        'दिखाया गया कुल सटीक है: यह वही क्रेडिट नोट है जो यह रिटर्न जारी करेगा, इनवॉइस छूट, शुल्क और TCS के आपके हिस्से सहित।',
      ],
      [
        'Give each line its condition. Sellable items go back into stock; Damaged items are written off and do not. The **Quick reasons** buttons fill the reason for you, and "Defective / damaged" also marks the ticked lines as Damaged.',
        'हर पंक्ति की स्थिति चुनें। Sellable माल स्टॉक में लौटता है; Damaged माल बट्टे खाते जाता है, स्टॉक में नहीं। **Quick reasons** बटन कारण भर देते हैं, और "Defective / damaged" चुनी पंक्तियों को Damaged भी कर देता है।',
      ],
      [
        'Stock comes back into the same lot and at the same cost it was sold from, line by line, so a bill with the same item on two lines restores each one correctly. Returns made before this tracking existed are restored at product level.',
        'माल उसी लॉट में और उसी लागत पर लौटता है जहाँ से बिका था, पंक्ति-दर-पंक्ति; इसलिए एक ही सामान दो पंक्तियों में हो तो हर पंक्ति सही लौटती है। इस ट्रैकिंग से पहले के रिटर्न प्रोडक्ट स्तर पर लौटते हैं।',
      ],
      [
        'If GST Guard blocks the return, the message lists exactly what to fix. Only an Owner or Manager can override a block, and they must type a reason, which is kept on the record.',
        'GST Guard रिटर्न रोके तो संदेश में ठीक-ठीक लिखा होता है क्या सुधारना है। ब्लॉक को सिर्फ़ मालिक या मैनेजर ओवरराइड कर सकते हैं और कारण लिखना ज़रूरी है, जो रिकॉर्ड में रहता है।',
      ],
      [
        'Use the search box (invoice number or customer) and the From / To dates to find a return. The From date cannot be after the To date.',
        'रिटर्न खोजने के लिए सर्च बॉक्स (बिल नंबर या ग्राहक) और From / To तारीख़ें इस्तेमाल करें। From तारीख़ To के बाद की नहीं हो सकती।',
      ],
      [
        'Save keeps a draft you can edit, complete or delete later. Staff can save drafts; an Owner or Admin completes or cancels a return. Cancelling a completed return puts stock and serials back as they were and cancels its credit note.',
        'Save से ड्राफ्ट बनता है जिसे बाद में एडिट, Complete या हटा सकते हैं। स्टाफ ड्राफ्ट सहेज सकता है; रिटर्न Complete या रद्द मालिक/एडमिन करते हैं। पूर्ण रिटर्न रद्द करने पर स्टॉक और सीरियल पहले जैसे हो जाते हैं और उसका क्रेडिट नोट रद्द होता है।',
      ],
    ],
    businessImpact: [
      [
        'Stock in, customer balance down, GST worksheets pick up the return / linked credit note path. Reports must not keep treating a full return as a live sale.',
        'स्टॉक अंदर, ग्राहक बकाया कम, GST वर्कशीट रिटर्न/क्रेडिट नोट देखती हैं। पूरी वापसी को चालू बिक्री न गिनें।',
      ],
    ],
    keyRules: [
      ['Return against a completed sale only. Quantity cannot exceed what remains returnable on each line.', 'केवल पूर्ण बिक्री पर रिटर्न। मात्रा प्रत्येक लाइन की बची वापसी से ज्यादा नहीं।'],
      ['Units already credited by a standalone credit note cannot be returned as well; the message names that credit note.', 'जो इकाइयाँ अलग क्रेडिट नोट से पहले ही क्रेडिट हो चुकी हैं, वे दोबारा वापस नहीं हो सकतीं; संदेश में उस क्रेडिट नोट का नाम आता है।'],
      ['The return date cannot be earlier than the invoice date.', 'रिटर्न की तारीख़ बिल की तारीख़ से पहले की नहीं हो सकती।'],
      ['When every unit on the invoice has come back, the invoice shows Returned. Cancelling one of the returns reopens it as Completed.', 'बिल की सारी इकाइयाँ लौट आने पर बिल Returned दिखता है। किसी एक रिटर्न को रद्द करने पर वह फिर Completed हो जाता है।'],
      ['If the credit is more than the customer still owes, the excess is kept as unallocated customer advance (the screen warns you).', 'यदि क्रेडिट ग्राहक के बकाया से अधिक है तो अधिक राशि अनावंटित ग्राहक अग्रिम में रखी जाती है (स्क्रीन चेतावनी देती है)।'],
    ],
    commonMistakes: [
      ['Cancelling instead of returning after the customer already booked the invoice.', 'ग्राहक के बुक कर लेने के बाद रद्द करना — रिटर्न/क्रेडिट नोट लें।'],
      ['Marking damaged goods as Sellable, which puts them back on the shelf and into stock value.', 'खराब माल को Sellable चुनना — वह स्टॉक और स्टॉक मूल्य में वापस जुड़ जाता है।'],
      ['Making a return for a price or discount change. No goods come back, so use a credit note.', 'दाम या छूट बदलने के लिए रिटर्न बनाना। माल लौटता नहीं, इसलिए क्रेडिट नोट बनाएँ।'],
    ],
    relatedPages: [
      { path: '/sales/history', labelKey: 'nav.salesHistory' },
      { path: '/sales/credit-notes', labelKey: 'nav.creditNotes' },
      { path: '/purchases/returns', labelKey: 'nav.purchaseReturns' },
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
        'GST law caps output-tax credit notes at 30 November after the FY (or annual return, whichever is earlier). Bizboard refuses a credit note dated after 30 November, and after the annual return filing date once you record it on the GSTR-9 screen.',
        'GST में आउटपुट टैक्स क्रेडिट नोट की सीमा वित्तीय वर्ष के बाद 30 नवम्बर (या वार्षिक रिटर्न, जो पहले हो)। बिज़बोर्ड 30 नवम्बर के बाद की तारीख वाला क्रेडिट नोट मना करता है, और GSTR-9 स्क्रीन पर रिटर्न दाखिल करने की तारीख दर्ज करने के बाद उस तारीख के बाद का भी।',
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
      'Book an order in a few taps: pick a customer, tap products, type or step the quantity, then Save & next order. It saves a sales order (when your company has that turned on) or a draft bill, and the server sets the price and GST.',
      'कुछ टैप में ऑर्डर बुक करें: ग्राहक चुनें, उत्पाद टैप करें, मात्रा लिखें या बढ़ाएँ, फिर “सहेजें और अगला ऑर्डर”। यह सेल्स ऑर्डर (अगर आपकी कंपनी में चालू है) या ड्राफ्ट बिल सहेजता है; मूल्य और GST सर्वर तय करता है।',
    ],
    howItWorks: [
      ['Customer: tap one of your recent customers or search by name. Only customers you have billed or booked recently appear as chips, and blocked or inactive customers never do.', 'ग्राहक: अपने हाल के ग्राहकों में से टैप करें या नाम से खोजें। चिप में केवल वे ग्राहक दिखते हैं जिन्हें आपने हाल में बिल/बुक किया है; ब्लॉक या निष्क्रिय ग्राहक कभी नहीं दिखते।'],
      ['Items: tap a recent item chip (it shows how many are in stock) or search by name or SKU. Tapping an item already in the order adds one more instead of a second line.', 'आइटम: हाल के आइटम पर टैप करें (स्टॉक की संख्या दिखती है) या नाम/SKU से खोजें। ऑर्डर में पहले से मौजूद आइटम पर टैप करने से दूसरी लाइन नहीं बनती, एक और जुड़ता है।'],
      ['Quantity: type it in the box, or use − and +. Whole-unit goods (pieces, boxes) take whole numbers; goods sold by measure (kg, litre, metre) can take decimals. − stops at the minimum; the bin removes the line and Undo brings it back.', 'मात्रा: बॉक्स में लिखें, या − और + से बदलें। पूरी इकाई वाले माल (नग, डिब्बे) में पूर्ण संख्या; माप वाले माल (किलो, लीटर, मीटर) में दशमलव चल सकता है। − न्यूनतम पर रुक जाता है; कूड़ेदान लाइन हटाता है और “पूर्ववत करें” उसे लौटा देता है।'],
      ['Price and GST are decided by the server when you save: the customer’s price list and quantity slabs first, then the product’s selling price, with the product’s current GST rate. Nothing stored on your phone can change them. Until the price check finishes, the screen shows list prices and an estimated GST, marked as such.', 'मूल्य और GST सहेजते समय सर्वर तय करता है: पहले ग्राहक की प्राइस लिस्ट और मात्रा-स्लैब, फिर उत्पाद का बिक्री मूल्य, और उत्पाद की मौजूदा GST दर। फ़ोन में रखी कोई चीज़ इन्हें नहीं बदल सकती। मूल्य जाँच पूरी होने तक स्क्रीन सूची-मूल्य और अनुमानित GST (अनुमानित लिखा हुआ) दिखाती है।'],
      ['Create: if your company has order mode on, choose Sales order or Draft bill above the customer. Otherwise it always saves a draft bill. A customer with several saved addresses gets a Deliver to choice for orders.', 'बनाएँ: अगर आपकी कंपनी में ऑर्डर मोड चालू है, तो ग्राहक के ऊपर सेल्स ऑर्डर या ड्राफ्ट बिल चुनें; वरना हमेशा ड्राफ्ट बिल सहेजा जाता है। कई सहेजे पतों वाले ग्राहक के ऑर्डर में “डिलीवरी का पता” चुनने का विकल्प मिलता है।'],
      ['Save & next order saves, clears the sheet and shows a link to what you saved, ready for the next customer. Save & open saves and opens the document.', '“सहेजें और अगला ऑर्डर” सहेजता है, शीट साफ़ करता है और सहेजे गए दस्तावेज़ का लिंक दिखाता है। “सहेजें और खोलें” सहेजकर दस्तावेज़ खोल देता है।'],
      ['Your unsaved order is kept on this device and offered back when you return (Resume or Discard). It is removed once the order is saved. It is not an offline mode: saving needs a connection.', 'आपका अधूरा ऑर्डर इस डिवाइस पर रखा जाता है और लौटने पर वापस दिया जाता है (जारी रखें या हटाएँ)। ऑर्डर सहेजते ही यह हट जाता है। यह ऑफ़लाइन मोड नहीं है: सहेजने के लिए कनेक्शन चाहिए।'],
      ['Tapping Save twice, or retrying after a dropped connection, does not create a second document: the same request is recognised and answered once.', 'दो बार Save दबाने या कनेक्शन टूटने के बाद दोबारा कोशिश करने से दूसरा दस्तावेज़ नहीं बनता: वही अनुरोध पहचानकर एक ही बार निपटाया जाता है।'],
    ],
    businessImpact: [
      ['A draft bill moves no stock and posts no ledger until you Complete it. A confirmed sales order reserves stock and counts toward the customer’s credit exposure, but posts no ledger until it is billed.', 'ड्राफ्ट बिल Complete से पहले न स्टॉक हिलाता है, न लेजर में जाता है। पुष्ट सेल्स ऑर्डर स्टॉक आरक्षित करता है और ग्राहक की क्रेडिट सीमा में गिना जाता है, पर बिल बनने तक लेजर में नहीं जाता।'],
      ['Orders saved here appear under Sales Orders and can go on to a delivery challan, an invoice or a delivery route. Draft bills appear under Sales History.', 'यहाँ सहेजे ऑर्डर “सेल्स ऑर्डर” में दिखते हैं और डिलीवरी चालान, इनवॉइस या डिलीवरी रूट तक जा सकते हैं। ड्राफ्ट बिल “सेल्स हिस्ट्री” में दिखते हैं।'],
      ['An order with no delivery address picks up the customer’s default saved address (or their shipping, then billing address), so route stops are not blank. Payment terms default to the customer’s credit days.', 'डिलीवरी पते के बिना ऑर्डर ग्राहक का डिफ़ॉल्ट सहेजा पता (या शिपिंग, फिर बिलिंग पता) ले लेता है, ताकि रूट के स्टॉप खाली न रहें। भुगतान की शर्तें ग्राहक के क्रेडिट दिनों से तय होती हैं।'],
    ],
    keyRules: [
      ['Needs the create-sales permission. Blocked or inactive customers are refused when you save, confirm or complete, and an expired or suspended subscription stops saving.', 'सेल्स बनाने की अनुमति चाहिए। सहेजते, पुष्टि करते या पूरा करते समय ब्लॉक/निष्क्रिय ग्राहक अस्वीकार होते हैं, और सब्सक्रिप्शन समाप्त या निलंबित होने पर सहेजना रुक जाता है।'],
      ['Auto-confirm (if your company turned it on) confirms the order right after saving. If a credit-limit or margin check refuses it, the order stays a draft and says Needs approval; a manager confirms it from Sales Orders. If the connection drops after saving, it says confirming did not complete; open the order and confirm it.', 'ऑटो-कन्फर्म (अगर आपकी कंपनी ने चालू किया है) सहेजते ही ऑर्डर पक्का करता है। क्रेडिट-सीमा या मार्जिन जाँच मना कर दे तो ऑर्डर ड्राफ्ट रहता है और “मंजूरी चाहिए” लिखता है; मैनेजर इसे “सेल्स ऑर्डर” से पक्का करता है। सहेजने के बाद कनेक्शन टूटे तो “पुष्टि पूरी नहीं हुई” लिखा आता है; ऑर्डर खोलकर पक्का करें।'],
      ['Warnings are advice, not blocks: a line larger than the stock on hand, an order that would take the customer over their credit limit, or a customer on credit hold. The server still decides when you confirm or complete.', 'चेतावनियाँ सलाह हैं, रोक नहीं: स्टॉक से बड़ी लाइन, ग्राहक को क्रेडिट सीमा के पार ले जाने वाला ऑर्डर, या क्रेडिट होल्ड वाला ग्राहक। पुष्टि या पूरा करते समय निर्णय सर्वर का ही रहता है।'],
      ['Composition and unregistered companies save non-GST documents. A regular company with a GSTIN customer saves a GST invoice; without one, a retail invoice. A regular company with no GSTIN saved cannot complete a GST invoice, and the screen warns you.', 'कम्पोज़िशन और अपंजीकृत कंपनियाँ नॉन-GST दस्तावेज़ सहेजती हैं। GSTIN वाले ग्राहक के लिए नियमित कंपनी GST इनवॉइस, और उसके बिना रिटेल इनवॉइस सहेजती है। जिस नियमित कंपनी का GSTIN सहेजा नहीं है, वह GST इनवॉइस पूरा नहीं कर सकती; स्क्रीन आपको चेताती है।'],
      ['Order mode, auto-confirm and the server price check are switched on per company by your administrator. If you do not see the Sales order / Draft bill choice, your company is on draft bills.', 'ऑर्डर मोड, ऑटो-कन्फर्म और सर्वर मूल्य जाँच आपका एडमिन कंपनी-वार चालू करता है। अगर “सेल्स ऑर्डर / ड्राफ्ट बिल” का विकल्प नहीं दिखता, तो आपकी कंपनी ड्राफ्ट बिल पर है।'],
    ],
    commonMistakes: [
      ['Treating an “estimated” price or GST on screen as final. The saved document can differ until the price check finishes; open it to see the real figures.', 'स्क्रीन के “अनुमानित” मूल्य या GST को अंतिम मान लेना। मूल्य जाँच पूरी होने तक सहेजा दस्तावेज़ अलग हो सकता है; असली आँकड़े देखने के लिए उसे खोलें।'],
      ['Expecting a draft bill to reserve stock or show in Sales Orders. Only a confirmed sales order reserves stock; a draft bill appears in Sales History.', 'ड्राफ्ट बिल से स्टॉक आरक्षित होने या “सेल्स ऑर्डर” में दिखने की उम्मीद करना। स्टॉक केवल पुष्ट सेल्स ऑर्डर आरक्षित करता है; ड्राफ्ट बिल “सेल्स हिस्ट्री” में दिखता है।'],
      ['Leaving the page with an order half-built and relying on it being there later on another phone. The draft is kept only on the device and browser where you started it.', 'आधा बना ऑर्डर छोड़कर बाद में दूसरे फ़ोन पर उसके मिलने की उम्मीद करना। ड्राफ्ट केवल उसी डिवाइस और ब्राउज़र पर रहता है जहाँ आपने शुरू किया।'],
      ['Typing 2.5 for goods sold in pieces. Only measured units (kg, litre, metre…) accept decimals; the box goes back to the last good value.', 'नग में बिकने वाले माल के लिए 2.5 लिखना। केवल माप वाली इकाइयाँ (किलो, लीटर, मीटर…) दशमलव लेती हैं; बॉक्स पिछले सही मान पर लौट जाता है।'],
      ['Using this for a GST bill when the company GSTIN is missing, then hitting an error on Complete.', 'कंपनी का GSTIN न होने पर GST बिल बनाना और Complete पर एरर पाना।'],
    ],
    relatedPages: [
      { path: '/sales/orders', labelKey: 'nav.salesOrders' },
      { path: '/sales/new', labelKey: 'nav.newInvoice' },
      { path: '/sales/history', labelKey: 'nav.salesHistory' },
      { path: '/sales/customers', labelKey: 'nav.customers' },
      { path: '/sales/delivery-routes', labelKey: 'nav.deliveryRoutes' },
    ],
    nextActions: [
      ['Use Save & next order to book the next customer, or Save & open to review the document. Open the full editor for tax options, e-Way or multi-godown.', 'अगले ग्राहक के लिए “सहेजें और अगला ऑर्डर”, या दस्तावेज़ देखने के लिए “सहेजें और खोलें”। टैक्स/e-Way/मल्टी-गोदाम के लिए पूरा एडिटर खोलें।'],
      ['If an order says Needs approval, ask a manager to confirm it from Sales Orders, or open the customer to check their overdue balance and credit limit.', 'अगर ऑर्डर पर “मंजूरी चाहिए” है, तो मैनेजर से “सेल्स ऑर्डर” में पक्का करवाएँ, या ग्राहक खोलकर उसका बकाया और क्रेडिट सीमा देखें।'],
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
      ['Choose weekly, monthly, quarterly, half-yearly or annual runs. You can set an end date or a maximum number of runs; the schedule then pauses itself.', 'साप्ताहिक, मासिक, तिमाही, छमाही या वार्षिक रन चुनें। समाप्ति तिथि या अधिकतम रन तय कर सकते हैं; फिर अनुसूची खुद रुक जाती है।'],
      ['Pause a schedule and resume it later. On resume you pick the next run date, and missed periods are not created back-dated. **History** lists every document a schedule made.', 'अनुसूची रोकें और बाद में फिर शुरू करें। फिर शुरू करते समय अगली तारीख़ चुनते हैं, और छूटी अवधियों के दस्तावेज़ पिछली तारीख़ में नहीं बनते। **इतिहास** में अनुसूची के बनाए सभी दस्तावेज़ दिखते हैं।'],
    ],
    businessImpact: [
      ['Until you Complete, there is no stock movement, no receivable and no GST row.', 'Complete से पहले न स्टॉक, न बकाया, न GST पंक्ति।'],
      ['With Complete the invoice ticked, each invoice is finalized when it is made: stock is taken and the customer balance changes. If a check fails (credit limit, stock, GST, plan limit) it stays a draft, and the History and the owner notice say why. After a long gap only the first missed period is completed; the rest stay drafts to check.', 'चालान पूर्ण करें चुना हो तो हर इनवॉइस बनते ही अंतिम हो जाता है: स्टॉक कटता है और ग्राहक का बकाया बदलता है। कोई जाँच (क्रेडिट सीमा, स्टॉक, GST, प्लान सीमा) विफल हो तो वह ड्राफ्ट रहता है, और इतिहास तथा मालिक की सूचना में कारण दिखता है। लंबे अंतराल के बाद केवल पहली छूटी अवधि पूर्ण होती है; बाकी जाँचने के लिए ड्राफ्ट रहती हैं।'],
    ],
    keyRules: [
      ['This is a convenience for retainers-style billing, not a filing or auto-debit engine.', 'यह सुविधा है, फाइलिंग या ऑटो-डेबिट इंजन नहीं।'],
      ['Run now uses up the current period, so the scheduled run for that period is skipped. A schedule made from a contract is changed from the contract, and pauses when the contract ends.', 'अभी चलाएँ से चालू अवधि इस्तेमाल हो जाती है, इसलिए उसी अवधि का निर्धारित रन छोड़ दिया जाता है। अनुबंध से बनी अनुसूची अनुबंध से बदली जाती है, और अनुबंध खत्म होने पर रुक जाती है।'],
    ],
    commonMistakes: [
      ['Assuming the schedule already billed the customer.', 'शेड्यूल को ग्राहक पर बिल समझना।'],
      ['Deleting a schedule that has run. Pause it instead; its history is kept.', 'जो अनुसूची चल चुकी है उसे हटाना। इसके बजाय रोकें; उसका इतिहास बना रहता है।'],
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
      'Turns a photo, PDF or CSV/Excel file of a sales bill into a **draft** sales invoice for you to check. It never invents a GST rate or a quantity, and it never completes the bill: nothing moves in stock, GST or the ledger until you Save & Complete the draft.',
      'बिक्री बिल की फोटो, PDF या CSV/Excel फ़ाइल से **ड्राफ्ट** बिक्री इनवॉइस बनाता है, जिसे आप जाँचते हैं। यह GST दर या मात्रा कभी गढ़ता नहीं और बिल कभी पूरा नहीं करता: जब तक आप ड्राफ्ट Save & Complete नहीं करते, स्टॉक, GST या खाते में कुछ नहीं बदलता।',
    ],
    howItWorks: [
      ['**1. Upload.** Choose Photo / PDF (scanned by an AI service) or a CSV / Excel export (read directly, no AI). Drop a file, paste an image, or pick one. Optionally choose the customer first. For a photo you must tick that the image goes to an AI service.', '**1. अपलोड।** फोटो / PDF (AI सेवा से पढ़ा जाता है) या CSV / Excel निर्यात (सीधे पढ़ा जाता है, AI नहीं) चुनें। फ़ाइल छोड़ें, चित्र पेस्ट करें या चुनें। चाहें तो पहले ग्राहक चुनें। फोटो के लिए टिक करना होगा कि चित्र AI सेवा को जाएगा।'],
      ['**2. Check each row against the original bill.** The bill is shown beside the rows (a drawer on a phone). Point at a row and it is outlined on the picture. Rows marked red need fixing; amber rows were flagged by the arithmetic check. Add a row the scanner missed, or delete one that is not an item.', '**2. हर पंक्ति को मूल बिल से मिलाएँ।** बिल पंक्तियों के बगल में दिखता है (फोन पर नीचे से खुलने वाला पैनल)। किसी पंक्ति पर पॉइंटर रखें तो चित्र पर वह घिर जाती है। लाल पंक्तियाँ ठीक करनी हैं; पीली पंक्तियाँ गणित जाँच में चिह्नित हुईं। स्कैनर से छूटी पंक्ति जोड़ें, या जो आइटम नहीं है उसे हटाएँ।'],
      ['**3. Confirm who it is for.** The customer is matched only on an exact GSTIN or name. If nothing matches, the name on the bill is used to create a new customer. Pick another customer, or edit the name and GSTIN, if it is wrong.', '**3. पक्का करें कि किसके लिए है।** ग्राहक केवल सटीक GSTIN या नाम पर मिलाया जाता है। कुछ न मिले तो बिल का नाम लेकर नया ग्राहक बनता है। गलत हो तो दूसरा ग्राहक चुनें, या नाम और GSTIN बदलें।'],
      ['**4. Check the money.** Set whether prices include GST, and enter freight and any bill discount. The totals shown are what the draft will have; if you type the total printed on the bill, the difference is shown.', '**4. रकम जाँचें।** तय करें कि दरों में GST शामिल है या नहीं, और भाड़ा व बिल छूट भरें। दिखने वाले कुल वही हैं जो ड्राफ्ट में होंगे; बिल पर छपा कुल भरें तो अंतर दिखता है।'],
      ['**5. Check before creating, then create.** Check before creating lists every problem at once. Create the draft opens it for the final review. Your edits save by themselves, so you can leave and come back from Recent uploads.', '**5. बनाने से पहले जाँचें, फिर बनाएँ।** बनाने से पहले जाँचें सभी समस्याएँ एक साथ दिखाता है। ड्राफ्ट बनाएँ से वह अंतिम समीक्षा के लिए खुलता है। आपके बदलाव अपने आप सहेजे जाते हैं, इसलिए आप जाकर हाल के अपलोड से लौट सकते हैं।'],
      ['**6. Finish on the draft.** The draft shows the source bill number and a link to the original file. Review it, fix anything, then Save & Complete. Until then you can undo the whole import.', '**6. ड्राफ्ट पर पूरा करें।** ड्राफ्ट पर मूल बिल का नंबर और मूल फ़ाइल का लिंक दिखता है। उसे देखें, जो ठीक करना हो करें, फिर Save & Complete करें। तब तक पूरा आयात पूर्ववत किया जा सकता है।'],
    ],
    businessImpact: [
      ['Nothing posts until you Complete the draft: no invoice number, stock, GST, or outstanding.', 'ड्राफ्ट Complete होने तक कुछ पोस्ट नहीं होता: न इनवॉइस नंबर, न स्टॉक, न GST, न बकाया।'],
      ['The draft gets the customer\'s credit days as its payment terms (30 days if the customer has none) and the due date from the bill date.', 'ड्राफ्ट को ग्राहक के क्रेडिट दिन भुगतान शर्त के रूप में मिलते हैं (ग्राहक के न हों तो 30 दिन), और देय तिथि बिल की तारीख से बनती है।'],
      ['Items that are not in your catalogue are created as new products marked **needs review**. They have no cost and no stock yet, so completing the sale can be blocked on stock or show a zero margin until you receive stock and set a cost.', 'जो आइटम आपके कैटलॉग में नहीं हैं वे **समीक्षा चाहिए** चिह्न के साथ नए आइटम बनते हैं। उनकी लागत और स्टॉक अभी नहीं है, इसलिए बिक्री पूरी करना स्टॉक पर रुक सकता है या मार्जिन शून्य दिख सकता है, जब तक आप स्टॉक न लें और लागत न भरें।'],
      ['GST type (CGST+SGST or IGST) follows the customer\'s state. If the customer has no state yet, the draft may stop at Place of Supply when you Complete.', 'GST प्रकार (CGST+SGST या IGST) ग्राहक के राज्य से तय होता है। ग्राहक का राज्य न हो तो Complete पर ड्राफ्ट Place of Supply पर रुक सकता है।'],
    ],
    keyRules: [
      ['A row with a problem is never dropped silently. If an included row is wrong (blank GST rate, bad HSN, no quantity), creating the draft is refused and every bad row is listed.', 'समस्या वाली पंक्ति चुपचाप नहीं छूटती। शामिल पंक्ति गलत हो (GST दर खाली, गलत HSN, मात्रा नहीं) तो ड्राफ्ट बनाना मना होता है और हर गलत पंक्ति सूचीबद्ध होती है।'],
      ['HSN must be 2, 4, 6 or 8 digits; the GST rate must be a valid slab (0, 0.25, 3, 5, 12, 18, 28).', 'HSN 2, 4, 6 या 8 अंकों का हो; GST दर मान्य स्लैब (0, 0.25, 3, 5, 12, 18, 28) में हो।'],
      ['The price you review is the price on the draft, even when it is below the customer\'s price list. Only an Owner or Manager may keep a lower price; the line is marked, and the draft says how many lines are below the list.', 'आपका जाँचा हुआ भाव ही ड्राफ्ट का भाव है, चाहे वह ग्राहक की मूल्य सूची से कम हो। कम भाव केवल Owner या Manager रख सकते हैं; पंक्ति चिह्नित होती है और ड्राफ्ट बताता है कि कितनी पंक्तियाँ सूची से कम हैं।'],
      ['Customers are never matched by a similar name: only exactly. Inactive, blocked and the walk-in customer are never picked automatically.', 'ग्राहक मिलते-जुलते नाम से कभी नहीं मिलाए जाते: केवल सटीक। निष्क्रिय, ब्लॉक और वॉक-इन ग्राहक अपने आप कभी नहीं चुने जाते।'],
      ['The same bill number for the same customer on the same date asks you to confirm it is not a duplicate.', 'उसी ग्राहक का उसी तारीख का वही बिल नंबर दोबारा आए तो पुष्टि माँगी जाती है कि यह प्रति नहीं है।'],
      ['If the scan is low-confidence, tick that you reviewed every line before the draft can be created.', 'स्कैन का भरोसा कम हो तो ड्राफ्ट बनाने से पहले टिक करें कि आपने हर पंक्ति जाँच ली।'],
      ['Uploading needs the Import permission and the right to create sales invoices.', 'अपलोड के लिए Import अनुमति और बिक्री इनवॉइस बनाने का अधिकार दोनों चाहिए।'],
    ],
    commonMistakes: [
      ['Completing the draft without comparing each row to the bill. The scan can misread names, quantities and rates.', 'हर पंक्ति को बिल से मिलाए बिना ड्राफ्ट Complete करना। स्कैन नाम, मात्रा और दर गलत पढ़ सकता है।'],
      ['Ignoring the new-products notice, then finding zero-cost items or stock-blocked sales later. Pick the right existing item on a row instead of creating a duplicate.', 'नए आइटम की सूचना अनदेखी करना, और बाद में शून्य लागत या स्टॉक पर रुकी बिक्री मिलना। डुप्लिकेट बनाने के बजाय पंक्ति पर सही मौजूदा आइटम चुनें।'],
      ['Leaving "prices include GST" wrong, so tax is added on top of a price that already had it. Compare the draft total with the printed total.', '"दरों में GST शामिल" गलत छोड़ना, जिससे पहले से GST वाले भाव पर फिर GST जुड़ जाता है। ड्राफ्ट का कुल छपे कुल से मिलाएँ।'],
      ['Uploading a purchase bill here. If the buyer GSTIN is yours the page warns and offers to switch it to a purchase bill.', 'यहाँ खरीद बिल अपलोड करना। खरीदार GSTIN आपका हो तो पेज चेतावनी देता है और उसे खरीद बिल में बदलने का विकल्प देता है।'],
      ['Closing the tab with unsaved edits. Edits autosave every moment or two, but wait for the "saved" note before closing.', 'बिना सहेजे बदलावों के साथ टैब बंद करना। बदलाव कुछ क्षणों में अपने आप सहेजे जाते हैं, पर बंद करने से पहले "सहेजा गया" संदेश देखें।'],
    ],
    relatedPages: [
      { path: '/sales/history', labelKey: 'nav.salesHistory' },
      { path: '/sales/new', labelKey: 'nav.newInvoice' },
      { path: '/inventory/products?needsReview=1', labelKey: 'products.needsReviewFilter' },
    ],
    nextActions: [
      ['Open the draft, check lines and customer, then Save & Complete.', 'ड्राफ्ट खोलें, पंक्तियाँ और ग्राहक जाँचें, फिर Save & Complete करें।'],
      ['Open the products marked needs review, set cost and stock, then mark them reviewed.', 'समीक्षा चाहिए वाले आइटम खोलें, लागत और स्टॉक भरें, फिर उन्हें समीक्षित चिह्नित करें।'],
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
