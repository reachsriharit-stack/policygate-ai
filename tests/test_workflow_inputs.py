"""Wiring checks for the dispatch inputs of the shipped workflows.

These guard properties that regress silently: an input that stops being
passed, or — the one that matters — operator text interpolated straight into a
`run:` block, where the expression is substituted before bash starts and the
text would be executed rather than read.

Parsed as text rather than with PyYAML: the test suite must run against
requirements.lock alone, which has no YAML library.
"""
import re
import unittest
from pathlib import Path

WORKFLOW_DIR = Path(__file__).resolve().parents[1] / ".github" / "workflows"
FINAL_DEMO = WORKFLOW_DIR / "final-policygate-demo.yml"


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip())


def _block_under(text: str, header_pattern: str) -> str:
    """The indented body that follows the first line matching the pattern."""
    lines = text.split("\n")
    for index, line in enumerate(lines):
        if re.match(header_pattern, line):
            base = _indent(line)
            body = []
            for following in lines[index + 1:]:
                if following.strip() and _indent(following) <= base:
                    break
                body.append(following)
            return "\n".join(body)
    return ""


def run_blocks(text: str) -> list[str]:
    """Every `run: |` block body, located by indentation in a single pass."""
    lines = text.split("\n")
    blocks: list[str] = []
    index = 0
    while index < len(lines):
        if re.match(r"^\s*run: \|\s*$", lines[index]):
            base = _indent(lines[index])
            body: list[str] = []
            index += 1
            while index < len(lines) and (
                not lines[index].strip() or _indent(lines[index]) > base
            ):
                body.append(lines[index])
                index += 1
            blocks.append("\n".join(body))
            continue
        # Single-line form: `run: echo hi`. Without this a one-liner could
        # interpolate an input and slip past the injection check below.
        inline = re.match(r"^\s*(?:- )?run:[ \t]+(?!\|)(.+)$", lines[index])
        if inline:
            blocks.append(inline.group(1))
        index += 1
    return blocks


def dispatch_input(text: str, name: str) -> str:
    return _block_under(text, rf"^\s+{re.escape(name)}:\s*$")


class RequestTextInputTests(unittest.TestCase):
    def setUp(self):
        self.text = FINAL_DEMO.read_text(encoding="utf-8")

    def test_request_text_is_a_required_dispatch_input(self):
        spec = dispatch_input(self.text, "request_text")
        self.assertIn("description: 'Plain-English infrastructure request'", spec)
        self.assertIn("required: true", spec)

    def test_default_request_is_the_demo_scenario(self):
        spec = dispatch_input(self.text, "request_text")
        for fragment in ("production PostgreSQL", "us-east-1", "30-day backups", "$900"):
            self.assertIn(fragment, spec)

    def test_request_reaches_the_script_through_the_environment(self):
        self.assertIn(
            "POLICYGATE_REQUEST_TEXT: ${{ inputs.request_text }}", self.text
        )

    def test_the_script_reads_the_request_from_the_environment(self):
        body = "\n".join(run_blocks(self.text))
        self.assertIn('os.environ.get("POLICYGATE_REQUEST_TEXT")', body)
        self.assertIn("parse(REQUEST", body)

    def test_the_request_is_no_longer_hardcoded(self):
        body = "\n".join(run_blocks(self.text))
        self.assertNotIn('"Provision production PostgreSQL on AWS in us-east-1. "', body)


class RunBlockInjectionTests(unittest.TestCase):
    """No workflow may interpolate dispatch input or event data into a shell
    block: the expression is substituted before bash runs, so the text would be
    executed rather than read."""

    def test_no_workflow_interpolates_inputs_or_event_data_into_a_run_block(self):
        offenders = []
        for path in sorted(WORKFLOW_DIR.glob("*.yml")):
            text = path.read_text(encoding="utf-8")
            for body in run_blocks(text):
                for marker in ("${{ inputs.", "${{ github.event"):
                    if marker in body:
                        offenders.append(f"{path.name}: {marker}")
        self.assertEqual(offenders, [], f"interpolated into run blocks: {offenders}")

    def test_the_parser_actually_finds_the_run_blocks(self):
        """Guards the guard: a parser that silently found nothing would make
        the injection test vacuous."""
        blocks = run_blocks(FINAL_DEMO.read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(blocks), 5)
        self.assertTrue(any("python -u - <<'PY'" in b for b in blocks))

    def test_single_line_run_steps_are_also_scanned(self):
        """ci.yml uses the one-line `run:` form; a one-liner interpolating an
        input must not slip past the injection check."""
        blocks = run_blocks((WORKFLOW_DIR / "ci.yml").read_text(encoding="utf-8"))
        self.assertTrue(any("unittest" in b for b in blocks), blocks)


if __name__ == "__main__":
    unittest.main()
