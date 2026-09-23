"""Compile every .bib file under a directory on its own and report problems.

    python tools/smoke.py /usr/local/texlive/2025/texmf-dist/bibtex/bib

Each file gets its own one-file configuration and its own run of the CLI, so
one bad file cannot hide another. Reports crashes (a traceback), standard
error lines that carry no diagnostic code, LaTeX remnants (a backslash or a
brace outside math) in emitted titles and names, and a histogram of codes.
Exits 1 on a crash or an uncoded line; remnants are listed for a person to
judge. Not run in CI: it is meant for real bibliographies, such as TeX Live's.
"""

import collections
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

# A diagnostic line on standard error, as the CLI prints it: a warning carries
# a prefix, and a code is upper-case words joined by hyphens.
CODED = re.compile(r"^(?:Warning: |Error[^:]*: )?([A-Z0-9]+(?:-[A-Z0-9]+)+) ")
# Math, kept verbatim, where backslashes and braces belong: `$$...$$` (tried
# before `$...$`), `$...$`, `\(...\)` and `\[...\]`, across line breaks.
MATH = re.compile(r"\$\$.*?\$\$|\$.*?\$|\\\(.*?\\\)|\\\[.*?\\\]", re.DOTALL)
TRACEBACK = "Traceback (most recent call last)"


def compile_one(bib: Path, work: Path):
    """Run the CLI on ``bib`` alone; return (stderr, document, problem)."""
    config, output = work / "lab.yaml", work / "out.json"
    output.unlink(missing_ok=True)
    # JSON is YAML, so the configuration needs no YAML writer.
    config.write_text(json.dumps({
        "bib_dir": str(bib.parent),
        "bib_files": [{"name": bib.name, "category": "Smoke"}]}))
    run = subprocess.run(
        [sys.executable, "-m", "sslabdata.cli", "--config", str(config),
         "--format", "json", "--output", str(output)],
        capture_output=True, text=True, errors="replace", check=False)
    try:  # output that does not parse fails this file, not the whole run
        text = output.read_text(encoding="utf-8") if output.exists() else "null"
        return run.stderr, json.loads(text), None
    except ValueError as e:
        return run.stderr, None, f"unreadable output: {e}"


def remnants(document):
    """Yield (key, text) for each title or name with LaTeX left outside math."""
    for work in document["works"]:
        texts = [work["title"]] + [person["name"] for person in
                                   work["authors"] + work["editors"]]
        for text in texts:
            if text and re.search(r"[\\{}]", MATH.sub("", text)):
                yield work["bib_id"], text


def main(root: str) -> int:
    crashes, uncoded, leftovers, documents = [], [], [], 0
    codes = collections.Counter()
    bibs = sorted(Path(root).rglob("*.bib"))
    if not bibs:
        print(f"no .bib files under {root}")
        return 1
    with tempfile.TemporaryDirectory() as tmp:
        for bib in bibs:
            stderr, document, problem = compile_one(bib, Path(tmp))
            # Lines before a traceback still count; the traceback is the crash.
            before, crashed, traceback = stderr.partition(TRACEBACK)
            if crashed:
                crashes.append((bib, traceback.strip().rsplit("\n", 1)[-1]))
            if problem:
                crashes.append((bib, problem))
            for line in before.splitlines():
                match = CODED.match(line)
                if match:
                    codes[match.group(1)] += 1
                else:
                    uncoded.append((bib, line))
            if document:
                documents += 1
                leftovers += [(bib, key, text)
                              for key, text in remnants(document)]
    for bib, last in crashes:
        print(f"CRASH {bib}: {last}")
    for bib, line in uncoded:
        print(f"UNCODED {bib}: {line}")
    for bib, key, text in leftovers:
        print(f"REMNANT {bib}:{key}: {text}")
    print(f"\n{len(bibs)} files, {documents} compiled to a document, "
          f"{len(crashes)} crashes, "
          f"{len(uncoded)} uncoded lines, {len(leftovers)} remnants")
    for code, count in sorted(codes.items()):
        print(f"  {count:6d}  {code}")
    return 1 if crashes or uncoded else 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: python tools/smoke.py <directory of .bib files>")
    sys.exit(main(sys.argv[1]))
