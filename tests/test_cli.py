import subprocess
import sys
import unittest


class TestCLINoConfig(unittest.TestCase):
    """Test CLI behaviour when no .xsyncfar.yml is present."""

    def test_exits_with_error_when_no_config(self):
        # Run from the filesystem root where no .xsyncfar.yml will be found
        root = "C:\\" if sys.platform.startswith("win") else "/"
        result = subprocess.run(
            [sys.executable, "-m", "xsyncfar"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            cwd=root,
        )
        self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
