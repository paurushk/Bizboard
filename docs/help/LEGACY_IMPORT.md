# Bring your data from Busy, Vyapar or Marg

A one-time import of parties (customers and suppliers with their opening balances), items (with
HSN, GST rate, prices and opening stock) from Busy, Vyapar or Marg ERP. It works like the Tally
import: you upload, check the preview, then confirm. Nothing is posted until you confirm, and
importing the same file again matches the parties already there instead of adding them twice.

The import is switched on per company by Bizboard support during your move. Ask from
**Help → Contact support** ("Switch on import from my old software").

Export **parties** and **items** as separate Excel or CSV files and upload them one at a time.

## Busy

- Parties: *Display → Account Books → Account List*, export to Excel with columns
  **Name, Group, Mobile No., GSTIN, State, Op. Bal., Dr/Cr**. Only parties in a debtor or creditor
  group (*Sundry Debtors*, *Sundry Creditors*, or groups with those words) become customers and
  suppliers; bank, cash, expense, tax and "… Payable" ledgers are skipped and listed in the preview.
- Items: *Display → Masters → Item List*, export with **Name, Alias, HSN/SAC Code, GST Rate,
  Purchase Price, Sale Price, Op. Stock (Qty)**. *Alias* becomes the item code.

## Vyapar

- Parties: *Parties → Export to Excel* — **Name, Phone No., GSTIN, State, Opening Balance,
  Balance Type** (*To Receive* = customer owes you, *To Pay* = you owe the supplier).
- Items: *Items → Export to Excel* — **Item Name, Item Code, HSN, Tax Rate, Purchase Price, Sale
  Price, Opening Stock Quantity**.

## Marg ERP

- Parties: *Ledger list → Export* — **Ledger Name, Group, Mobile, GST No, State, Opening Balance,
  Dr/Cr**. Only *Sundry Debtors* and *Sundry Creditors* are imported.
- Items: *Product list → Export* — **Product Name, Product Code, HSN Code, GST %, Purchase Rate,
  Sale Rate, Opening Stock**.

## If the file is refused

"This does not look like a … export" means the column names did not match. Export again with the
columns above, or send the file to support. A row with a balance that is not one number, or a GST
rate that is not one GST rate, is shown as a row error with the row number from your file. An
opening balance on the wrong side (a customer in credit, a supplier you paid in advance) is **not**
imported: the preview lists it, and you record it as an advance receipt or payment after the
import, so the opening totals still tie. Report total rows and items without a code are handled
for you (totals are skipped; an item without a code gets one made from its name, so the same item
in a later file is matched, not duplicated). Save CSV files with names in quotes, or use .xlsx: a
name with a comma in it otherwise shifts the columns, and the file is refused. Old .xls files must
be saved as .xlsx or CSV first.

The column names here follow each tool's standard export. Support checks them against your own
file before switching the import on (plan WP-GR1b; confirmed per source with pilot files).
