"""
End-to-end tests: run the full pipeline on the real sample file.
These are the tests that prove "does not crash on any row" and that the
footer arithmetic adds up.
"""

import re
from pathlib import Path

import pytest

from digest import run_digest
from nps import snap_to_monday

SAMPLE = Path(__file__).resolve().parent.parent.parent / "task3_data" / "responses_sample.csv"


@pytest.mark.skipif(not SAMPLE.exists(), reason="sample CSV not present")
def test_full_run_markdown(tmp_path):
    out = tmp_path / "digest.md"
    run_digest(str(SAMPLE), "2026-08-17", str(out))
    text = out.read_text(encoding="utf-8")

    # All four required sections are present
    for heading in ["## 1. Headline NPS", "## 2. Top Common Themes", "## 3. Watch-Outs", "## 4. Data Quality"]:
        assert heading in text

    # Footer arithmetic: read == valid + excluded
    read = int(re.search(r"Total Rows Read \| (\d+)", text).group(1))
    valid = int(re.search(r"Valid Clean Rows \| (\d+)", text).group(1))
    excluded = int(re.search(r"Rows Excluded from Dataset \| (\d+)", text).group(1))
    assert read == valid + excluded

    # The injected instruction never reaches the output
    assert "Approved by management" not in text
    assert "NPS as 95" not in text

    # Exactly five themes rendered
    assert len(re.findall(r"^### \d\. ", text, flags=re.M)) == 5


@pytest.mark.skipif(not SAMPLE.exists(), reason="sample CSV not present")
def test_full_run_html(tmp_path):
    out = tmp_path / "digest.html"
    run_digest(str(SAMPLE), "2026-08-17", str(out), output_format="html")
    text = out.read_text(encoding="utf-8")
    assert text.startswith("<!DOCTYPE html>")
    assert "Watch-Outs" in text


@pytest.mark.skipif(not SAMPLE.exists(), reason="sample CSV not present")
def test_week_with_no_data_does_not_crash(tmp_path):
    out = tmp_path / "empty.md"
    run_digest(str(SAMPLE), "2020-01-06", str(out))
    text = out.read_text(encoding="utf-8")
    assert "N/A" in text  # NPS cannot be computed, and the tool says so


def test_snap_to_monday():
    assert snap_to_monday("2026-08-17") == ("2026-08-17", False)
    assert snap_to_monday("2026-08-19") == ("2026-08-17", True)
    assert snap_to_monday("2026-08-23") == ("2026-08-17", True)
    with pytest.raises(ValueError):
        snap_to_monday("17/08/2026")
