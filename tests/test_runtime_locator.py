import unittest
from unittest.mock import patch

from visualizer.services.runtime_locator import find_node_runtime


class RuntimeLocatorTest(unittest.TestCase):
    def test_finds_node_in_common_windows_install_directory(self):
        with patch("os.name", "nt"), patch(
            "shutil.which",
            side_effect=lambda command: None,
        ), patch.dict(
            "os.environ",
            {"ProgramFiles": r"C:\Program Files"},
            clear=False,
        ), patch("pathlib.Path.is_file", autospec=True) as is_file:
            is_file.side_effect = lambda path: str(path).lower() == r"c:\program files\nodejs\node.exe"
            self.assertEqual(find_node_runtime(), r"C:\Program Files\nodejs\node.exe")


if __name__ == "__main__":
    unittest.main()
