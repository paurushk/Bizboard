/** Shared blob download / print helpers for invoice PDFs. */

export function triggerBlobDownload(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
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
  }
  window.setTimeout(() => {
    URL.revokeObjectURL(url);
  }, 120000);
}

export function openBlobInTab(blob: Blob): () => void {
  const url = URL.createObjectURL(blob);
  window.open(url, '_blank');
  return () => URL.revokeObjectURL(url);
}
