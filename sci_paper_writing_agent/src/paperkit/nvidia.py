"""NVIDIA hosted models (build.nvidia.com) and self-hosted NIM, through the OpenAI-compatible chat endpoint.

Standard library only, so there is no extra dependency. Two things differ from the Anthropic path:
- the free hosted endpoints are rate limited, so HTTP 429 and 5xx are retried after a wait;
- open models do not always honour a JSON schema, so every answer is validated here and the model
  gets a chance to repair it. Schema-guided decoding is requested first and dropped for a model
  whose endpoint rejects it.
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request

from pydantic import BaseModel, ValidationError

BASE_URL = "https://integrate.api.nvidia.com/v1"    # override with NVIDIA_BASE_URL for a local NIM
REPAIRS = 2                     # extra attempts when an answer does not fit the schema
BACKOFF = (2, 5, 15, 30)        # seconds to wait after HTTP 429 or 5xx, one entry per retry
TIMEOUT = 300
RETRYABLE = {429, 500, 502, 503, 504}
HINTS = {
    401: "the key was rejected: check NVIDIA_API_KEY",
    403: "this key has no access to the model",
    404: "model not found: copy the model ID from its page on build.nvidia.com",
    429: "rate limit reached: wait a minute and try again",
}
_NO_GUIDED: set[str] = set()    # models whose endpoint rejected nvext.guided_json


class ApiError(RuntimeError):
    def __init__(self, status: int, detail: str):
        super().__init__(f"HTTP {status}: {detail}")
        self.status, self.detail = status, detail


def post(url: str, key: str, body: dict) -> dict:
    """POSTs JSON and returns the decoded answer. Waits and retries on rate limits and server errors."""
    data = json.dumps(body).encode("utf-8")
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json", "Accept": "application/json"}
    for wait in (*BACKOFF, None):
        request = urllib.request.Request(url, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = " ".join(exc.read().decode("utf-8", "replace").split())[:300]
            if exc.code in RETRYABLE and wait is not None:
                asked = exc.headers.get("Retry-After", "")
                time.sleep(min(float(asked), 60) if asked.replace(".", "", 1).isdigit() else wait)
                continue
            raise ApiError(exc.code, detail) from None
        except urllib.error.URLError as exc:
            raise ApiError(0, f"cannot reach {url}: {exc.reason}") from None
    raise ApiError(0, "no answer")      # not reached: the last round always returns or raises


def extract_json(text: str) -> str:
    """The JSON object inside a model answer. Reasoning blocks, code fences and chatter are dropped."""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S)
    start, end = text.find("{"), text.rfind("}")
    return text[start:end + 1] if 0 <= start < end else text.strip()


def call(system: str, user: str, schema: type[BaseModel], model: str, max_tokens: int = 8000) -> BaseModel:
    """One request with no history, answered as a validated instance of `schema`."""
    key = os.environ.get("NVIDIA_API_KEY")
    if not key:
        raise RuntimeError("NVIDIA_API_KEY is not set. Get a key at build.nvidia.com and put it in .env.")
    url = (os.environ.get("NVIDIA_BASE_URL") or BASE_URL).rstrip("/") + "/chat/completions"
    json_schema = schema.model_json_schema()
    messages = [
        {"role": "system", "content": f"{system}\n\nAnswer with one JSON object and nothing else. "
                                      f"It must be valid for this JSON schema:\n{json.dumps(json_schema)}"},
        {"role": "user", "content": user},
    ]
    problem, attempts = "", 0
    while attempts <= REPAIRS:
        body = {"model": model, "messages": messages, "max_tokens": max_tokens, "temperature": 0.2, "stream": False}
        guided = model not in _NO_GUIDED and os.environ.get("PAPERKIT_GUIDED_JSON", "1") != "0"
        if guided:
            body["nvext"] = {"guided_json": json_schema}
        try:
            data = post(url, key, body)
        except ApiError as exc:
            if guided and exc.status in (400, 422):
                _NO_GUIDED.add(model)   # this endpoint does not take guided_json: rely on the prompt and on validation
                continue
            raise RuntimeError(f"NVIDIA API, model {model}: {HINTS.get(exc.status, exc)}") from None
        attempts += 1
        choice = (data.get("choices") or [{}])[0]
        if choice.get("finish_reason") == "length":
            raise RuntimeError("Answer was cut off: raise PAPERKIT_MAX_TOKENS")
        text = (choice.get("message") or {}).get("content") or ""
        try:
            return schema.model_validate_json(extract_json(text))
        except ValidationError as exc:
            problem = " ".join(str(exc).split())[:600]
            messages = messages[:2] + [
                {"role": "assistant", "content": text[:6000] or "(empty answer)"},
                {"role": "user", "content": f"That answer is not valid for the schema: {problem}\n"
                                            "Return only the corrected JSON object."},
            ]
    raise RuntimeError(f"{model} gave no valid {schema.__name__} after {REPAIRS + 1} attempts: {problem}")
