"""Outbound AI, image and search calls (standard library only). Secrets never leave the server."""
import base64
import json
import urllib.error
import urllib.request
from typing import Iterator

from .config import env
from .settings_store import effective_ai


class ProviderError(Exception):
    """Raised for upstream failures. `public` is safe to show users; `detail` is for the server log only."""

    def __init__(self, public: str, detail: str = ""):
        super().__init__(public)
        self.public = public
        self.detail = detail


class NotConfigured(ProviderError):
    pass


def _open(req: urllib.request.Request, timeout: int):
    try:
        return urllib.request.urlopen(req, timeout=timeout)
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read(400).decode("utf-8", "replace")
        except Exception:
            pass
        if e.code in (401, 403):
            raise ProviderError("The AI provider rejected the server's credentials. The owner should check the API key.", f"HTTP {e.code}: {body}")
        if e.code == 429:
            raise ProviderError("The AI provider is rate limiting requests. Try again in a moment.", f"HTTP 429: {body}")
        raise ProviderError("The AI provider returned an error. Try again.", f"HTTP {e.code}: {body}")
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise ProviderError("Could not reach the AI provider. Try again.", f"{type(e).__name__}: {e}")


def _sse_events(resp) -> Iterator[tuple[str, str]]:
    event, data = "message", []
    for raw in resp:
        line = raw.decode("utf-8", "replace").rstrip("\r\n")
        if not line:
            if data:
                yield event, "\n".join(data)
            event, data = "message", []
        elif line.startswith("event:"):
            event = line[6:].strip()
        elif line.startswith("data:"):
            data.append(line[5:].lstrip())
    if data:
        yield event, "\n".join(data)


def stream_chat(system: str, messages: list[dict], max_tokens: int = 4096) -> Iterator[str]:
    cfg = effective_ai()
    e = env()
    if not e.ai_api_key:
        raise NotConfigured("The AI provider is not configured. The owner must set AI_API_KEY.")
    if cfg["provider"] == "anthropic":
        body = {"model": cfg["model"], "max_tokens": max_tokens, "system": system, "messages": messages, "stream": True}
        req = urllib.request.Request(cfg["base_url"] + "/v1/messages", data=json.dumps(body).encode(), method="POST",
                                     headers={"content-type": "application/json", "x-api-key": e.ai_api_key,
                                              "anthropic-version": "2023-06-01"})
        with _open(req, 120) as resp:
            for event, data in _sse_events(resp):
                if event == "error":
                    raise ProviderError("The AI provider reported an error. Try again.", data[:300])
                if event == "content_block_delta":
                    try:
                        d = json.loads(data).get("delta", {})
                    except json.JSONDecodeError:
                        continue
                    if d.get("type") == "text_delta" and d.get("text"):
                        yield d["text"]
    else:
        body = {"model": cfg["model"], "stream": True, "max_tokens": max_tokens,
                "messages": [{"role": "system", "content": system}] + messages}
        req = urllib.request.Request(cfg["base_url"] + "/chat/completions", data=json.dumps(body).encode(), method="POST",
                                     headers={"content-type": "application/json", "authorization": "Bearer " + e.ai_api_key})
        with _open(req, 120) as resp:
            for _event, data in _sse_events(resp):
                if data.strip() == "[DONE]":
                    return
                try:
                    choices = json.loads(data).get("choices") or [{}]
                except json.JSONDecodeError:
                    continue
                text = (choices[0].get("delta") or {}).get("content")
                if text:
                    yield text


def web_search(query: str, max_results: int = 5) -> list[dict]:
    e = env()
    if not e.search_api_key:
        raise NotConfigured("Web search is not configured. The owner must set SEARCH_API_KEY.")
    req = urllib.request.Request(e.search_base_url + "/search", method="POST",
                                 data=json.dumps({"query": query[:400], "max_results": max_results}).encode(),
                                 headers={"content-type": "application/json", "authorization": "Bearer " + e.search_api_key})
    with _open(req, 30) as resp:
        data = json.loads(resp.read(2_000_000))
    out = []
    for r in data.get("results", [])[:max_results]:
        url = str(r.get("url", ""))
        if url.startswith(("http://", "https://")):
            out.append({"title": str(r.get("title", url))[:200], "url": url, "snippet": str(r.get("content", ""))[:700]})
    return out


def generate_image(prompt: str) -> bytes:
    e = env()
    if not e.image_api_key:
        raise NotConfigured("Image generation is not configured. The owner must set IMAGE_API_KEY.")
    req = urllib.request.Request(e.image_base_url + "/images/generations", method="POST",
                                 data=json.dumps({"model": e.image_model, "prompt": prompt, "n": 1, "size": "1024x1024"}).encode(),
                                 headers={"content-type": "application/json", "authorization": "Bearer " + e.image_api_key})
    with _open(req, 180) as resp:
        data = json.loads(resp.read(40_000_000))
    items = data.get("data") or []
    b64 = items[0].get("b64_json") if items else None
    if not b64:
        raise ProviderError("The image provider did not return an image. Try a different prompt.", "no b64_json in response")
    try:
        raw = base64.b64decode(b64, validate=True)
    except Exception:
        raise ProviderError("The image provider returned unreadable data.", "bad base64")
    return raw
