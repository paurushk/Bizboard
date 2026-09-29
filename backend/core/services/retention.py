"""Retention defaults until a written compliance policy replaces them.

POD photos are not GST documents. GSP filing rows and bank payloads follow
the longer books-retention window.
"""

POD_PHOTO_RETENTION_DAYS = 365 * 3
GSP_FILING_RETENTION_DAYS = 365 * 8
BANK_FEED_RETENTION_DAYS = 365 * 8
