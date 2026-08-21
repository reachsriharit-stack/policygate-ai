import unittest

from policygate.provisioning.terraform_generator import generate_terraform


def _evidence(**plan_overrides):
    plan = {
        "cloud": "aws",
        "service": "rds",
        "database_engine": "postgresql",
        "environment": "production",
        "region": "us-east-1",
        "instance_class": "db.r6g.large",
        "high_availability": True,
        "encryption_at_rest": True,
        "backup_retention_days": 30,
        "public_access": False,
        "estimated_monthly_cost_usd": 817.0,
        "estimate_source": "fixed hackathon demo catalog (not live AWS pricing)",
        "policy_injected_controls": [],
    }
    plan.update(plan_overrides)
    return {
        "request_id": "PG-TEST-0001",
        "plan_sha256": "deadbeef" * 8,
        "proposed_plan": plan,
    }


class TerraformGeneratorTests(unittest.TestCase):
    def test_generates_rds_with_aws_managed_master_password(self):
        tf = generate_terraform(_evidence())
        self.assertIn('resource "aws_db_instance" "policygate_db"', tf)
        self.assertIn("manage_master_user_password = true", tf)
        self.assertNotIn('resource "random_password"', tf)
        self.assertNotIn('resource "aws_secretsmanager_secret_version"', tf)

    def test_no_password_value_is_generated_or_assigned(self):
        tf = generate_terraform(_evidence())
        password_assignment_lines = [
            line for line in tf.splitlines() if line.strip().startswith("password =")
        ]
        self.assertEqual(password_assignment_lines, [])
        self.assertNotIn("random_password", tf)
        self.assertIn("master_user_secret", tf)

    def test_reflects_plan_fields_accurately(self):
        tf = generate_terraform(_evidence(
            instance_class="db.t4g.medium", high_availability=False, backup_retention_days=1,
            public_access=True, encryption_at_rest=False, region="us-west-2",
        ))
        self.assertIn('instance_class    = "db.t4g.medium"', tf)
        self.assertIn("multi_az                = false", tf)
        self.assertIn("backup_retention_period = 1", tf)
        self.assertIn("publicly_accessible     = true", tf)
        self.assertIn("storage_encrypted = false", tf)
        self.assertIn('region = "us-west-2"', tf)

    def test_embeds_request_id_and_plan_hash_for_traceability(self):
        evidence = _evidence()
        tf = generate_terraform(evidence)
        self.assertIn(evidence["request_id"], tf)
        self.assertIn(evidence["plan_sha256"], tf)

    def test_rejects_non_aws_or_non_postgresql_plans(self):
        with self.assertRaises(ValueError):
            generate_terraform(_evidence(cloud="azure"))
        with self.assertRaises(ValueError):
            generate_terraform(_evidence(database_engine="mysql"))


if __name__ == "__main__":
    unittest.main()
