"""Build an agent message that carries a mockup image for the model to read.

The branding agent extracts the printed text / medium by *looking at* the image.
How the image travels depends on the link scheme:

  * ``gs://…`` Cloud Storage URIs are passed BY REFERENCE — a Gemini ``file_data``
    part carrying the URI. Only the link travels; Vertex loads the bytes.
  * ``http(s)://…`` URLs are NOT fetched by Vertex (they come back empty), so the
    bytes are downloaded here and sent INLINE.
"""

import json
import mimetypes
import re
import urllib.request

from google.genai import types
from google.adk.models import LlmResponse

# A gs:// or http(s) link, as it might appear typed into a chat message OR embedded
# in a JSON request. Exclude quotes/commas/brackets/whitespace so we don't swallow
# the JSON tail (e.g. `gs://…jpg","target_market":"…`).
_URI_RE = re.compile(r'(gs://[^\s"\'<>,;)\]}]+|https?://[^\s"\'<>,;)\]}]+)')


def _download(url: str) -> tuple[bytes, str]:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = resp.read()
        mime = resp.headers.get_content_type() or "image/jpeg"
    return data, mime


def image_part(image_uri: str) -> types.Part | None:
    """A Gemini Part for the image: file_data (link) for gs://, inline bytes for http(s)."""
    if not image_uri:
        return None
    if image_uri.startswith("gs://"):
        mime = mimetypes.guess_type(image_uri.split("?", 1)[0])[0] or "image/png"
        return types.Part.from_uri(file_uri=image_uri, mime_type=mime)
    if image_uri.startswith("http"):
        try:
            data, mime = _download(image_uri)
        except Exception:
            # Unreachable/expired/403 URL → treat as no image (agent will ask),
            # rather than crashing the caller building the message.
            return None
        return types.Part.from_bytes(data=data, mime_type=mime)
    return None


def content_with_image(text: str, image_uri: str | None) -> types.Content:
    """A user Content of the text plus, when available, the image."""
    parts = [types.Part.from_text(text=text)]
    part = image_part(image_uri) if image_uri else None
    if part is not None:
        parts.append(part)
    return types.Content(role="user", parts=parts)


def _request_has_image(llm_request) -> bool:
    for content in getattr(llm_request, "contents", None) or []:
        for part in getattr(content, "parts", None) or []:
            if getattr(part, "inline_data", None) or getattr(part, "file_data", None):
                return True
    return False


def _find_image_uri(llm_request, callback_context) -> str | None:
    """Look for an image LINK in session state or the message text."""
    try:
        uri = (callback_context.state.get("image_uri") if callback_context else None) or ""
    except Exception:
        uri = ""
    if uri:
        return uri
    for content in getattr(llm_request, "contents", None) or []:
        for part in getattr(content, "parts", None) or []:
            text = getattr(part, "text", None)
            if text:
                m = _URI_RE.search(text)
                if m:
                    return m.group(1).rstrip(".,);]'\"")
    return None


def require_image_before_model(callback_context, llm_request):
    """before_model_callback: ensure a real image is present before the model runs.

    Vision agents invent plausible text when handed no image, so this guard checks
    for an actual image part. If there is none but the message/state carries an
    image LINK, it resolves the link into an image part (file_data for gs://,
    downloaded+inline for http) so the model can genuinely read it. Only when there
    is neither an image nor a link does it short-circuit to needs_input.
    """
    if _request_has_image(llm_request):
        return None

    uri = _find_image_uri(llm_request, callback_context)
    if uri:
        try:
            part = image_part(uri)
        except Exception:
            part = None
        if part is not None:
            contents = llm_request.contents or []
            if contents and getattr(contents[-1], "parts", None) is not None:
                contents[-1].parts.append(part)
            else:
                contents.append(types.Content(role="user", parts=[part]))
            llm_request.contents = contents
            return None  # image resolved from the link → let the model read it

    payload = json.dumps({
        "agent": "brand_style_compliance_agent",
        "status": "needs_input",
        "needs": ["image"],
        "question": (
            "Please provide the mockup image (attach it, or give an approved "
            "gs:// Cloud Storage link) — I won't guess its contents without seeing it."
        ),
    })
    return LlmResponse(content=types.Content(role="model", parts=[types.Part.from_text(text=payload)]))
