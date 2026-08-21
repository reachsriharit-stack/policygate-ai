import os
import unittest
from pathlib import Path
from unittest.mock import patch

from policygate.provisioning import terraform_runner


class ApplyGatingTests(unittest.TestCase):
    """All apply gates are unit-tested without invoking a real Terraform binary."""

    def setUp(self):
        self._orig_env = os.environ.get("POLICYGATE_ALLOW_APPLY")
        os.environ.pop("POLICYGATE_ALLOW_APPLY", None)

    def tearDown(self):
        if self._orig_env is None:
            os.environ.pop("POLICYGATE_ALLOW_APPLY", None)
        else:
            os.environ["POLICYGATE_ALLOW_APPLY"] = self._orig_env

    def test_rejects_when_not_authorized(self):
        with self.assertRaises(PermissionError):
            terraform_runner.run_apply("some/workdir", authorized=False, allow_apply=True)

    def test_rejects_when_allow_apply_false(self):
        os.environ["POLICYGATE_ALLOW_APPLY"] = "true"
        with self.assertRaises(PermissionError):
            terraform_runner.run_apply("some/workdir", authorized=True, allow_apply=False)

    def test_rejects_when_env_var_missing(self):
        with self.assertRaises(PermissionError):
            terraform_runner.run_apply("some/workdir", authorized=True, allow_apply=True)

    def test_rejects_when_env_var_wrong_value(self):
        os.environ["POLICYGATE_ALLOW_APPLY"] = "yes"
        with self.assertRaises(PermissionError):
            terraform_runner.run_apply("some/workdir", authorized=True, allow_apply=True)

    @patch("policygate.provisioning.terraform_runner._run")
    def test_all_three_gates_open_call_apply_with_saved_plan(self, mock_run):
        os.environ["POLICYGATE_ALLOW_APPLY"] = "true"
        expected = terraform_runner.TerraformResult(
            command=["terraform", "apply"], stdout="ok", stderr=""
        )
        mock_run.return_value = expected

        result = terraform_runner.run_apply(
            "some/workdir", authorized=True, allow_apply=True, plan_file="approved.tfplan"
        )

        self.assertIs(result, expected)
        mock_run.assert_called_once_with(
            Path("some/workdir"),
            ["apply", "-input=false", "-auto-approve", "approved.tfplan"],
        )


class DestroyGatingTests(unittest.TestCase):
    def setUp(self):
        self._orig_env = os.environ.get("POLICYGATE_ALLOW_DESTROY")
        os.environ.pop("POLICYGATE_ALLOW_DESTROY", None)

    def tearDown(self):
        if self._orig_env is None:
            os.environ.pop("POLICYGATE_ALLOW_DESTROY", None)
        else:
            os.environ["POLICYGATE_ALLOW_DESTROY"] = self._orig_env

    def test_destroy_rejects_without_explicit_caller_opt_in(self):
        with self.assertRaises(PermissionError):
            terraform_runner.run_destroy(
                "some/workdir", request_id="PG-1", confirm_request_id="PG-1"
            )

    def test_destroy_rejects_without_environment_gate(self):
        with self.assertRaises(PermissionError):
            terraform_runner.run_destroy(
                "some/workdir", allow_destroy=True, request_id="PG-1", confirm_request_id="PG-1"
            )

    def test_destroy_rejects_wrong_request_confirmation(self):
        os.environ["POLICYGATE_ALLOW_DESTROY"] = "true"
        with self.assertRaises(PermissionError):
            terraform_runner.run_destroy(
                "some/workdir", allow_destroy=True, request_id="PG-1", confirm_request_id="PG-WRONG"
            )

    @patch("policygate.provisioning.terraform_runner._run")
    def test_destroy_all_gates_open_calls_destroy(self, mock_run):
        os.environ["POLICYGATE_ALLOW_DESTROY"] = "true"
        expected = terraform_runner.TerraformResult(
            command=["terraform", "destroy"], stdout="ok", stderr=""
        )
        mock_run.return_value = expected

        result = terraform_runner.run_destroy(
            "some/workdir",
            allow_destroy=True,
            request_id="PG-1",
            confirm_request_id="PG-1",
        )

        self.assertIs(result, expected)
        mock_run.assert_called_once_with(
            Path("some/workdir"), ["destroy", "-input=false", "-auto-approve"]
        )


if __name__ == "__main__":
    unittest.main()
