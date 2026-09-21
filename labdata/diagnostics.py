"""
Coded diagnostics: one line each, `<CODE> <file>:<key>:<field>: <message>`.

A located part that does not apply is left empty, so the separators stay
where a reader expects them: `CONFIG-NOT-A-MAPPING lab.yaml::: ...` names a
file and nothing inside it. See "Diagnostic codes" in SPEC.md.

Copyright (c) 2024 Personal Robotics Laboratory, University of Washington
Author: Siddhartha Srinivasa <siddh@cs.washington.edu>
MIT License - see LICENSE file for details.
"""

from typing import Optional


class Diagnostic(str):
    """One coded diagnostic: the line itself, with its parts kept alongside.

    A ``str``, so every list that has always carried diagnostics as strings
    carries these unchanged; the parts are there for a caller that would
    otherwise have to split the line, which a citation key containing a
    colon would defeat.
    """

    code: str
    file: Optional[str]
    key: Optional[str]
    field: Optional[str]
    message: str


def diagnostic(code: str, file: Optional[str], key: Optional[str],
               field: Optional[str], message: str) -> Diagnostic:
    """Build one coded diagnostic line; ``None`` parts are left empty."""
    line = Diagnostic(
        f"{code} {file or ''}:{key or ''}:{field or ''}: {message}")
    line.code, line.file, line.key, line.field, line.message = (
        code, file, key, field, message)
    return line
