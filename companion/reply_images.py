"""In-memory reply pictures. Untrusted URLs never reach local network services."""
from __future__ import annotations

import base64
import http.client
import io
import ipaddress
import re
import socket
import ssl
import time
from urllib.parse import urljoin, urlsplit

from .core import Answer, ReplyImage, SYSTEM, UserError, build_request, request_json

MAX_IMAGE_BYTES = 8_000_000
MAX_IMAGES = 3
IMAGE_MODELS = {
    "OpenAI": ("gpt-image-2.5-flare", "gpt-image-2.5-sunburst", "gpt-image-1.5"),
    "Gemini": ("gemini-nano-banana-2.1", "gemini-3.1-flash-lite-image", "gemini-3-pro-image"),
}
IMAGE_MARKDOWN = re.compile(r"!\[([^\]\n]{0,160})\]\((https://[^\s<>)]{1,2048})\)")


def extract_images(text):
    images, seen = [], set()
    def replace(match):
        caption, url = match.groups()
        if url not in seen and len(images) < MAX_IMAGES:
            seen.add(url)
            images.append(ReplyImage(None, caption or "网页配图", url))
            return ""
        return "[其余配图已省略]"
    return IMAGE_MARKDOWN.sub(replace, text).strip(), images


def normalize_image(raw):
    from PIL import Image, UnidentifiedImageError
    if not raw or len(raw) > MAX_IMAGE_BYTES:
        raise UserError("图片为空或超过 8 MB。")
    try:
        with Image.open(io.BytesIO(raw)) as image:
            if image.format not in ("PNG", "JPEG", "WEBP", "GIF"):
                raise UserError("仅显示 PNG、JPEG、WebP 或 GIF 首帧。")
            if image.width * image.height > 20_000_000:
                raise UserError("图片分辨率过大。")
            image.load()
            image.thumbnail((2048, 2048))
            image = image.convert("RGB")
            output = io.BytesIO()
            image.save(output, "PNG")
            result = output.getvalue()
            if len(result) > MAX_IMAGE_BYTES:
                raise UserError("图片解码后过大。")
            return result
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        raise UserError("无法显示这张图片。") from None


