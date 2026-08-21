import unittest

from policygate.planner import build_plan
from policygate.rules import evaluate
from policygate.schema import ChangeRequest


def make_request(**overrides) -> ChangeRequest:
    base = dict(
        request_id="PG-TEST-0001",
        requested_by="Demo Engineer",
        environment="production",
        cloud="aws",
        database_engine="postgresql",
        region="us-east-1",
        high_availability=True,
        encryption_at_rest=True,
        backup_retention_days=30,
        public_access=False,
        monthly_budget_usd=900,
        approver_name="Jane Smith",
        approver_email="jane@example.com",
    )
    base.update(overrides)
    return ChangeRequest(**base)


class RuleEngineTests(unittest.TestCase):
    def evaluate(self, request):
        return evaluate(request, build_plan(request))

    def test_fully_compliant_request_passes(self):
        self.assertTrue(self.evaluate(make_request()).passed)

    def test_policy_injects_omitted_controls(self):
        req = make_request(encryption_at_rest=None, public_access=None, backup_retention_days=None)
        plan = build_plan(req)
        result = evaluate(req, plan)
        self.assertTrue(result.passed)
        self.assertIn("encryption_at_rest", plan.policy_injected_controls)
        self.assertIn("private_network_access", plan.policy_injected_controls)

    def test_explicit_no_encryption_fails(self):
        result = self.evaluate(make_request(encryption_at_rest=False))
        self.assertIn("SEC-01", [c.code for c in result.failed_checks])

    def test_single_az_fails(self):
        result = self.evaluate(make_request(high_availability=False))
        self.assertIn("HA-01", [c.code for c in result.failed_checks])

    def test_short_backup_fails(self):
        result = self.evaluate(make_request(backup_retention_days=7))
        self.assertIn("BKP-01", [c.code for c in result.failed_checks])

    def test_public_access_fails(self):
        result = self.evaluate(make_request(public_access=True))
        self.assertIn("NET-01", [c.code for c in result.failed_checks])

    def test_unapproved_region_fails(self):
        result = self.evaluate(make_request(region="eu-west-1"))
        self.assertIn("REG-01", [c.code for c in result.failed_checks])

    def test_budget_fails(self):
        result = self.evaluate(make_request(monthly_budget_usd=700))
        self.assertIn("COST-01", [c.code for c in result.failed_checks])

    def test_named_approver_required(self):
        result = self.evaluate(make_request(approver_name=None))
        self.assertIn("APR-01", [c.code for c in result.failed_checks])

    def test_approver_email_required(self):
        result = self.evaluate(make_request(approver_email=None))
        self.assertIn("APR-02", [c.code for c in result.failed_checks])

    def test_invalid_approver_email_fails(self):
        result = self.evaluate(make_request(approver_email="not-an-email"))
        self.assertIn("APR-02", [c.code for c in result.failed_checks])

    def test_zero_budget_fails_instead_of_falling_back_to_org_ceiling(self):
        result = self.evaluate(make_request(monthly_budget_usd=0))
        self.assertIn("COST-01", [c.code for c in result.failed_checks])


if __name__ == "__main__":
    unittest.main()
