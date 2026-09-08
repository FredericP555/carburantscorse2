from __future__ import annotations

import re
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_DIR = ROOT / ".github" / "workflows"
LOCK = ROOT / "requirements.lock.txt"
DEPENDABOT = ROOT / ".github" / "dependabot.yml"
ACTION_REF = re.compile(r"^\s*-?\s*uses:\s*([^\s@]+)@([^\s#]+)")
EXACT_REQUIREMENT = re.compile(r"^[A-Za-z0-9_.-]+==[^=<>!~\s]+$")


def workflow_files() -> list[Path]:
    return sorted({*WORKFLOW_DIR.glob("*.yml"), *WORKFLOW_DIR.glob("*.yaml")})


class CiSupplyChainContracts(unittest.TestCase):
    def test_all_external_actions_are_pinned_to_full_commit_sha(self):
        failures: list[str] = []
        for path in workflow_files():
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                match = ACTION_REF.match(line)
                if not match:
                    continue
                action, ref = match.groups()
                if action.startswith("./"):
                    continue
                if not re.fullmatch(r"[0-9a-f]{40}", ref):
                    failures.append(f"{path.name}:{number}: {action}@{ref}")
        self.assertEqual(failures, [], "unpinned Actions:\n" + "\n".join(failures))

    def test_hosted_runner_major_image_is_pinned(self):
        failures = []
        for path in workflow_files():
            text = path.read_text(encoding="utf-8")
            if "runs-on: ubuntu-latest" in text:
                failures.append(path.name)
        self.assertEqual(failures, [], f"ubuntu-latest remains in: {failures}")

    def test_setup_python_patch_version_is_exact(self):
        failures = []
        for path in workflow_files():
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if "python-version:" not in line:
                    continue
                value = line.split("python-version:", 1)[1].strip().strip("'\"")
                if value != "3.12.14":
                    failures.append(f"{path.name}:{number}: {value}")
        self.assertEqual(failures, [], "non-exact Python versions:\n" + "\n".join(failures))

    def test_ci_dependency_installs_use_exact_lock(self):
        failures = []
        for path in workflow_files():
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if "pip install" in line and "requirements" in line:
                    if "requirements.lock.txt" not in line or "requirements.txt" in line.replace("requirements.lock.txt", ""):
                        failures.append(f"{path.name}:{number}: {line.strip()}")
        self.assertEqual(failures, [], "CI installs not using requirements.lock.txt:\n" + "\n".join(failures))

    def test_lock_file_contains_only_exact_pins(self):
        self.assertTrue(LOCK.is_file(), "requirements.lock.txt is missing")
        lines = [line.strip() for line in LOCK.read_text(encoding="utf-8").splitlines()]
        requirements = [line for line in lines if line and not line.startswith("#")]
        self.assertTrue(requirements, "requirements.lock.txt is empty")
        bad = [line for line in requirements if not EXACT_REQUIREMENT.fullmatch(line)]
        self.assertEqual(bad, [], f"non-exact lock entries: {bad}")
        normalized = {line.split("==", 1)[0].lower().replace("_", "-") for line in requirements}
        for required in {"pandas", "requests", "beautifulsoup4", "openpyxl"}:
            self.assertIn(required, normalized)

    def test_pip_cache_key_tracks_lock_file(self):
        failures = []
        for path in workflow_files():
            text = path.read_text(encoding="utf-8")
            if "cache: pip" in text and "cache-dependency-path: requirements.lock.txt" not in text:
                failures.append(path.name)
        self.assertEqual(failures, [], f"pip cache does not track lock in: {failures}")

    def test_permissions_are_explicit_and_not_global_write(self):
        failures = []
        for path in workflow_files():
            text = path.read_text(encoding="utf-8")
            if "\npermissions:" not in "\n" + text:
                failures.append(f"{path.name}: missing permissions")
            if re.search(r"(?m)^permissions:\s*write-all\s*$", text):
                failures.append(f"{path.name}: write-all")
        self.assertEqual(failures, [], "permission contract failures:\n" + "\n".join(failures))

    def test_business_verifier_does_not_request_actions_scope(self):
        for path in workflow_files():
            if not path.name.startswith("verify-"):
                continue
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("actions: read", text, f"{path.name} has unnecessary actions: read")

    def test_long_lived_production_evidence_is_kept_90_days(self):
        failures = []
        for path in workflow_files():
            text = path.read_text(encoding="utf-8")
            if "weekly-audit" in text or "business-success-receipt" in text:
                if "retention-days: 90" not in text:
                    failures.append(path.name)
        self.assertEqual(failures, [], f"production evidence below 90-day contract: {failures}")

    def test_dependabot_maintains_pip_and_github_actions(self):
        self.assertTrue(DEPENDABOT.is_file(), ".github/dependabot.yml is missing")
        text = DEPENDABOT.read_text(encoding="utf-8")
        self.assertIn('package-ecosystem: "pip"', text)
        self.assertIn('package-ecosystem: "github-actions"', text)


if __name__ == "__main__":
    unittest.main()
