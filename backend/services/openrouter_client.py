import json
import logging
from datetime import date, datetime
from typing import Optional
from urllib import request, error

logger = logging.getLogger(__name__)


class OpenRouterClient:
    """Minimal OpenRouter client for image analysis."""

    def __init__(
        self,
        api_key: str,
        model: str,
        daily_limit: int,
        min_interval_seconds: int
    ):
        self.api_key = api_key
        self.model = model
        self.daily_limit = daily_limit
        self.min_interval_seconds = min_interval_seconds
        self._daily_date = date.today()
        self._daily_count = 0
        self._last_request_time: Optional[datetime] = None

    def _reset_if_new_day(self) -> None:
        today = date.today()
        if self._daily_date != today:
            self._daily_date = today
            self._daily_count = 0

    def _rate_limit_ok(self) -> bool:
        self._reset_if_new_day()
        if self._daily_count >= self.daily_limit:
            return False
        if self._last_request_time is None:
            return True
        elapsed = (datetime.now() - self._last_request_time).total_seconds()
        return elapsed >= self.min_interval_seconds

    def analyze_image_base64(self, image_b64: str, prompt: str) -> dict:
        if not self.api_key:
            return {
                "summary": "OpenRouter API key not configured.",
                "person_detected": None,
                "confidence": 0,
                "model": self.model,
                "error": "missing_api_key",
            }

        if not self._rate_limit_ok():
            return {
                "summary": "Analysis skipped due to rate limits.",
                "person_detected": None,
                "confidence": 0,
                "model": self.model,
                "error": "rate_limited",
            }

        instruction = (
            "Return ONLY valid JSON with keys: "
            "person_detected (boolean), confidence (0-100 integer), "
            "importance (1-5 integer), send_gif (boolean), summary (short sentence)."
        )

        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": f"{instruction}\n{prompt}"},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{image_b64}"
                            },
                        },
                    ],
                },
            ],
            "temperature": 0.2,
            "max_tokens": 200,
        }

        req = request.Request(
            "https://openrouter.ai/api/v1/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
                "HTTP-Referer": "http://localhost",
                "X-Title": "Security Camera Dashboard",
            },
            method="POST",
        )

        try:
            with request.urlopen(req, timeout=45) as response:
                data = json.loads(response.read().decode("utf-8"))
        except error.HTTPError as e:
            logger.error(f"OpenRouter HTTP error: {e.read().decode('utf-8')}")
            return {
                "summary": "OpenRouter request failed.",
                "person_detected": None,
                "confidence": 0,
                "model": self.model,
                "error": f"http_{e.code}",
            }
        except Exception as e:
            logger.error(f"OpenRouter request error: {e}")
            return {
                "summary": "OpenRouter request failed.",
                "person_detected": None,
                "confidence": 0,
                "model": self.model,
                "error": "request_failed",
            }

        content = ""
        try:
            content = data["choices"][0]["message"]["content"]
        except Exception:
            content = ""

        self._daily_count += 1
        self._last_request_time = datetime.now()

        parsed = self._extract_json(content)
        if not parsed:
            return {
                "summary": content.strip()[:300] or "No analysis response.",
                "person_detected": None,
                "confidence": 0,
                "model": self.model,
                "error": "parse_failed",
            }

        person_detected = parsed.get("person_detected")
        if isinstance(person_detected, str):
            person_detected = person_detected.strip().lower() == "true"

        send_gif = parsed.get("send_gif")
        if isinstance(send_gif, str):
            send_gif = send_gif.strip().lower() == "true"

        return {
            "summary": str(parsed.get("summary", "")).strip(),
            "person_detected": person_detected,
            "confidence": int(parsed.get("confidence", 0) or 0),
            "importance": int(parsed.get("importance", 0) or 0),
            "send_gif": send_gif if send_gif is not None else None,
            "model": self.model,
            "error": None,
        }

    @staticmethod
    def _extract_json(text: str) -> Optional[dict]:
        if not text:
            return None
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None
        try:
            return json.loads(text[start:end + 1])
        except Exception:
            return None
