# WhatsApp template: invoice with a payment link

First template (GD-25): `invoice_with_payment_link`.

Body, in the customer's language: the invoice number, the amount due, and the payment link for that invoice. No other document is attached in this template.

The reminder template stays second. It is not used for campaigns. Sending a reminder still waits on [WHATSAPP_CONSENT_POLICY.md](WHATSAPP_CONSENT_POLICY.md).

Credentials (token, phone number id, and the approved template) belong in the deployment secret store. They are not stored in this repository.

If Cloud is off or the keys are missing, staff get a wa.me link with the same text. The screen must not say the message was delivered.
