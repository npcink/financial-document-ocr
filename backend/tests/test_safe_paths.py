import os
import tempfile
import unittest

from app.utils.safe_paths import (
    resolve_under,
    resource_path,
    sanitize_filename,
    validate_resource_id,
)


class SafePathsTest(unittest.TestCase):
    def test_accepts_server_generated_parent_and_child_ids(self):
        self.assertEqual(validate_resource_id("012345abcdef"), "012345abcdef")
        self.assertEqual(validate_resource_id("012345abcdef_0001"), "012345abcdef_0001")

    def test_rejects_path_like_or_unexpected_ids(self):
        for value in ("../012345abcdef", "/tmp/012345abcdef", "job-123", "", "012345abcdef_1"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    validate_resource_id(value)

    def test_sanitizes_cross_platform_upload_names(self):
        self.assertEqual(sanitize_filename(r"C:\\fakepath\\客户回单(1).PDF"), "客户回单(1).PDF")
        self.assertEqual(sanitize_filename("../../etc/passwd"), "passwd")
        self.assertEqual(sanitize_filename("客户/../账单?.xlsx"), "账单_.xlsx")

    def test_resolve_under_rejects_traversal_and_symlink_escape(self):
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as outside:
            real_root = os.path.realpath(root)
            self.assertTrue(resolve_under(root, "safe", "file.pdf").startswith(real_root + os.sep))
            with self.assertRaises(ValueError):
                resolve_under(root, "..", "outside.pdf")

            os.symlink(outside, os.path.join(root, "escape"))
            with self.assertRaises(ValueError):
                resolve_under(root, "escape", "outside.pdf")

    def test_resource_path_validates_id_and_containment(self):
        with tempfile.TemporaryDirectory() as root:
            path = resource_path(root, "012345abcdef", "report.pdf")
            self.assertEqual(path, os.path.join(os.path.realpath(root), "012345abcdef", "report.pdf"))
            with self.assertRaises(ValueError):
                resource_path(root, "../../outside", "report.pdf")


if __name__ == "__main__":
    unittest.main()
