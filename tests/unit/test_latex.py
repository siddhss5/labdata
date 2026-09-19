"""Tests for LaTeX-to-Markdown and LaTeX-to-text conversion."""

from labdata.latex import replace_latex_accents, latex_to_markdown, latex_to_text


class TestReplaceLatexAccents:
    """Tests for Unicode accent replacement."""

    def test_acute_accents(self):
        assert replace_latex_accents("\\'e") == "é"
        assert replace_latex_accents("\\'a") == "á"
        assert replace_latex_accents("\\'E") == "É"

    def test_umlaut_accents(self):
        assert replace_latex_accents('\\"u') == "ü"
        assert replace_latex_accents('\\"o') == "ö"
        assert replace_latex_accents('\\"a') == "ä"

    def test_grave_accents(self):
        assert replace_latex_accents("\\`e") == "è"
        assert replace_latex_accents("\\`a") == "à"

    def test_circumflex(self):
        assert replace_latex_accents("\\^e") == "ê"
        assert replace_latex_accents("\\^o") == "ô"

    def test_tilde(self):
        assert replace_latex_accents("\\~n") == "ñ"
        assert replace_latex_accents("\\~a") == "ã"

    def test_cedilla(self):
        assert replace_latex_accents("\\c{c}") == "ç"
        assert replace_latex_accents("\\c{C}") == "Ç"

    def test_caron(self):
        assert replace_latex_accents("\\v{c}") == "č"
        assert replace_latex_accents("\\v{s}") == "š"
        assert replace_latex_accents("\\v{z}") == "ž"

    def test_special_chars(self):
        assert replace_latex_accents("\\ss") == "ß"
        assert replace_latex_accents("\\ae") == "æ"
        assert replace_latex_accents("\\o") == "ø"
        assert replace_latex_accents("\\l") == "ł"

    def test_braced_forms(self):
        """BibTeX commonly wraps accents in braces: {M{\\"u}ller}"""
        assert replace_latex_accents('{M{\\"u}ller}') == "{Müller}"
        assert replace_latex_accents("{\\'e}") == "é"

    def test_braced_char_form(self):
        """Handle \\'{e} form (brace around the char)."""
        assert replace_latex_accents("\\'{e}") == "é"
        assert replace_latex_accents('\\"{u}') == "ü"

    def test_mixed_text(self):
        text = "Caf\\'e M\\\"{u}ller na\\\"ive"
        result = replace_latex_accents(text)
        assert "é" in result
        assert "ü" in result

    def test_no_accents(self):
        assert replace_latex_accents("plain text") == "plain text"

    def test_non_string_input(self):
        assert replace_latex_accents(None) is None
        assert replace_latex_accents(42) == 42


class TestLatexToMarkdown:
    """Tests for LaTeX-to-Markdown conversion."""

    def test_bold(self):
        assert latex_to_markdown("\\textbf{bold text}") == "**bold text**"

    def test_italic_emph(self):
        assert latex_to_markdown("\\emph{italic text}") == "*italic text*"

    def test_italic_textit(self):
        assert latex_to_markdown("\\textit{italic text}") == "*italic text*"

    def test_href_with_text(self):
        result = latex_to_markdown("\\href{https://example.com}{click here}")
        assert result == "[click here](https://example.com)"

    def test_href_without_text(self):
        result = latex_to_markdown("\\href{https://example.com}")
        assert result == "[https://example.com](https://example.com)"

    def test_superscript(self):
        assert latex_to_markdown("x^{2}") == "x<sup>2</sup>"

    def test_subscript(self):
        assert latex_to_markdown("H_{2}O") == "H<sub>2</sub>O"

    def test_math_passthrough(self):
        result = latex_to_markdown("Time complexity is $O(n \\log n)$")
        assert "$O(n \\log n)$" in result

    def test_math_not_processed_as_formatting(self):
        """Math content should not have its braces removed or formatting applied."""
        result = latex_to_markdown("$\\textbf{x}$")
        assert "$\\textbf{x}$" in result

    def test_curly_braces_removed(self):
        assert latex_to_markdown("{Some} {Title}") == "Some Title"

    def test_accents_converted(self):
        result = latex_to_markdown("Caf\\'e")
        assert result == "Café"

    def test_combined(self):
        text = "\\textbf{Best Paper} at \\emph{RSS} $2024$"
        result = latex_to_markdown(text)
        assert "**Best Paper**" in result
        assert "*RSS*" in result
        assert "$2024$" in result

    def test_orphaned_textbf(self):
        """\\textbf without braces should be stripped."""
        result = latex_to_markdown("\\textbf something")
        assert "\\textbf" not in result

    def test_non_string_input(self):
        assert latex_to_markdown(None) is None

    def test_empty_string(self):
        assert latex_to_markdown("") == ""


class TestLatexToText:
    """Tests for LaTeX-to-plain-text conversion."""

    def test_strips_bold(self):
        assert latex_to_text("\\textbf{bold}") == "bold"

    def test_strips_italic(self):
        assert latex_to_text("\\emph{italic}") == "italic"

    def test_strips_href_keeps_text(self):
        result = latex_to_text("\\href{https://example.com}{click here}")
        assert result == "click here"

    def test_strips_superscript(self):
        assert latex_to_text("x^{2}") == "x2"

    def test_accents_converted(self):
        assert latex_to_text("M\\\"{u}ller") == "Müller"

    def test_braces_removed(self):
        assert latex_to_text("{Some} {Title}") == "Some Title"

    def test_non_string_input(self):
        assert latex_to_text(None) is None
