"""Kiểm tra gateway phục vụ luồng sản phẩm, không chạy target hoặc Docker."""
from types import ModuleType
import builtins
from contextlib import ExitStack
from tempfile import TemporaryDirectory
import unittest
from email.message import Message
from io import BytesIO
from pathlib import Path
from unittest.mock import Mock, patch


PATH = Path(__file__).resolve().parents[2] / "cyber-range/runtime/gateway.py"


def load_gateway(source=None):
    code = compile(PATH.read_text(encoding="utf-8") if source is None else source, str(PATH), "exec")
    original_open = builtins.open

    def read_only_open(file, mode="r", *args, **kwargs):
        if any(flag in mode for flag in "wax+"):
            raise AssertionError("Import ghi tệp")
        return original_open(file, mode, *args, **kwargs)

    with TemporaryDirectory() as directory, ExitStack() as stack:
        stack.enter_context(patch.dict("os.environ", {"SHOPLAB_DATA_DIR": directory}))
        stack.enter_context(patch("builtins.open", side_effect=read_only_open))
        guards = [stack.enter_context(patch(target, side_effect=AssertionError(target))) for target in (
            "pathlib.Path.mkdir", "pathlib.Path.write_text", "pathlib.Path.write_bytes",
            "pathlib.Path.open", "sqlite3.connect", "socket.socket", "socket.create_connection",
            "http.server.HTTPServer.__init__", "http.server.HTTPServer.serve_forever",
        )]
        module = ModuleType("gateway_import_fixture")
        module.__file__ = str(PATH)
        exec(code, module.__dict__)
        for guard in guards:
            guard.assert_not_called()
        assert not list(Path(directory).iterdir()), "Import tạo tệp"
    return module


gateway = load_gateway()