def decode_image(encoded):
    if not isinstance(encoded, str) or len(encoded) > (MAX_IMAGE_BYTES * 4 // 3 + 4):
        raise UserError("图片数据无效或过大。")
    try:
        return normalize_image(base64.b64decode(encoded, validate=True))
    except (ValueError, TypeError):
        raise UserError("图片编码无效。") from None


def public_image_target(url, *, resolver=None):
    try:
        parts = urlsplit(url)
        host = (parts.hostname or "").encode("idna").decode("ascii")
        if (parts.scheme != "https" or not host or parts.username or parts.password
                or parts.port not in (None, 443) or parts.fragment or len(url) > 4096
                or any(ord(c) <= 32 or ord(c) == 127 for c in url) or "\\" in url):
            raise ValueError()
        addresses = (resolver or socket.getaddrinfo)(host, 443, type=socket.SOCK_STREAM)
        if not addresses or any(not ipaddress.ip_address(x[4][0]).is_global for x in addresses):
            raise ValueError()
        return host, addresses[0], (parts.path or "/") + ("?" + parts.query if parts.query else "")
    except (ValueError, UnicodeError, OSError):
        raise UserError("配图地址不是可访问的公开 HTTPS 图片地址。") from None


class PublicImageConnection(http.client.HTTPSConnection):
    def __init__(self, host, address, timeout):
        super().__init__(host, timeout=timeout, context=ssl.create_default_context())
        self.address = address

    def connect(self):
        # Connect to the exact checked address; do not re-resolve after validation.
        family, socktype, proto, _, sockaddr = self.address
        raw = socket.socket(family, socktype, proto)
        try:
            raw.settimeout(self.timeout)
            raw.connect(sockaddr)
            self.sock = self._context.wrap_socket(raw, server_hostname=self.host)
        except BaseException:
            raw.close()
            raise


def download_image(url, *, resolver=None, connection_factory=None):
    deadline = time.monotonic() + 20
    try:
        for _ in range(3):
            host, address, path = public_image_target(url, resolver=resolver)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise UserError("配图下载超时。")
            connection = (connection_factory or PublicImageConnection)(host, address, min(8, remaining))
            try:
                connection.request("GET", path, headers={"User-Agent": "ForeverAI/0.4", "Accept": "image/png,image/jpeg,image/webp,image/gif"})
                response = connection.getresponse()
                if response.status in (301, 302, 303, 307, 308):
                    location = response.getheader("Location")
                    if not location:
                        raise UserError("配图重定向无效。")
                    url = urljoin(url, location)
                    continue  # Validate every redirect, including DNS and protocol.
                mime = response.getheader("Content-Type", "").split(";")[0].strip().lower()
                if response.status != 200 or mime not in ("image/png", "image/jpeg", "image/webp", "image/gif"):
                    raise UserError("该地址没有返回可显示的图片。")
                data = bytearray()
                while len(data) <= MAX_IMAGE_BYTES:
                    if time.monotonic() > deadline:
                        raise UserError("配图下载超时。")
                    chunk = response.read(min(64_000, MAX_IMAGE_BYTES + 1 - len(data)))
                    if not chunk:
                        break
                    data.extend(chunk)
                return normalize_image(bytes(data))
            finally:
                connection.close()
        raise UserError("配图重定向次数过多。")
    except (OSError, http.client.HTTPException, ValueError):
        raise UserError("配图下载失败；文字回答仍可阅读。") from None


def resolve_images(answer, *, downloader=None):
    for image in answer.images[:MAX_IMAGES]:
        if image.png is None and image.url:
            try:
                image.png = (downloader or download_image)(image.url)
            except UserError as exc:
                answer.warnings.append("配图未加载：" + str(exc))
    return answer


def generate_image(provider, key, model, prompt, *, snapshot=None, history=(), transport=None):
    if provider not in IMAGE_MODELS:
        raise UserError("生成图片请选择 OpenAI 或 Gemini；Claude 只能提供文字和来源配图。")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,149}", model):
        raise UserError("请填写有效的图片模型 ID。")
    # Reuse the same bounded snapshot/history validation as ordinary chat.
    _, context = build_request("OpenAI", "context-only", prompt, snapshot=snapshot, history=history, search=False)
    instruction = ("Create ONE explanatory illustration, not a factual game screenshot. "
                   "Label it AI 示意图. Do not invent WoW map coordinates or claim verified geography.\n")
    text = instruction + json_context(context)
    if provider == "OpenAI":
        url = "https://api.openai.com/v1/images/generations"
        body = {"model": model, "prompt": text[:32000], "n": 1, "size": "1024x1024", "quality": "low", "output_format": "png"}
    else:
        url = "https://generativelanguage.googleapis.com/v1beta/interactions"
        body = {"model": model, "input": text, "system_instruction": SYSTEM, "store": False,
                "response_format": {"type": "image", "aspect_ratio": "1:1", "image_size": "1K"}}
    data = request_json(provider, key, url, body, transport=transport, timeout=180, limit=24_000_000)
    images, texts = [], []
    if provider == "OpenAI":
        for item in data.get("data", [])[:1]:
            images.append(ReplyImage(decode_image(item.get("b64_json")), "AI 示意图", generated=True))
    else:
        for step in data.get("steps", []):
            if step.get("type") != "model_output":
                continue  # Never render thought text or thought images.
            for part in step.get("content", []):
                if part.get("type") == "text":
                    texts.append(str(part.get("text", "")))
                elif part.get("type") == "image" and not images:
                    images.append(ReplyImage(decode_image(part.get("data")), "AI 示意图", generated=True))
    if not images:
        raise UserError("模型没有返回图片，可能不支持生图或本次被拒绝。没有自动重试。")
    return Answer("\n".join(texts) or "AI 示意图 · 不能作为真实游戏地图或掉落证据。", images=images)


def json_context(context):
    import json
    return json.dumps(context["input"], ensure_ascii=False)
