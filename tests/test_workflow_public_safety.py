"""Guards the properties that make the workflows safe in a public repository.

Run logs and workflow artifacts are world readable once a repository is
public. Three things keep operator identity and account identifiers out of
them, and each regresses silently:

  * the runner prints the job-level `env:` block at the start of every step,
    so a dispatch input holding an address is echoed once per step unless the
    very first step registers it as a masked value;
  * `aws-actions/configure-aws-credentials` does not mask the account id by
    default, and `sts get-caller-identity` prints it along with the role ARN;
  * an uploaded audit artifact must carry digests rather than addresses.

Parsed as text rather than with PyYAML: the suite must run against
requirements.lock alone, which has no YAML library.
"""
import re
import unittest
from pathlib import Path

WORKFLOW_DIR = Path(__file__).resolve().parents[1] / ".github" / "workflows"

# Workflows that take an approver address as a dispatch input.
IDENTITY_WORKFLOWS = (
    "final-policygate-demo.yml",
    "live-foxit-esign-send.yml",
    "live-foxit-esign-verify.yml",
)
# Workflows that assume an AWS role over OIDC.
AWS_WORKFLOWS = (
    "final-policygate-demo.yml",
    "live-terraform-plan.yml",
)
# Workflows that upload an audit record built by policygate.audit, which keeps
# the real address in the in-run copy.
LIBRARY_AUDIT_WORKFLOWS = (
    "live-foxit-esign-send.yml",
    "live-foxit-esign-verify.yml",
)


def read(name: str) -> str:
    return (WORKFLOW_DIR / name).read_text(encoding="utf-8")


def first_step_name(text: str) -> str:
    """The `name:` of the first entry under `steps:`."""
    match = re.search(r"^    steps:\n(?:\s*#.*\n)*\s*- name: (.+)$", text, re.M)
    return match.group(1).strip() if match else ""


class MasksApproverIdentity(unittest.TestCase):
    def test_masking_is_the_first_step(self):
        # Anything earlier in the job echoes the env block unmasked, so this
        # has to lead. A later step would leave every preceding step leaking.
        for name in IDENTITY_WORKFLOWS:
            with self.subTest(workflow=name):
                self.assertIn("Mask the approver's identity", first_step_name(read(name)))

    def test_add_mask_covers_every_identity_input(self):
        for name in IDENTITY_WORKFLOWS:
            with self.subTest(workflow=name):
                text = read(name)
                self.assertIn("::add-mask::", text)
                # Every SIGNER env var fed from a dispatch input must appear in
                # the masking step, or that value survives into the log.
                declared = set(re.findall(
                    r"^\s+(POLICYGATE_[A-Z_]*SIGNER[A-Z_]*):\s*\$\{\{\s*inputs\.", text, re.M))
                mask_step = text.split("- name: Check out repository")[0]
                for var in declared:
                    self.assertIn(var, mask_step,
                                  f"{var} is a dispatch input but is never masked")

    def test_short_values_are_not_masked(self):
        # Masking a one-character value would redact most of the log.
        for name in IDENTITY_WORKFLOWS:
            with self.subTest(workflow=name):
                self.assertRegex(read(name), r'\$\{#value\}"?\s*\]?\s*-gt 1')


class MasksAwsAccountId(unittest.TestCase):
    def test_every_credential_step_masks_the_account_id(self):
        for name in AWS_WORKFLOWS:
            with self.subTest(workflow=name):
                text = read(name)
                uses = text.count("aws-actions/configure-aws-credentials")
                self.assertGreater(uses, 0)
                self.assertEqual(
                    text.count("mask-aws-account-id: true"), uses,
                    "every configure-aws-credentials step must mask the account id")


class ArtifactsCarryNoIdentity(unittest.TestCase):
    def test_preserved_metadata_holds_a_digest_not_an_address(self):
        text = read("final-policygate-demo.yml")
        preserved = text.split("preserved = {")[1].split("}")[0]
        self.assertIn("expected_signer_sha256", preserved)
        # Reading audit["expected_signer_email"] to hash it is correct and
        # required; what must not appear is an output *key* of that name, so
        # match the trailing colon that distinguishes a key from a lookup.
        self.assertNotIn('"expected_signer_email":', preserved)
        self.assertNotIn('"foxit_folder_id":', preserved)

    def test_library_written_audits_are_stripped_before_upload(self):
        for name in LIBRARY_AUDIT_WORKFLOWS:
            with self.subTest(workflow=name):
                text = read(name)
                self.assertIn("Strip identity from the artifact copy", text)
                # The stripping step must precede the upload, or it uploads the
                # unredacted file.
                strip_at = text.index("Strip identity from the artifact copy")
                upload_at = text.index("uses: actions/upload-artifact")
                self.assertLess(strip_at, upload_at)

    def test_stripping_removes_every_address_key(self):
        for name in LIBRARY_AUDIT_WORKFLOWS:
            with self.subTest(workflow=name):
                text = read(name)
                for key in ("signer_email", "expected_signer_email",
                            "verified_signer_email"):
                    self.assertIn(f'"{key}"', text)
                self.assertIn('record.pop("foxit_folder_id", None)', text)


if __name__ == "__main__":
    unittest.main()
