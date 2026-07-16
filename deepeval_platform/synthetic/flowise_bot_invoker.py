"""FlowiseBotInvoker — HTTP invocation against a Flowise prediction endpoint,
normalizing success/failure to a Turn (M4.1, R6). Never raises through the
simulator callback.
"""
from __future__ import annotations

import httpx

from deepeval.test_case import Turn

from deepeval_platform.synthetic.bot_invoker_base import BotInvokerBase

_TIMEOUT_SECONDS = 30.0


class FlowiseBotInvoker(BotInvokerBase):
    def __init__(self, bot_id: str, endpoint_url: str) -> None:
        self._bot_id = bot_id
        self._endpoint_url = endpoint_url

    def __call__(self, input: str, turns: list[Turn], thread_id: str) -> Turn:
        try:
            response = httpx.post(
                self._endpoint_url,
                json={"question": input, "overrideConfig": {"sessionId": thread_id}},
                timeout=_TIMEOUT_SECONDS,
            )
            if response.status_code < 200 or response.status_code >= 300:
                return self._unreachable(
                    code="non_2xx_response",
                    error_type="HTTPStatusError",
                    message=f"Flowise responded with status {response.status_code}",
                )

            try:
                data = response.json()
            except Exception as exc:
                return self._unreachable(
                    code="malformed_response",
                    error_type="ResponseNormalizationError",
                    message=f"Flowise response was not valid JSON: {exc}",
                )
            if not isinstance(data, dict):
                return self._unreachable(
                    code="malformed_response",
                    error_type="ResponseNormalizationError",
                    message="Flowise response was not a JSON object",
                )

            text = data.get("text")
            if not isinstance(text, str) or text == "":
                return self._unreachable(
                    code="malformed_response",
                    error_type="ResponseNormalizationError",
                    message="Flowise response had no non-empty string 'text' field",
                )

            return Turn(
                role="assistant",
                content=text,
                metadata={"bot_id": self._bot_id, "session_id": thread_id},
            )
        except Exception as exc:
            return self._unreachable(
                code="invocation_error",
                error_type=type(exc).__name__,
                message=str(exc),
            )

    def _unreachable(self, *, code: str, error_type: str, message: str) -> Turn:
        return Turn(
            role="assistant",
            content="[BOT_UNREACHABLE]",
            metadata={
                "error": {
                    "code": code,
                    "type": error_type,
                    "message": message,
                    "bot_id": self._bot_id,
                }
            },
        )
