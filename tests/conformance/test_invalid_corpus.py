"""Diagnostics for the invalid corpus (tests/corpus/invalid/<dir>/).

Each case in tests/corpus/expected/diagnostics.yaml is run in its own folder,
so one broken input cannot hide another. Checks look at the exit status and
at tokens (file, entry key, field, value) in labdata's output, never at exact
wording or at parser-library messages.
"""

import pytest
import yaml

from .support import EXPECTED, INVALID, export, run_labdata

with open(EXPECTED / "diagnostics.yaml", encoding="utf-8") as f:
    DIAGNOSTICS = yaml.safe_load(f)

CHECKS = ("exit", "reports", "locates", "kept")


def params(check):
    rows = []
    for case_id, spec in DIAGNOSTICS.items():
        if check not in spec:
            continue
        issue = spec.get("xfail", {}).get(check)
        marks = [pytest.mark.xfail(strict=True, reason=issue)] if issue else []
        rows.append(pytest.param(case_id, spec, id=case_id, marks=marks))
    return rows


def validate(spec):
    return run_labdata(["--config", "lab.yaml", "--validate"], INVALID / spec["dir"])


@pytest.mark.parametrize("case_id, spec", params("exit"))
def test_exit(case_id, spec):
    run = validate(spec)
    assert run.crash is None, f"labdata crashed: {run.crash}"
    if spec["exit"] == "error":
        assert run.code != 0, run.output
        assert run.output.strip(), "exited non-zero without a message"
    elif spec["exit"] == "ok":
        assert run.code == 0, run.output


@pytest.mark.parametrize("case_id, spec", params("reports"))
def test_reports(case_id, spec):
    run = validate(spec)
    missing = [t for t in spec["reports"] if t not in run.output]
    assert not missing, f"output does not name {missing}:\n{run.output}"


@pytest.mark.parametrize("case_id, spec", params("locates"))
def test_locates(case_id, spec):
    run = validate(spec)
    missing = [t for t in spec["locates"] if t not in run.output]
    assert not missing, f"output does not locate {missing}:\n{run.output}"


@pytest.mark.parametrize("case_id, spec", params("kept"))
def test_kept(tmp_path, case_id, spec):
    run, data = export(INVALID / spec["dir"], tmp_path)
    assert run.crash is None, f"labdata crashed: {run.crash}"
    assert data is not None, run.output
    keys = [p["bib_id"] for p in data["publications"]]
    missing = [k for k in spec["kept"] if k not in keys]
    assert not missing, f"entries dropped: {missing}"


def test_spec_is_well_formed():
    for case_id, spec in DIAGNOSTICS.items():
        assert (INVALID / spec["dir"] / "lab.yaml").is_file(), case_id
        assert spec["exit"] in ("error", "ok", "any"), case_id
        assert set(spec) <= {"dir", "xfail", *CHECKS}, case_id
        assert set(spec.get("xfail", {})) <= set(CHECKS) & set(spec), case_id
    dirs = {spec["dir"] for spec in DIAGNOSTICS.values()}
    assert dirs == {d.name for d in INVALID.iterdir() if d.is_dir()}
