from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest

from app.integrations import telegram as telegram_module
from app.integrations.telegram import telegram_send


@pytest.fixture
def configured_settings(monkeypatch):
    monkeypatch.setattr(
        telegram_module.settings, "TELEGRAM_BOT_TOKEN", "TEST_TOKEN_123"
    )
    monkeypatch.setattr(
        telegram_module.settings, "TELEGRAM_CHAT_ID", "-1001234567890"
    )


class TestTelegramSendDisabled:
    def test_no_token_no_call(self, monkeypatch):
        monkeypatch.setattr(telegram_module.settings, "TELEGRAM_BOT_TOKEN", "")
        monkeypatch.setattr(
            telegram_module.settings, "TELEGRAM_CHAT_ID", "-1001"
        )
        with patch.object(telegram_module, "httpx") as mock_httpx:
            telegram_send("hello")
        mock_httpx.Client.assert_not_called()

    def test_no_chat_id_no_call(self, monkeypatch):
        monkeypatch.setattr(
            telegram_module.settings, "TELEGRAM_BOT_TOKEN", "TOKEN"
        )
        monkeypatch.setattr(telegram_module.settings, "TELEGRAM_CHAT_ID", "")
        with patch.object(telegram_module, "httpx") as mock_httpx:
            telegram_send("hello")
        mock_httpx.Client.assert_not_called()

    def test_both_empty_no_call(self, monkeypatch):
        monkeypatch.setattr(telegram_module.settings, "TELEGRAM_BOT_TOKEN", "")
        monkeypatch.setattr(telegram_module.settings, "TELEGRAM_CHAT_ID", "")
        with patch.object(telegram_module, "httpx") as mock_httpx:
            telegram_send("hello")
        mock_httpx.Client.assert_not_called()


class TestTelegramSendUrl:
    def test_url_includes_bot_token(self, configured_settings):
        with patch.object(telegram_module, "httpx") as mock_httpx:
            client_mock = mock_httpx.Client.return_value.__enter__.return_value
            client_mock.post.return_value = MagicMock(status_code=200)
            client_mock.post.return_value.raise_for_status = MagicMock()

            telegram_send("hi")

            url_arg = client_mock.post.call_args[0][0]
            assert url_arg == (
                "https://api.telegram.org/botTEST_TOKEN_123/sendMessage"
            )

    def test_post_used_not_get(self, configured_settings):
        with patch.object(telegram_module, "httpx") as mock_httpx:
            client_mock = mock_httpx.Client.return_value.__enter__.return_value
            client_mock.post.return_value = MagicMock()
            client_mock.post.return_value.raise_for_status = MagicMock()

            telegram_send("x")
            assert client_mock.post.called
            assert not client_mock.get.called


class TestTelegramSendPayload:
    def test_payload_contract(self, configured_settings):
        with patch.object(telegram_module, "httpx") as mock_httpx:
            client_mock = mock_httpx.Client.return_value.__enter__.return_value
            client_mock.post.return_value = MagicMock()
            client_mock.post.return_value.raise_for_status = MagicMock()

            telegram_send("<b>hello</b>")

            payload = client_mock.post.call_args.kwargs["json"]
            assert payload == {
                "chat_id": "-1001234567890",
                "text": "<b>hello</b>",
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            }

    def test_text_passed_verbatim(self, configured_settings):
        with patch.object(telegram_module, "httpx") as mock_httpx:
            client_mock = mock_httpx.Client.return_value.__enter__.return_value
            client_mock.post.return_value = MagicMock()
            client_mock.post.return_value.raise_for_status = MagicMock()

            payload_text = (
                "<b>Alert</b>\n"
                "<b>severity</b>: critical\n"
                "<b>src_ip</b>: 10.0.0.1\n"
            )
            telegram_send(payload_text)

            assert (
                client_mock.post.call_args.kwargs["json"]["text"]
                == payload_text
            )


class TestTelegramSendHttpTimeout:
    def test_client_uses_5s_timeout(self, configured_settings):
        with patch.object(telegram_module, "httpx") as mock_httpx:
            client_mock = mock_httpx.Client.return_value.__enter__.return_value
            client_mock.post.return_value = MagicMock()
            client_mock.post.return_value.raise_for_status = MagicMock()

            telegram_send("x")
            mock_httpx.Client.assert_called_once_with(timeout=5.0)


class TestTelegramSendHttpErrors:
    def test_http_error_is_raised(self, configured_settings):
        with patch.object(telegram_module, "httpx") as mock_httpx:
            client_mock = mock_httpx.Client.return_value.__enter__.return_value
            response = MagicMock()
            response.raise_for_status.side_effect = httpx.HTTPStatusError(
                "401 Unauthorized",
                request=MagicMock(),
                response=MagicMock(status_code=401),
            )
            client_mock.post.return_value = response

            with pytest.raises(httpx.HTTPStatusError):
                telegram_send("x")

    def test_network_error_propagates(self, configured_settings):
        with patch.object(telegram_module, "httpx") as mock_httpx:
            client_mock = mock_httpx.Client.return_value.__enter__.return_value
            client_mock.post.side_effect = httpx.ConnectError("dns failure")

            with pytest.raises(httpx.ConnectError):
                telegram_send("x")
