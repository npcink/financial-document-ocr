import unittest

from app.utils.logging_safety import (
    safe_exception_label,
    safe_file_label,
    safe_job_label,
)


class _Response:
    status_code = 429


class _ProviderError(Exception):
    response = _Response()


class LoggingSafetyTest(unittest.TestCase):
    def test_file_labels_are_stable_opaque_and_keep_only_safe_suffix(self):
        filename = "客户张三-银行账号-6212345678901234.PDF"
        first = safe_file_label(filename)
        second = safe_file_label(filename)

        self.assertEqual(first, second)
        self.assertTrue(first.startswith("file-"))
        self.assertTrue(first.endswith(".pdf"))
        self.assertNotIn("张三", first)
        self.assertNotIn("6212345678901234", first)
        self.assertNotEqual(first, safe_file_label("其他客户.pdf"))

    def test_job_labels_do_not_include_source_identifier(self):
        job_id = "customer-session-job-123456"
        label = safe_job_label(job_id)

        self.assertTrue(label.startswith("job-"))
        self.assertNotIn(job_id, label)

    def test_exception_labels_drop_messages_but_keep_status_classification(self):
        exc = _ProviderError("token=secret customer=张三")
        label = safe_exception_label(exc)

        self.assertEqual(label, "_ProviderError(status=429)")
        self.assertNotIn("secret", label)
        self.assertNotIn("张三", label)


if __name__ == "__main__":
    unittest.main()
