import subprocess
import sys
import unittest


class TestCLI(unittest.TestCase):
    def test_module_cli_prints_helloworld(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "xsyncfar"],
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertEqual(result.stdout.strip(), "helloworld")


if __name__ == "__main__":
    unittest.main()
