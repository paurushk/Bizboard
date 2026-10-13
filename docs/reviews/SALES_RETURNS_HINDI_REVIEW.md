# Hindi strings added for Sales and Purchase Returns: review sheet

The Hindi below was written by an AI assistant, not a native reviewer. Please read each line against the English, correct anything that sounds wrong, and tick it off. Placeholders in braces (for example `{count}`) must stay exactly as written.

Reviewer: ____________   Date: ____________

| Done | Key | English | Hindi |
|---|---|---|---|
| [ ] | `billing.serialPicked` | {count} of {max} serial(s) picked | {max} में से {count} सीरियल चुने गए |
| [ ] | `phase1.cancelReturn` | Cancel return | वापसी रद्द करें |
| [ ] | `phase1.editSalesReturnDraft` | Edit sales return draft | बिक्री वापसी ड्राफ्ट संपादित करें |
| [ ] | `phase1.returnLinesUnits` | {lines} line(s) · {units} unit(s) | {lines} पंक्ति · {units} इकाई |
| [ ] | `phase1.returnTaxable` | Taxable | कर योग्य |
| [ ] | `phase1.returnGst` | GST | जीएसटी |
| [ ] | `phase1.returnCreditNoteTotal` | Credit note total | क्रेडिट नोट कुल |
| [ ] | `phase1.returnPreviewNote` | Exact figures: includes your share of invoice discount, charges and TCS. | सटीक आँकड़े: इनवॉइस छूट, शुल्क और टीसीएस का आपका हिस्सा शामिल है। |
| [ ] | `phase1.returnPreviewLoading` | Calculating credit note… | क्रेडिट नोट की गणना हो रही है… |
| [ ] | `phase1.returnPreviewUnavailable` | Total preview unavailable: {message} | कुल का पूर्वावलोकन उपलब्ध नहीं: {message} |
| [ ] | `phase1.returnDiscountShare` | Invoice discount share | इनवॉइस छूट का हिस्सा |
| [ ] | `phase1.returnChargesShare` | Charges share | शुल्क का हिस्सा |
| [ ] | `phase1.returnTcsShare` | TCS share | टीसीएस का हिस्सा |
| [ ] | `phase1.filterFrom` | From date | आरंभ तिथि |
| [ ] | `phase1.filterTo` | To date | अंतिम तिथि |
| [ ] | `phase1.clearFilters` | Clear filters | फ़िल्टर हटाएँ |
| [ ] | `phase1.dateRangeInvalid` | “From” date cannot be after “To” date. | “आरंभ” तिथि “अंतिम” तिथि के बाद नहीं हो सकती। |
| [ ] | `phase1.detailDiscountPct` | Disc % | छूट % |
| [ ] | `phase1.detailGstPct` | GST % | जीएसटी % |
| [ ] | `phase1.detailTaxable` | Taxable | कर योग्य |
| [ ] | `phase1.detailRoundOff` | Round off | राउंड ऑफ |
| [ ] | `phase1.reasonPresetDefective` | Defective / damaged | दोषपूर्ण / क्षतिग्रस्त |
| [ ] | `phase1.reasonPresetWrongItem` | Wrong item | गलत सामान |
| [ ] | `phase1.reasonPresetChangedMind` | Customer changed mind | ग्राहक ने मन बदल लिया |
| [ ] | `phase1.reasonPresetQuality` | Quality / expiry | गुणवत्ता / एक्सपायरी |
| [ ] | `phase1.reasonPresetsLabel` | Quick reasons | त्वरित कारण |
| [ ] | `phase1.reasonPresetDefectiveHint` | Marks the selected lines as Damaged | चुनी हुई पंक्तियों को क्षतिग्रस्त चिह्नित करता है |
| [ ] | `phase1.paidInvoiceReturnNotice` | This credit is more than the amount still owed on the invoice. The excess will be kept as unallocated customer advance. | यह क्रेडिट इनवॉइस पर अभी बकाया राशि से अधिक है। अधिक राशि ग्राहक के अनावंटित अग्रिम (advance) के रूप में रखी जाएगी। |
| [ ] | `phase1.purchaseReturnDraftSaved` | Purchase return draft saved | खरीद वापसी ड्राफ्ट सहेजा गया |
| [ ] | `phase1.purchaseReturnCancelled` | Purchase return cancelled | खरीद वापसी रद्द की गई |
| [ ] | `phase1.purchaseReturnDeleted` | Purchase return draft deleted | खरीद वापसी ड्राफ्ट हटाया गया |
| [ ] | `phase1.cancelPurchaseReturnConfirm` | Cancel this completed purchase return? This will put the stock back, revert serial numbers, and cancel the linked purchase credit note. | क्या आप इस पूर्ण खरीद वापसी को रद्द करना चाहते हैं? इससे स्टॉक वापस जुड़ेगा, सीरियल नंबर पहले की स्थिति में लौटेंगे और जुड़ा हुआ खरीद क्रेडिट नोट रद्द होगा। |
| [ ] | `phase1.deletePurchaseReturnDraftConfirm` | Delete this draft purchase return? | क्या आप इस ड्राफ्ट खरीद वापसी को हटाना चाहते हैं? |
| [ ] | `phase1.editPurchaseReturnDraft` | Edit purchase return draft | खरीद वापसी ड्राफ्ट संपादित करें |
| [ ] | `phase1.sourcePurchase` | Source purchase | स्रोत खरीद |
| [ ] | `phase1.autoPurchaseCreditNoteNotice` | Completing this return takes the items out of stock and automatically issues a purchase credit note. | इस वापसी को पूर्ण करने पर सामान स्टॉक से बाहर होगा और अपने आप खरीद क्रेडिट नोट जारी होगा। |

## Longer help text

The help page additions are in `web/src/contextHelp/catalog/sales.ts` (page `sales-returns`) and `web/src/contextHelp/catalog/purchases.ts` (page `purchase-returns`); the FAQ is in `web/src/pages/help/faqContent.tsx` (`sales-return`). Each English paragraph sits next to its Hindi in the same array, so review them in place.

After review, edit `web/src/i18n/hi.ts` and those files directly, then run `npx vitest run src/i18n src/contextHelp src/pages/help`.
