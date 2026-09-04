/** Shared blob download / print helpers for invoice PDFs. */

export function triggerBlobDownload(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.style.display = 'none';
  document.body.appendChild(a);
  a.click();
  setTimeout(() => {
    try {
      document.body.removeChild(a);
    } catch {
      // ignore
    }
    URL.revokeObjectURL(url);
  }, 10_000);
}

export function printBlob(blob: Blob) {
  const url = URL.createObjectURL(blob);
  const printWindow = window.open(url, '_blank');
  if (printWindow) {
    printWindow.focus();
    printWindow.onload = () => {
      try {
        printWindow.print();
      } catch {
        // Browser PDF viewer handles print internally
      }
    };
    // F1-012: don't leak the object URL. Revoke after the print dialog closes,
    // with a long fallback timeout in case afterprint never fires (some PDF
    // viewers) — the blob can be multi-MB and otherwise lives until tab close.
    const revoke = () => URL.revokeObjectURL(url);
    try {
      printWindow.addEventListener('afterprint', revoke, { once: true });
      printWindow.addEventListener('pagehide', revoke, { once: true });
    } catch {
      /* cross-origin PDF viewer — rely on the timeout */
    }
    window.setTimeout(revoke, 120000);
  } else {
    const iframe = document.createElement('iframe');
    iframe.style.position = 'fixed';
    iframe.style.right = '0';
    iframe.style.bottom = '0';
    iframe.style.width = '0';
    iframe.style.height = '0';
    iframe.style.border = '0';
    iframe.style.visibility = 'hidden';
    iframe.src = url;
    document.body.appendChild(iframe);
    iframe.onload = () => {
      try {
        iframe.contentWindow?.focus();
        iframe.contentWindow?.print();
      } catch {
        triggerBlobDownload(blob, 'document.pdf');
      }
    };
    window.setTimeout(() => {
      URL.revokeObjectURL(url);
      if (iframe.parentNode) {
        iframe.parentNode.removeChild(iframe);
      }
    }, 120000);
  }
}

export function openBlobInTab(blob: Blob): () => void {
  const url = URL.createObjectURL(blob);
  window.open(url, '_blank');
  return () => URL.revokeObjectURL(url);
}
