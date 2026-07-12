import os
import tempfile
import unittest
from pathlib import Path

from pr_factory.observability import configure_logging, get_log_file, get_logger


class ObservabilityTests(unittest.TestCase):
    def test_logger_writes_to_configured_file(self):
        with tempfile.TemporaryDirectory(prefix="logger-test-") as tmp:
            log_file = Path(tmp) / "pr-factory-test.log"
            old_file = os.environ.get("PR_FACTORY_LOG_FILE")
            old_level = os.environ.get("PR_FACTORY_LOG_LEVEL")
            os.environ["PR_FACTORY_LOG_FILE"] = str(log_file)
            os.environ["PR_FACTORY_LOG_LEVEL"] = "INFO"
            try:
                logger = configure_logging(force=True)
                get_logger("test.module").info("hello from test logger")

                for handler in logger.handlers:
                    handler.flush()

                self.assertEqual(get_log_file(), log_file)
                self.assertTrue(log_file.exists())
                self.assertIn("hello from test logger", log_file.read_text(encoding="utf-8"))
            finally:
                if old_file is None:
                    os.environ.pop("PR_FACTORY_LOG_FILE", None)
                else:
                    os.environ["PR_FACTORY_LOG_FILE"] = old_file
                if old_level is None:
                    os.environ.pop("PR_FACTORY_LOG_LEVEL", None)
                else:
                    os.environ["PR_FACTORY_LOG_LEVEL"] = old_level
                configure_logging(force=True)


if __name__ == "__main__":
    unittest.main()
