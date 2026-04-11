import os
import unittest
from unittest import mock

import server


class ApiAuthTestCase(unittest.TestCase):
    def test_requests_are_allowed_when_no_token_is_configured(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertTrue(server._is_authorized_request(None))

    def test_bearer_token_must_match_when_configured(self) -> None:
        with mock.patch.dict(os.environ, {"NYX_API_TOKEN": "secret-token"}, clear=True):
            self.assertTrue(server._is_authorized_request("Bearer secret-token"))
            self.assertFalse(server._is_authorized_request("Bearer wrong"))
            self.assertFalse(server._is_authorized_request(None))


if __name__ == "__main__":
    unittest.main()
