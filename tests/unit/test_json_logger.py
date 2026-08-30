import json
import logging

import pytest

from src.infrastructure.logging.json_formatter import JsonFormatter
from src.infrastructure.logging.logger import Logger
from src.infrastructure.logging.trace import RequestContextFilter


@pytest.mark.unit
class TestJsonFormatter:
	def test_flat_fields_present(self):
		record = logging.LogRecord(
			name="scripulya",
			level=logging.INFO,
			pathname="service.py",
			lineno=10,
			msg="hello %s",
			args=("world",),
			exc_info=None,
			func="do_work",
		)
		line = JsonFormatter().format(record)
		payload = json.loads(line)
		assert payload["message"] == "hello world"
		assert payload["level"] == "INFO"
		assert payload["logger"] == "scripulya"
		assert payload["location"] == "service.py:do_work:10"
		assert payload["service"] == "scripulya-ai"
		assert "timestamp" in payload

	def test_context_fields_from_filter(self):
		record = logging.LogRecord(
			name="scripulya",
			level=logging.WARNING,
			pathname="jwt_service.py",
			lineno=69,
			msg="Invalid JWT token",
			args=None,
			exc_info=None,
			func="verify_token",
		)
		RequestContextFilter().filter(record)
		line = JsonFormatter().format(record)
		payload = json.loads(line)
		assert payload["trace_id"] == "-"
		assert payload["user_id"] == "-"

	def test_extra_keys_ride_along(self):
		record = logging.LogRecord(
			name="scripulya",
			level=logging.INFO,
			pathname="middlewares.py",
			lineno=73,
			msg="Request completed",
			args=None,
			exc_info=None,
			func="dispatch",
		)
		record.status_code = 401
		line = JsonFormatter().format(record)
		payload = json.loads(line)
		assert payload["status_code"] == 401

	def test_exc_info_serialized_as_exception(self):
		try:
			raise ValueError("boom")
		except ValueError:
			import sys

			record = logging.LogRecord(
				name="scripulya",
				level=logging.ERROR,
				pathname="app.py",
				lineno=1,
				msg="failed",
				args=None,
				exc_info=sys.exc_info(),
				func="handler",
			)
		line = JsonFormatter().format(record)
		payload = json.loads(line)
		assert "ValueError: boom" in payload["exception"]

	def test_non_serializable_extra_falls_back_to_str(self):
		record = logging.LogRecord(
			name="scripulya",
			level=logging.DEBUG,
			pathname="x.py",
			lineno=1,
			msg="dbg",
			args=None,
			exc_info=None,
			func="f",
		)
		record.payload = object()
		line = JsonFormatter().format(record)
		payload = json.loads(line)
		assert "object at" in str(payload["payload"])


@pytest.mark.unit
class TestLoggerConfigure:
	@pytest.fixture(autouse=True)
	def restore_root_logging(self):
		root = logging.getLogger()
		snapshot = (list(root.handlers), root.level)
		yield
		root.handlers = snapshot[0]
		root.setLevel(snapshot[1])

	def test_json_mode_installs_json_formatter(self, monkeypatch):
		monkeypatch.setattr("src.conf.settings.LOG_FORMAT_JSON", True, raising=False)
		Logger.configure()
		root = logging.getLogger()
		assert root.handlers
		formatters = [h.formatter for h in root.handlers]
		assert any(isinstance(f, JsonFormatter) for f in formatters)

	def test_text_mode_installs_text_formatter(self, monkeypatch):
		monkeypatch.setattr("src.conf.settings.LOG_FORMAT_JSON", False, raising=False)
		Logger.configure()
		root = logging.getLogger()
		assert all(not isinstance(h.formatter, JsonFormatter) for h in root.handlers)

	def test_handlers_carry_context_filter(self, monkeypatch):
		monkeypatch.setattr("src.conf.settings.LOG_FORMAT_JSON", True, raising=False)
		Logger.configure()
		root = logging.getLogger()
		for handler in root.handlers:
			assert any(isinstance(f, RequestContextFilter) for f in handler.filters)
