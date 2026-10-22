"""Retention defaults until a written compliance policy replaces them.

POD photos are not GST documents. GSP filing rows and bank payloads follow
the longer books-retention window.
"""

POD_PHOTO_RETENTION_DAYS = 365 * 3
GSP_FILING_RETENTION_DAYS = 365 * 8
BANK_FEED_RETENTION_DAYS = 365 * 8

# WP-CP1: CERT-In Directions (2022) — ICT system logs kept for 180 days, stored in India. Applies to
# web/API access logs, sign-in/MFA events, admin and break-glass actions, worker logs and payment
# webhooks (docs/ops/LOG_RETENTION.md). Nothing in the app may prune these sooner.
CERT_IN_LOG_RETENTION_DAYS = 180
