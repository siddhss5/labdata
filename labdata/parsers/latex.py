"""
LaTeX → plain Unicode text, via pylatexenc.

One field value at a time. Math is left as TeX (``math_mode='verbatim'``) so
``$...$`` reaches KaTeX or MathJax untouched; everything else becomes plain
Unicode. Callers convert field by field and fall back to ``strip_braces`` when
a value cannot be converted, so a bad field never costs the whole entry.

Together with bibtex.py this is the adapter: no other module imports pybtex or
pylatexenc.

Copyright (c) 2024 Personal Robotics Laboratory, University of Washington
Author: Siddhartha Srinivasa <siddh@cs.washington.edu>
MIT License - see LICENSE file for details.
"""

import re

from pylatexenc.latex2text import LatexNodes2Text


_CONVERTER = LatexNodes2Text(math_mode='verbatim')

# pylatexenc 2.11 raises IndexError on every \href, so the link is rewritten
# to "text (url)" before conversion. The URL itself is set aside first: it is
# not LaTeX, and characters such as _ or % would not survive the converter.
# Carrying the link content into explicit fields is #27.
_HREF_URL_TEXT = re.compile(r'\\href\s*\{([^{}]*)\}\s*\{((?:[^{}]|\{[^{}]*\})*)\}')
_HREF_URL_ONLY = re.compile(r'\\href\s*\{([^{}]*)\}')

# An unescaped & in a BibTeX field is a literal ampersand, not an alignment tab.
_BARE_AMPERSAND = re.compile(r'(?<!\\)&')

_PLACEHOLDER = '\x01'
_PLACEHOLDER_RE = re.compile(f'{_PLACEHOLDER}(\\d+){_PLACEHOLDER}')


def latex_to_text(text: str) -> str:
    """Convert one LaTeX field value to plain Unicode text.

    Raises whatever pylatexenc raises; callers decide what to do with a value
    that cannot be converted.
    """
    if not text:
        return text

    verbatim: list = []

    def set_aside(value: str) -> str:
        verbatim.append(value)
        return f'{_PLACEHOLDER}{len(verbatim) - 1}{_PLACEHOLDER}'

    text = _HREF_URL_TEXT.sub(lambda m: f'{m.group(2)} ({set_aside(m.group(1))})', text)
    text = _HREF_URL_ONLY.sub(lambda m: set_aside(m.group(1)), text)
    text = _BARE_AMPERSAND.sub(r'\&', text)

    converted = _CONVERTER.latex_to_text(text)
    return _PLACEHOLDER_RE.sub(lambda m: verbatim[int(m.group(1))], converted)


def strip_braces(text: str) -> str:
    """The fallback for a value pylatexenc cannot convert: keep it, lose the braces."""
    return text.replace('{', '').replace('}', '')
