"""Wiring checks for the dispatch inputs of the shipped workflows.

These are cheap guards on properties that regress silently: an input that
stops being passed, or — the one that matters — operator text interpolated
straight into a `run:` block, where it would be evaluated by the shell before
the script ever sees it.
"""
import unittest
from pathlib import Path

import yaml

WORKFLOW_DIR = Path(__file__).resolve().parents[1] / ".github" / "workflows"
FINAL_DEMO = WORKFLOW_DIR / "final-policygate-demo.yml"


def load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def workflow_inputs(doc: dict) -> dict:
    # PyYAML parses the `on:` key as the boolean True.
    triggers = doc.get("on") or doc.get(True) or {}
    return (triggers.get("workflow_dispatch") or {}).get("inputs") or {}


def run_blocks(doc: dict):
    for job in (doc.get("jobs") or {}).values():
        for step in job.get("steps", []):
            if step.get("run"):
                yield step.get("name", "<unnamed>"), step["run"]


class RequestTextInputTests(unittest.TestCase):
    def setUp(self):
        self.doc = load(FINAL_DEMO)
        self.job = self.doc["jobs"]["final-demo"]

    def test_request_text_is_a_required_dispatch_input(self):
        spec = workflow_inputs(self.doc)["request_text"]
        self.assertTrue(spec["required"])
        self.assertIn("Plain-English", spec["description"])

    def test_default_request_is_the_demo_scenario(self):
        default = workflow_inputs(self.doc)["request_text"]["default"]
        for fragment in ("production PostgreSQL", "us-east-1", "30-day backups", "$900"):
            self.assertIn(fragment, default)

    def test_request_reaches_the_script_through_the_environment(self):
        self.assertEqual(
            self.job["env"]["POLICYGATE_REQUEST_TEXT"], "${{ inputs.request_text }}"
        )

    def test_the_script_reads_the_request_from_the_environment(self):
        body = "\n".join(run for _, run in run_blocks(self.doc))
        self.assertIn('os.environ.get("POLICYGATE_REQUEST_TEXT")', body)
        self.assertIn("parse(REQUEST", body)

    def test_the_request_is_no_longer_hardcoded(self):
        body = "\n".join(run for _, run in run_blocks(self.doc))
        self.assertNotIn('"Provision production PostgreSQL on AWS in us-east-1. "', body)


class RunBlockInjectionTests(unittest.TestCase):
    """No workflow may interpolate dispatch input or event data into a shell
    block: the expression is substituted before bash runs, so the text would be
    executed rather than read."""

    def test_no_workflow_interpolates_inputs_or_event_data_into_a_run_block(self):
        offenders = []
        for path in sorted(WORKFLOW_DIR.glob("*.yml")):
            for name, run in run_blocks(load(path)):
                for marker in ("${{ inputs.", "${{ github.event"):
                    if marker in run:
                        offenders.append(f"{path.name} :: {name} :: {marker}")
        self.assertEqual(offenders, [], f"interpolated into run blocks: {offenders}")


if __name__ == "__main__":
    unittest.main()
