"""Agent tax-wording policy (ADR-A7).

Agents do NOT reuse the assistant's blanket TAX_PATTERNS: they must be able to restate computed
facts such as "bill rate 18%, PO rate 12%". What is blocked is *advice or determinations*.
Every tax-related number must also pass agents.numbers. The phrase list needs CA review before R5
(QOS item).
"""

from __future__ import annotations

import re

_ADVICE_EN = [
    r"you\s+(?:should|must|need\s+to)\s+(?:claim|reverse|file|pay)\b[^.]{0,40}\b(?:itc|gst|tax)",
    r"(?:claim|reverse)\s+(?:the\s+)?itc",
    r"this\s+is\s+(?:the\s+)?(?:correct|right|applicable)\s+(?:gst\s+|tax\s+)?rate",
    r"(?:is|are)\s+(?:not\s+)?(?:eligible|ineligible)\s+for\s+(?:itc|input\s+tax)",
    r"tax\s+(?:planning|saving|evasion|avoidance)",
    r"(?:file|filing)\s+(?:your\s+)?(?:gstr|return)",
    r"no\s+need\s+to\s+(?:charge|pay)\s+(?:gst|tax)",
]
_ADVICE_HI = [
    r"आपको\s+(?:आईटीसी|itc)\s+(?:क्लेम|दावा)",
    r"सही\s+(?:जीएसटी|gst)\s+दर",
    r"जीएसटी\s+(?:नहीं\s+)?(?:लगाना|देना)\s+(?:है|चाहिए)",
]
ADVICE_RE = re.compile("|".join(_ADVICE_EN + _ADVICE_HI), re.IGNORECASE)


def advice_phrases(text: str) -> list[str]:
    return [m.group(0) for m in ADVICE_RE.finditer(str(text or ""))]


def violates(text: str) -> bool:
    return bool(ADVICE_RE.search(str(text or "")))
