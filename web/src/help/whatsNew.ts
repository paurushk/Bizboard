/**
 * WP-CM3: "What's new" entries, newest first. Source for the in-app panel; docs/help/WHATS_NEW.md
 * mirrors the same ids for people reading the docs. ``guard_whats_new`` fails CI when an entry is
 * missing its Hindi text or the doc and this list disagree.
 *
 * An id starts with its date (YYYY-MM-DD-slug) so the newest id sorts last; the server keeps the
 * newest id each user opened and the help button shows a dot while a newer entry exists.
 */
export interface WhatsNewEntry {
  id: string;
  en: { title: string; body: string };
  hi: { title: string; body: string };
}

export const WHATS_NEW: WhatsNewEntry[] = [
  {
    id: '2026-10-22-signed-in-devices',
    en: {
      title: 'See and sign out your devices',
      body: 'Settings → Users now lists the devices your account is signed in on. Sign out any you do not recognise. We also email you when a new device signs in.',
    },
    hi: {
      title: 'अपने डिवाइस देखें और साइन आउट करें',
      body: 'सेटिंग्स → यूज़र्स में अब वे डिवाइस दिखते हैं जिन पर आपका खाता साइन-इन है। जिसे आप नहीं पहचानते, उसे साइन आउट करें। नया डिवाइस साइन-इन होने पर हम आपको ईमेल भी भेजते हैं।',
    },
  },
  {
    id: '2026-10-22-tds-credit',
    en: {
      title: 'TDS on Bizboard fees comes off your renewal',
      body: 'Claim back TDS you deducted on Bizboard invoices under Billing. Once we check your Form 16A, the amount comes off your next renewal, or we refund it if you ask.',
    },
    hi: {
      title: 'Bizboard फ़ीस पर कटा TDS रिन्यूअल से घटेगा',
      body: 'Bizboard इनवॉइस पर काटा गया TDS बिलिंग में वापस माँगें। फ़ॉर्म 16A की जाँच के बाद यह रकम आपके अगले रिन्यूअल से घट जाएगी, या आप कहें तो हम लौटा देंगे।',
    },
  },
  {
    id: '2026-10-22-support-access',
    en: {
      title: 'Let support look without a screen share',
      body: 'Under Help → Contact support, an owner can let Bizboard support view the company data for one request, read-only, for up to 72 hours. You see every page they open and can end it at any time.',
    },
    hi: {
      title: 'स्क्रीन शेयर के बिना सपोर्ट को देखने दें',
      body: 'सहायता → सपोर्ट से संपर्क में मालिक किसी एक अनुरोध के लिए Bizboard सपोर्ट को कंपनी का डेटा केवल देखने के लिए, अधिकतम 72 घंटे तक, दिखा सकते हैं। वे जो पेज खोलते हैं वह आपको दिखता है और आप कभी भी पहुँच खत्म कर सकते हैं।',
    },
  },
];

export function newestWhatsNewId(): string {
  // Not .at(-1): Safari before 15.4 (and old Android WebViews) lack it, and this runs in the shell.
  const ids = WHATS_NEW.map((e) => e.id).sort();
  return ids.length ? ids[ids.length - 1] : '';
}