class GatewayProductTests(unittest.TestCase):
    def guarded_import(self, source):
        return load_gateway(source).__dict__

    def test_import_has_no_filesystem_database_or_network_side_effects(self):
        self.guarded_import(PATH.read_text(encoding="utf-8"))

    def test_import_guards_detect_side_effects(self):
        for source in (
            "open('fixture.txt', 'w')",
            "from pathlib import Path; Path('fixture').mkdir()",
            "import sqlite3; sqlite3.connect(':memory:')",
            "import socket; socket.socket()",
            "from http.server import HTTPServer; HTTPServer(('127.0.0.1', 0), None)",
            "from http.server import HTTPServer; HTTPServer.serve_forever(None)",
        ):
            with self.subTest(source=source), self.assertRaises(AssertionError):
                self.guarded_import(source)

    def make_handler(self, path="/login", body=b""):
        handler = object.__new__(gateway.Gateway)
        handler.path = path
        handler.command = "POST"
        handler.headers = Message()
        handler.headers["Content-Length"] = str(len(body))
        handler.rfile = BytesIO(body)
        handler.wfile = BytesIO()
        handler.connection = Mock()
        handler.send_error = Mock()
        handler.send_response = Mock()
        handler.send_header = Mock()
        handler.end_headers = Mock()
        return handler

    def upstream(self, status=200, body=b"ok", headers=()):
        connection = Mock()
        response = connection.getresponse.return_value
        response.status = status
        response.read.return_value = body
        response.getheaders.return_value = list(headers)
        return connection

    def proxy(self, handler, connection):
        with patch.object(gateway, "TARGET_HOST", "lab-ecommerce"), \
                patch.object(gateway, "TARGET_PORT", 8080), \
                patch.object(gateway, "HTTPConnection", return_value=connection) as factory:
            handler._proxy()
        return factory

    def test_preserves_session_and_multiple_cookies_without_following_redirect(self):
        handler = self.make_handler(body=b"form=data")
        handler.headers["Cookie"] = "session=test-fixture"
        handler.headers["X-CSRF-Token"] = "test-csrf"
        handler.headers["Authorization"] = "must-not-forward"
        connection = self.upstream(302, b"", [
            ("Set-Cookie", "session=new-fixture; Path=/; HttpOnly"),
            ("Set-Cookie", "csrf=fixture; Path=/"),
            ("Location", "/cart"),
            ("Content-Length", "999"),
            ("Connection", "close"),
        ])
        self.proxy(handler, connection)
        handler.send_response.assert_called_once_with(302)
        sent = connection.request.call_args.kwargs["headers"]
        self.assertEqual(sent["Cookie"], "session=test-fixture")
        self.assertEqual(sent["X-CSRF-Token"], "test-csrf")
        self.assertNotIn("Authorization", sent)
        self.assertEqual(connection.request.call_count, 1)
        sent_headers = [call.args for call in handler.send_header.call_args_list]
        self.assertEqual(sum(key == "Set-Cookie" for key, _ in sent_headers), 2)
        self.assertIn(("Location", "/cart"), sent_headers)
        self.assertIn(("Content-Length", "0"), sent_headers)
        self.assertNotIn(("Connection", "close"), sent_headers)
        handler.send_error.assert_not_called()
        connection.close.assert_called_once()

    def test_forwards_error_status_and_bounded_body(self):
        handler = self.make_handler()
        connection = self.upstream(403, b"denied", [("Content-Type", "text/plain")])
        self.proxy(handler, connection)
        handler.send_response.assert_called_once_with(403)
        self.assertEqual(handler.wfile.getvalue(), b"denied")
        connection.getresponse.return_value.read.assert_called_once_with(gateway.MAX_BODY + 1)

    def test_rejects_external_redirect_without_second_request(self):
        handler = self.make_handler()
        connection = self.upstream(302, b"", [("Location", "https://outside.invalid/")])
        self.proxy(handler, connection)
        handler.send_error.assert_called_once_with(502)
        handler.send_response.assert_not_called()
        self.assertEqual(connection.request.call_count, 1)

    def test_normalizes_same_upstream_absolute_redirect(self):
        with patch.object(gateway, "TARGET_HOST", "lab-ecommerce"), \
                patch.object(gateway, "TARGET_PORT", 8080):
            self.assertEqual(gateway.safe_location("http://lab-ecommerce:8080/cart", "/login"), "/cart")
            self.assertEqual(gateway.safe_location("../cart", "/account/login"), "/cart")

    def test_rejects_path_authority_and_ambiguous_framing_before_connect(self):
        for path in ("http://outside.invalid/", "//outside.invalid/", "/%2foutside.invalid/", "/bad%0dpath", "/bad\\path", "/path#fragment"):
            with self.subTest(path=path):
                handler = self.make_handler(path)
                factory = self.proxy(handler, self.upstream())
                handler.send_error.assert_called_once_with(400)
                factory.assert_not_called()
        for kind in ("duplicate", "transfer", "negative", "malformed"):
            with self.subTest(kind=kind):
                handler = self.make_handler()
                if kind == "duplicate":
                    handler.headers["Content-Length"] = "0"
                elif kind == "transfer":
                    handler.headers["Transfer-Encoding"] = "chunked"
                else:
                    handler.headers.replace_header("Content-Length", "-1" if kind == "negative" else "abc")
                factory = self.proxy(handler, self.upstream())
                handler.send_error.assert_called_once_with(400)
                factory.assert_not_called()

    def test_rejects_encoded_authority_after_multiple_decode_passes(self):
        for path in ("/%252foutside.invalid/", "/%25252foutside.invalid/"):
            with self.subTest(path=path):
                handler = self.make_handler(path)
                factory = self.proxy(handler, self.upstream())
                handler.send_error.assert_called_once_with(400)
                factory.assert_not_called()

    def test_rejects_ambiguous_redirect_and_header_controls(self):
        for headers in (
            [("Location", "/cart"), ("Location", "/orders")],
            [("Set-Cookie", "session=fixture\r\nInvalid: value")],
        ):
            with self.subTest(headers=headers):
                handler = self.make_handler()
                connection = self.upstream(302, b"", headers)
                self.proxy(handler, connection)
                handler.send_error.assert_called_once_with(502)
                handler.send_response.assert_not_called()
                connection.close.assert_called_once()

    def test_removes_headers_named_by_connection(self):
        handler = self.make_handler()
        connection = self.upstream(headers=[
            ("Connection", "Set-Cookie"),
            ("Set-Cookie", "session=must-not-forward"),
            ("Content-Type", "text/plain"),
        ])
        self.proxy(handler, connection)
        sent = [call.args for call in handler.send_header.call_args_list]
        self.assertFalse(any(key.lower() == "set-cookie" for key, _ in sent))
        self.assertIn(("Content-Type", "text/plain"), sent)

    def test_rejects_unregistered_upstream(self):
        handler = self.make_handler()
        with patch.object(gateway, "TARGET_HOST", "outside.invalid"), \
                patch.object(gateway, "HTTPConnection") as factory:
            handler._proxy()
        handler.send_error.assert_called_once_with(503)
        factory.assert_not_called()

    def test_rejects_oversized_or_truncated_request(self):
        for oversized in (True, False):
            handler = self.make_handler(body=b"a")
            handler.headers.replace_header("Content-Length", str(gateway.MAX_BODY + 1 if oversized else 2))
            factory = self.proxy(handler, self.upstream())
            handler.send_error.assert_called_once_with(413 if oversized else 400)
            factory.assert_not_called()

    def test_rejects_oversized_response_and_closes_connection(self):
        handler = self.make_handler()
        connection = self.upstream(body=b"x" * (gateway.MAX_BODY + 1))
        self.proxy(handler, connection)
        handler.send_error.assert_called_once_with(502)
        handler.send_response.assert_not_called()
        connection.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
