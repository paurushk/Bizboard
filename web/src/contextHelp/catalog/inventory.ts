import { helpPage } from '../buildPage';
import type { ContextHelpPage } from '../types';

export const INVENTORY_HELP: ContextHelpPage[] = [
  helpPage('products', {
    title: ['Products', 'प्रोडक्ट'],
    summary: [
      'Item master: SKU, tax, units, batch/serial flags, active status. Saving a product does not move stock. Opening stock and bills do.',
      'आइटम मास्टर: SKU, टैक्स, यूनिट, बैच/सीरियल, सक्रिय स्थिति। प्रोडक्ट सेव से स्टॉक नहीं चलता। ओपनिंग और बिल चलते हैं।',
    ],
    howItWorks: [
      [
        'Stock is stored in the **base** unit. An optional alternate unit converts with a rate > 0 before stock updates.',
        'स्टॉक **बेस** यूनिट में रहता है। वैकल्पिक यूनिट दर > 0 से बदलकर स्टॉक अपडेट होता है।',
      ],
      [
        'Track batch and track serial are mutually exclusive. After the first stock movement, the base unit is locked.',
        'बैच और सीरियल एक साथ नहीं। पहली स्टॉक मूवमेंट के बाद बेस यूनिट लॉक।',
      ],
    ],
    businessImpact: [
      [
        'Inactive products cannot go on a new invoice. Wrong HSN/rate here flows into every later GST bill.',
        'निष्क्रिय आइटम नए बिल पर नहीं। गलत HSN/दर हर GST बिल में जाती है।',
      ],
    ],
    keyRules: [
      [
        'The Products list “available” is company-wide across godowns. A bill draws from **one** godown only.',
        'प्रोडक्ट लिस्ट का “उपलब्ध” सभी गोदामों का योग है। बिल **एक** गोदाम से काटता है।',
      ],
    ],
    commonMistakes: [
      ['Selling an inactive SKU or changing base unit after movements exist.', 'निष्क्रिय SKU बेचना या मूवमेंट बाद बेस यूनिट बदलना।'],
    ],
    relatedPages: [
      { path: '/inventory/stock', labelKey: 'nav.currentStock' },
      { path: '/settings/units', labelKey: 'nav.units' },
      { path: '/sales/new', labelKey: 'nav.newInvoice' },
    ],
    nextActions: [
      ['Set HSN, GST rate and godown opening stock before the first bill.', 'पहले बिल से पहले HSN, GST दर और गोदाम ओपनिंग सेट करें।'],
    ],
  }),

  helpPage('current-stock', {
    title: ['Current stock', 'वर्तमान स्टॉक'],
    summary: [
      'On hand is physical quantity in a godown. Reserved is committed to open documents. Available = on hand − reserved — that is what billing and low-stock use.',
      'हाथ में = गोदाम की भौतिक मात्रा। रिज़र्व = खुले दस्तावेज़ों पर। उपलब्ध = हाथ में − रिज़र्व — बिलिंग और लो-स्टॉक यही देखते हैं।',
    ],
    howItWorks: [
      [
        'Filter by godown. Company-wide totals can look fine while one godown is empty.',
        'गोदाम से फ़िल्टर करें। कुल ठीक दिखे और एक गोदाम खाली हो सकता है।',
      ],
    ],
    businessImpact: [
      [
        'Sales Complete reduces on hand here. Purchase Complete increases it. Transfers move between godowns without a sale.',
        'बिक्री Complete हाथ में घटाता है, खरीद बढ़ाती है। ट्रांसफर गोदामों के बीच है, बिक्री नहीं।',
      ],
    ],
    keyRules: [
      ['This page is a reader. Adjustments, counts, transfers and bills are the writers.', 'यह पेज पढ़ता है। एडजस्टमेंट, काउंट, ट्रांसफर और बिल लिखते हैं।'],
    ],
    commonMistakes: [
      ['Billing from the default godown while stock sits in another. Change godown on the bill or transfer first.', 'स्टॉक दूसरे गोदाम में हो और डिफ़ॉल्ट से बिल काटना। बिल का गोदाम बदलें या पहले ट्रांसफर करें।'],
    ],
    relatedPages: [
      { path: '/inventory/transfers', labelKey: 'nav.stockTransfers' },
      { path: '/inventory/adjustments', labelKey: 'nav.stockAdjustment' },
      { path: '/inventory/warehouses', labelKey: 'nav.warehouses' },
    ],
    nextActions: [
      ['If a bill failed insufficient stock, read the godown named in the error, then transfer or change the bill godown.', 'स्टॉक कम हो तो एरर वाला गोदाम देखें, ट्रांसफर करें या बिल का गोदाम बदलें।'],
    ],
  }),

  helpPage('stock-adjustment', {
    title: ['Stock adjustment', 'स्टॉक समायोजन'],
    summary: [
      'Correct on-hand quantity (damage, found stock, opening correction). This is not a sale or purchase and should not replace a bill.',
      'हाथ की मात्रा ठीक करें (क्षति, मिला स्टॉक, ओपनिंग सुधार)। यह बिक्री/खरीद नहीं और बिल की जगह नहीं।',
    ],
    howItWorks: [
      ['Pick godown, item, quantity direction and reason, then post. Batch/serial items need those identifiers.', 'गोदाम, आइटम, दिशा और कारण चुनकर पोस्ट करें। बैच/सीरियल पर वे पहचान चाहिए।'],
    ],
    businessImpact: [
      [
        'On-hand changes immediately. Valuation and low-stock follow. GST output/ITC does not come from an adjustment.',
        'हाथ में तुरंत बदलता है। वैल्यूएशन/लो-स्टॉक चलते हैं। GST आउटपुट/ITC एडजस्टमेंट से नहीं आता।',
      ],
    ],
    keyRules: [
      ['Closed accounting period can block posting. Prefer a purchase/return when goods actually moved with a party.', 'बंद खाता पीरियड पोस्ट रोक सकता है। पार्टी के साथ माल चला हो तो खरीद/रिटर्न बेहतर।'],
    ],
    commonMistakes: [
      ['Using adjustment to hide a missing purchase bill, leaving ITC and payables wrong.', 'खरीद बिल छुपाने के लिए एडजस्टमेंट — ITC और देनदारी गलत रहती है।'],
    ],
    relatedPages: [
      { path: '/inventory/stock', labelKey: 'nav.currentStock' },
      { path: '/purchases/new', labelKey: 'nav.newPurchase' },
    ],
    nextActions: [
      ['Post only the difference you counted. Then re-check current stock.', 'जो फर्क गिना वही पोस्ट करें। फिर वर्तमान स्टॉक देखें।'],
    ],
  }),

  helpPage('stock-transfers', {
    title: ['Stock transfers', 'स्टॉक ट्रांसफर'],
    summary: [
      'Move quantity from one godown to another. No sale, no GST invoice, no party balance.',
      'एक गोदाम से दूसरे में मात्रा। न बिक्री, न GST बिल, न पार्टी बैलेंस।',
    ],
    howItWorks: [
      ['Source must have available quantity. Complete the transfer to post both sides.', 'स्रोत पर उपलब्ध मात्रा चाहिए। दोनों ओर पोस्ट के लिए ट्रांसफर Complete करें।'],
    ],
    businessImpact: [
      ['After Complete, billing from the destination godown can succeed; the source godown can no longer sell that qty.', 'Complete बाद गंतव्य गोदाम से बिल चल सकता है; स्रोत से वह मात्रा नहीं बिकेगी।'],
    ],
    keyRules: [
      ['Godown is not a GSTIN. Moving stock does not change which GSTIN files the bill.', 'गोदाम GSTIN नहीं। स्टॉक खिसकाने से फाइलिंग GSTIN नहीं बदलता।'],
    ],
    commonMistakes: [
      ['Transferring after already Completing a bill from the empty godown.', 'खाली गोदाम से बिल Complete करने के बाद ट्रांसफर।'],
    ],
    relatedPages: [
      { path: '/inventory/stock', labelKey: 'nav.currentStock' },
      { path: '/inventory/warehouses', labelKey: 'nav.warehouses' },
    ],
    nextActions: [
      ['Transfer first, then Complete the sales bill from the godown that now holds stock.', 'पहले ट्रांसफर, फिर जिस गोदाम में स्टॉक है उससे बिल Complete करें।'],
    ],
  }),

  helpPage('warehouses', {
    title: ['Godowns', 'गोदाम'],
    summary: [
      'Stock locations. Each bill uses one godown. This is not a GST branch — extra GSTINs live under Settings → GST.',
      'स्टॉक स्थान। हर बिल एक गोदाम इस्तेमाल करता है। यह GST शाखा नहीं — अतिरिक्त GSTIN सेटिंग → GST में हैं।',
    ],
    howItWorks: [
      ['Create named godowns, then pick them on invoices, purchases and transfers.', 'गोदाम बनाएँ, फिर बिल/खरीद/ट्रांसफर पर चुनें।'],
    ],
    businessImpact: [
      ['Wrong default godown is the usual reason “stock shows but Complete fails”.', 'गलत डिफ़ॉल्ट गोदाम ही अक्सर “स्टॉक दिखे पर Complete फेल” की वजह है।'],
    ],
    keyRules: [
      ['Deactivating a godown does not move its stock; transfer first.', 'गोदाम निष्क्रिय करने से स्टॉक नहीं खिसकता; पहले ट्रांसफर करें।'],
    ],
    commonMistakes: [
      ['Creating a godown per GSTIN expecting separate invoice series. Series follow GSTIN, not godown.', 'हर GSTIN पर गोदाम बनाकर सीरीज़ अलग समझने — सीरीज़ GSTIN से है।'],
    ],
    relatedPages: [
      { path: '/inventory/stock', labelKey: 'nav.currentStock' },
      { path: '/settings/gst', labelKey: 'nav.gst' },
    ],
    nextActions: [
      ['Set a sensible default godown for counter sales.', 'काउंटर बिक्री के लिए सही डिफ़ॉल्ट गोदाम सेट करें।'],
    ],
  }),

  helpPage('stock-counts', {
    title: ['Stock counts', 'स्टॉक गिनती'],
    summary: [
      'Physical count session. Posting the count writes on-hand to what you counted (with the session’s rules). It is not a GST document.',
      'भौतिक गिनती। पोस्ट करने पर हाथ की मात्रा गिनी गई मात्रा बनती है। यह GST दस्तावेज़ नहीं।',
    ],
    howItWorks: [
      ['Open a session, enter counted qty per item/godown, then post. Batch/serial items need those codes.', 'सेशन खोलें, मात्रा भरें, पोस्ट करें। बैच/सीरियल कोड चाहिए।'],
    ],
    businessImpact: [
      ['On-hand, valuation and later bills all follow the posted count. Large swings should be explained (theft, missed purchase).', 'हाथ, वैल्यूएशन और बाद के बिल गिनती के बाद। बड़े फर्क की वजह लिखें।'],
    ],
    keyRules: [
      ['Do not leave a count in preview and assume stock already moved.', 'प्रीव्यू गिनती को स्टॉक न समझें।'],
    ],
    commonMistakes: [
      ['Counting in one godown while billing continues in another without a freeze process.', 'एक गोदाम गिनते हुए दूसरे से बिल चलाना बिना फ्रीज।'],
    ],
    relatedPages: [
      { path: '/inventory/stock', labelKey: 'nav.currentStock' },
      { path: '/inventory/adjustments', labelKey: 'nav.stockAdjustment' },
    ],
    nextActions: [
      ['Post the session, then spot-check current stock.', 'सेशन पोस्ट करें, फिर स्टॉक जाँचें।'],
    ],
  }),

  helpPage('serials', {
    title: ['Serial numbers', 'सीरियल नंबर'],
    summary: [
      'Tracks individual units. An item cannot be both batch-tracked and serial-tracked. Selling a serial marks it sold.',
      'हर इकाई की ट्रैकिंग। आइटम बैच और सीरियल दोनों नहीं। सीरियल बेचने पर sold होता है।',
    ],
    howItWorks: [
      ['Issue on Complete of a sale; receive on purchase Complete. This list shows availability.', 'बिक्री Complete पर इश्यू, खरीद Complete पर रिसीव। यह सूची उपलब्धता दिखाती है।'],
    ],
    businessImpact: [
      ['Wrong serial on a bill leaves the physical unit and the system out of sync.', 'गलत सीरियल से वास्तविक इकाई और सिस्टम अलग हो जाते हैं।'],
    ],
    keyRules: [
      ['You cannot sell a serial that is not AVAILABLE.', 'जो AVAILABLE नहीं उसे नहीं बेच सकते।'],
    ],
    commonMistakes: [
      ['Typing a new serial on a sale instead of picking one received on a purchase.', 'खरीद पर आए सीरियल की जगह बिक्री पर नया टाइप करना।'],
    ],
    relatedPages: [
      { path: '/inventory/products', labelKey: 'nav.products' },
      { path: '/sales/new', labelKey: 'nav.newInvoice' },
    ],
    nextActions: [
      ['Receive serials on the purchase, then pick them on the sale.', 'खरीद पर सीरियल लें, बिक्री पर वही चुनें।'],
    ],
  }),

  helpPage('expiry-alerts', {
    title: ['Expiry alerts', 'एक्सपायरी अलर्ट'],
    summary: [
      'Batch lots nearing expiry. This is a reader of batch stock, not a write-off. Use adjustment or a sale/return to change quantity.',
      'एक्सपायरी के पास बैच। यह पढ़ता है, राइट-ऑफ नहीं। मात्रा बदलने के लिए एडजस्टमेंट या बिक्री/रिटर्न।',
    ],
    howItWorks: [
      ['FEFO reservation on orders prefers nearest expiry first.', 'ऑर्डर पर FEFO रिज़र्व पहले नज़दीक एक्सपायरी लेता है।'],
    ],
    businessImpact: [
      ['Ignoring this list can lead to selling expired lots if the bill allows a later batch.', 'नज़रअंदाज़ करने पर बाद का बैच बिल पर जा सकता है।'],
    ],
    keyRules: [
      ['Alerts do not block Complete by themselves unless a batch rule on the line does.', 'अलर्ट अकेले Complete नहीं रोकते जब तक लाइन का बैच नियम न हो।'],
    ],
    commonMistakes: [
      ['Writing off expiry only in this screen — post an adjustment to move stock.', 'यहीं राइट-ऑफ समझना — स्टॉक के लिए एडजस्टमेंट पोस्ट करें।'],
    ],
    relatedPages: [
      { path: '/inventory/stock', labelKey: 'nav.currentStock' },
      { path: '/inventory/adjustments', labelKey: 'nav.stockAdjustment' },
    ],
    nextActions: [
      ['Sell, return to supplier, or adjust expired lots, then refresh this list.', 'एक्सपायर्ड लॉट बेचें, सप्लायर लौटाएँ या एडजस्ट करें।'],
    ],
  }),

  helpPage('low-stock', {
    title: ['Low stock', 'कम स्टॉक'],
    summary: [
      'Items at or below reorder using **available** (on hand − reserved), not raw on-hand.',
      'रीऑर्डर पर या नीचे आइटम — **उपलब्ध** (हाथ में − रिज़र्व), सिर्फ हाथ में नहीं।',
    ],
    howItWorks: [
      ['Company-wide or per view as implemented on the page. It does not place a purchase order by itself.', 'पेज के अनुसार कुल/दृश्य। यह खुद खरीद ऑर्डर नहीं बनाता।'],
    ],
    businessImpact: [
      ['Reserved sales orders can make an item look low even when on-hand looks fine.', 'रिज़र्व ऑर्डर से आइटम कम दिख सकता है जबकि हाथ में ठीक हो।'],
    ],
    keyRules: [
      ['This is a reader. Create a purchase or transfer to fix it.', 'यह पढ़ता है। ठीक करने के लिए खरीद या ट्रांसफर।'],
    ],
    commonMistakes: [
      ['Raising a PO without checking which godown is actually low.', 'कौन सा गोदाम कम है देखे बिना PO।'],
    ],
    relatedPages: [
      { path: '/purchases/new', labelKey: 'nav.newPurchase' },
      { path: '/inventory/stock', labelKey: 'nav.currentStock' },
    ],
    nextActions: [
      ['Open current stock by godown, then purchase or transfer.', 'गोदामवार स्टॉक खोलें, फिर खरीद या ट्रांसफर।'],
    ],
  }),

  helpPage('label-print', {
    title: ['Print labels', 'लेबल प्रिंट'],
    summary: [
      'Prints shelf or barcode labels from products. Printing does not change stock or prices.',
      'प्रोडक्ट से शेल्फ/बारकोड लेबल। प्रिंट से स्टॉक या कीमत नहीं बदलती।',
    ],
    howItWorks: [
      ['Select items and print. Use the barcode on POS or the invoice scanner (F2 on the invoice editor).', 'आइटम चुनकर प्रिंट। POS या इनवॉइस स्कैनर (F2) पर बारकोड।'],
    ],
    businessImpact: [
      ['Wrong SKU on a label causes the next scan to bill the wrong item.', 'गलत SKU अगली स्कैन पर गलत आइटम बिल करेगा।'],
    ],
    keyRules: [
      ['Labels are not statutory invoices.', 'लेबल कानूनी इनवॉइस नहीं।'],
    ],
    commonMistakes: [
      ['Printing before the SKU/barcode on the product is saved.', 'प्रोडक्ट पर SKU/बारकोड सेव से पहले प्रिंट।'],
    ],
    relatedPages: [
      { path: '/inventory/products', labelKey: 'nav.products' },
      { path: '/pos', labelKey: 'nav.pos' },
    ],
    nextActions: [
      ['Save the product, print labels, then scan on POS or New Invoice.', 'प्रोडक्ट सेव करें, लेबल प्रिंट करें, POS या नए बिल पर स्कैन करें।'],
    ],
  }),

  helpPage('pos', {
    title: ['Point of Sale', 'पॉइंट ऑफ सेल'],
    summary: [
      'Counter billing. Completing a POS sale is still a sales Complete: stock, customer (or walk-in), GST type and payments follow the same books as New Invoice.',
      'काउंटर बिलिंग। POS Complete भी बिक्री Complete है: स्टॉक, ग्राहक/वॉक-इन, GST और भुगतान नए इनवॉइस जैसी किताबों में जाते हैं।',
    ],
    howItWorks: [
      [
        'Scan or search items, take payment, Complete. UPI QR (if configured) does not by itself mark the bill paid — record the mode or wait for a link capture.',
        'स्कैन/खोज, भुगतान, Complete। UPI QR खुद Paid नहीं करता — मोड दर्ज करें या लिंक कैप्चर का इंतज़ार।',
      ],
    ],
    businessImpact: [
      ['Each completed sale hits the same stock, GST, receivables and reports as a back-office invoice.', 'हर पूर्ण बिक्री बैक-ऑफिस इनवॉइस जैसे स्टॉक, GST, प्राप्य और रिपोर्ट में जाती है।'],
    ],
    keyRules: [
      ['Need POS enabled and POS permission. Offline outbox (if used) must sync before you assume the server has the bill.', 'POS चालू और अनुमति चाहिए। ऑफ़लाइन आउटबॉक्स सिंक हुए बिना सर्वर पर बिल न मानें।'],
    ],
    commonMistakes: [
      ['Closing the drawer without Completing, leaving a draft with no stock movement.', 'Complete बिना दराज बंद — ड्राफ्ट पर स्टॉक नहीं कटता।'],
    ],
    relatedPages: [
      { path: '/sales/history', labelKey: 'nav.salesHistory' },
      { path: '/sales/receipts', labelKey: 'nav.receipts' },
      { path: '/offline-outbox', labelKey: 'nav.offlineOutbox' },
    ],
    nextActions: [
      ['Complete the sale, then verify it in sales history if the customer needs a GST invoice copy.', 'बिक्री Complete करें; GST कॉपी चाहिए तो बिक्री इतिहास में देखें।'],
    ],
  }),
];
