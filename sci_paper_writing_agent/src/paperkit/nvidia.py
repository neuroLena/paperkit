"""NVIDIA hosted models (build.nvidia.com) and self-hosted NIM, through the OpenAI-compatible chat endpoint.

Standard library only, so there is no extra dependency. Two things differ from the Anthropic path:
- the free hosted endpoints are rate limited, so HTTP 429 and 5xx are retried after a wait;
- the hosted gateway drops a connection that is silent for 300 s (HTTP 504), and a reasoning model
  thinks for longer than that before a plain answer starts, so answers are streamed: bytes flow
  while the model thinks. PAPERKIT_REASONING sets how much it thinks;
- open models do not always honour a JSON schema, so every answer is validated here and the model
  gets a chance to repair it. Schema-guided decoding is requested first and dropped for a model
  whose endpoint rejects it.
"""
from __future__ import annotations

import http.client
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

from pydantic import BaseModel, ValidationError

BASE_URL = "https://integrate.api.nvidia.com/v1"    # override with NVIDIA_BASE_URL for a local NIM
REPAIRS = 2                     # extra attempts when an answer does not fit the schema
BACKOFF = (2, 5, 15, 30)        # seconds to wait after HTTP 429 or 5xx, one entry per retry
TIMEOUT = 300                   # seconds without any bytes from the server; PAPERKIT_TIMEOUT overrides
STALL_RETRIES = 1               # a request that got no answer (timeout, HTTP 504, broken stream) is sent once more
RETRYABLE = {429, 500, 502, 503}
STALLED = ("The free endpoint is busy or this model is down: try again later, set PAPERKIT_REASONING=low, "
           "or use another model (`paperkit ping` tests each one)")
HINTS = {
    401: "the key was rejected: check NVIDIA_API_KEY",
    403: "this key has no access to the model",
    404: "model not found: copy the model ID from its page on build.nvidia.com",
    429: "rate limit reached: wait a minute and try again",
}
_NO_GUIDED: set[str] = set()    # models whose endpoint rejected nvext.guided_json


class ApiError(RuntimeError):
    def __init__(self, status: int, detail: str):
        super().__init__(f"HTTP {status}: {detail}" if status else detail)
        self.status, self.detail = status, detail


class Stalled(Exception):
    """The stream ended before the model finished. The gateway does this after 300 s of silence."""


def read_answer(response) -> dict:
    """The answer as one chat completion, whether the server sent plain JSON or a stream of events."""
    if "text/event-stream" not in (response.headers.get("Content-Type") or ""):
        return json.loads(response.read().decode("utf-8"))
    content, reasoning, finish = [], [], None
    for raw in response:
        line = raw.decode("utf-8", "replace").strip()
        if not line.startswith("data:"):
            continue                                    # blank separators and ": keep-alive" comments
        payload = line[5:].strip()
        if payload == "[DONE]":
            break
        try:
            event = json.loads(payload)
        except ValueError:
            continue
        if not isinstance(event, dict):
            continue
        if event.get("error") or (event.get("detail") and not event.get("choices")):
            error = event.get("error") or event
            detail = error.get("message") or error.get("detail") if isinstance(error, dict) else error
            status = event.get("status") or (error.get("code") if isinstance(error, dict) else 0)
            raise ApiError(int(status) if str(status).isdigit() else 0, " ".join(str(detail or event).split())[:300])
        for choice in event.get("choices") or []:
            delta = choice.get("delta") or {}
            content.append(delta.get("content") or "")
            reasoning.append(delta.get("reasoning_content") or delta.get("reasoning") or "")
            finish = choice.get("finish_reason") or finish
    if finish is None:
        raise Stalled()
    message = {"role": "assistant", "content": "".join(content), "reasoning_content": "".join(reasoning)}
    return {"choices": [{"message": message, "finish_reason": finish}]}


def reasoning() -> dict:
    """Request fields for PAPERKIT_REASONING: low, high or max set how much the model thinks, off stops it.

    GLM-5.3 always thinks and takes reasoning_effort (its default is max, the slowest).
    Models with a thinking switch (GLM-4.7 to GLM-5.2 and others) take enable_thinking.
    """
    level = (os.environ.get("PAPERKIT_REASONING") or "").strip().lower()
    if not level:
        return {}
    if level in ("off", "none", "false", "0"):
        return {"chat_template_kwargs": {"enable_thinking": False}}
    return {"reasoning_effort": level}


def post(url: str, key: str, body: dict) -> dict:
    """POSTs JSON and returns one chat completion. Retries rate limits, server errors and a request that stalled."""
    data = json.dumps(body).encode("utf-8")
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json",
               "Accept": "text/event-stream" if body.get("stream") else "application/json"}
    timeout = float(os.environ.get("PAPERKIT_TIMEOUT") or TIMEOUT)
    stalls = 0
    for wait in (*BACKOFF, None):
        request = urllib.request.Request(url, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return read_answer(response)
        except urllib.error.HTTPError as exc:
            detail = " ".join(exc.read().decode("utf-8", "replace").split())[:300]
            if exc.code != 504:
                if exc.code in RETRYABLE and wait is not None:
                    asked = exc.headers.get("Retry-After", "")
                    time.sleep(min(float(asked), 60) if asked.replace(".", "", 1).isdigit() else wait)
                    continue
                raise ApiError(exc.code, detail) from None
            why = "HTTP 504, the gateway got no answer from the model"
        except urllib.error.URLError as exc:
            if not isinstance(exc.reason, TimeoutError):
                raise ApiError(0, f"cannot reach {url}: {exc.reason}") from None
            why = f"no connection in {timeout:.0f} s"
        except TimeoutError:
            why = f"no bytes from the server for {timeout:.0f} s"
        except (Stalled, ConnectionError, http.client.HTTPException):
            why = "the answer stopped half way"
        stalls += 1
        if stalls > STALL_RETRIES:
            raise ApiError(0, f"{why}, {stalls} times. {STALLED}") from None
        print(f"  {body.get('model', 'model')}: {why}, trying once more", file=sys.stderr)
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
        body = {"model": model, "messages": messages, "max_tokens": max_tokens, "temperature": 0.2,
                "stream": os.environ.get("PAPERKIT_STREAM", "1") != "0", **reasoning()}
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
        message = choice.get("message") or {}
        text = message.get("content") or message.get("reasoning_content") or ""   # some servers put guided JSON there
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
