"""GBF Tag Processor — General Bible Format
============================================
Converts MySword GBF markup tags to plain text and HTML.

Usage:
    from apps.scriptures.gbf import process_gbf
    plain, html = process_gbf(raw_scripture_text)
"""

import re


# Patterns for paired tags: <TAG>content<tag_close>
_PAIRED_TAGS = {
    # Formatting
    "FI": ("", "", "<em>", "</em>"),                                 # Added/italicized words
    "FR": ("", "", '<span class="red-letter">', "</span>"),          # Words of Yeshua
    "FO": ("", "", '<span class="ot-quote">', "</span>"),            # OT quotation
    "FU": ("", "", "<u>", "</u>"),                                   # Underline
    "FB": ("", "", "<b>", "</b>"),                                   # Bold
    # Section titles — extracted and rendered above the verse
    "TS": ("", "", '<div class="section-title">', "</div>"),
    # Footnotes
    "RF": ("", "", '<sup class="footnote" title="', '">†</sup>'),
}

# Pattern to match any GBF paired tag: <XX>...<Xx> (uppercase start, lowercase end)
_PAIRED_RE = re.compile(
    r"<(" + "|".join(_PAIRED_TAGS.keys()) + r")>(.*?)<\1[a-z]>",
    re.DOTALL | re.IGNORECASE,
)

# Stand-alone / self-closing tags
_STANDALONE_RE = re.compile(
    r"<("
    r"CM|"                         # paragraph marker
    r"CI|"                         # indent
    r"CL|"                         # new line
    r"WG\d+|WH\d+|WT[A-Za-z0-9-]+|"  # Strong's numbers + morphology
    r"RX[^>]*|"                    # cross-references
    r"PI\d*|PF\d*"                 # poetry indent
    r")>",
    re.IGNORECASE,
)

# Map standalone tags to HTML replacements
_STANDALONE_HTML = {
    "CM": "<br/>",
    "CI": "",
    "CL": "<br/>",
}


def process_gbf(raw: str) -> tuple[str, str]:
    """Convert a raw MySword GBF-tagged verse to (plain_text, html_text).

    - plain_text: all tags stripped, whitespace normalized.
    - html_text: GBF tags converted to semantic HTML.
    """
    if not raw:
        return ("", "")

    html = raw
    plain = raw

    # --- Process paired tags ---
    # We iterate because tags can be nested (e.g. <FI> inside <FR>)
    for _pass in range(3):  # max 3 nesting passes
        prev = html
        html = _PAIRED_RE.sub(_replace_paired_html, html)
        plain = _PAIRED_RE.sub(_replace_paired_plain, plain)
        if html == prev:
            break

    # --- Process standalone tags ---
    html = _STANDALONE_RE.sub(_replace_standalone_html, html)
    plain = _STANDALONE_RE.sub("", plain)

    # --- Cleanup ---
    # Strip any remaining unknown tags
    html = re.sub(r"</?[A-Z][a-z]>", "", html)
    plain = re.sub(r"</?[A-Z][a-z]>", "", plain)
    # Also strip any angle-bracket tags that look like GBF leftovers
    plain = re.sub(r"<[A-Za-z/][^>]*>", "", plain)

    # Normalize whitespace
    plain = re.sub(r"\s+", " ", plain).strip()
    html = re.sub(r"  +", " ", html).strip()

    return (plain, html)


def _replace_paired_html(m: re.Match) -> str:
    tag = m.group(1).upper()
    content = m.group(2)
    if tag in _PAIRED_TAGS:
        _, _, h_open, h_close = _PAIRED_TAGS[tag]
        # Special handling for footnotes: content goes into title attribute
        if tag == "RF":
            escaped = content.replace('"', "&quot;").replace("<", "").replace(">", "")
            return f'<sup class="footnote" title="{escaped}">†</sup>'
        return f"{h_open}{content}{h_close}"
    return content


def _replace_paired_plain(m: re.Match) -> str:
    tag = m.group(1).upper()
    content = m.group(2)
    if tag in _PAIRED_TAGS:
        p_open, p_close, _, _ = _PAIRED_TAGS[tag]
        # For section titles, add a newline separator in plain text
        if tag == "TS":
            return ""  # strip section titles from plain text
        # For footnotes, strip entirely from plain text
        if tag == "RF":
            return ""
        return f"{p_open}{content}{p_close}"
    return content


def _replace_standalone_html(m: re.Match) -> str:
    tag = m.group(1).upper()
    # Check for known prefixed tags
    for prefix, replacement in _STANDALONE_HTML.items():
        if tag.startswith(prefix):
            return replacement
    # Poetry indentation
    if tag.startswith("PI") or tag.startswith("PF"):
        level = tag[2:] or "1"
        try:
            indent = int(level) * 2
        except ValueError:
            indent = 2
        return f'<span style="margin-left:{indent}em"></span>'
    return ""
