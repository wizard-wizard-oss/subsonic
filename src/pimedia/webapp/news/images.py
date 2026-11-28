"""Image d'un article RSS/Atom : média déclaré, pièce jointe ou première vraie image HTML."""
import ipaddress
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit, urldefrag

MAX_IMAGE_URL = 4096
HTML_FIELDS = {"description", "summary", "content", "encoded"}


def image_address(value, base):
    if not value or len(value) > MAX_IMAGE_URL or any(char.isspace() or ord(char) < 32 for char in value):
        return ""
    try:
        url = urldefrag(urljoin(base, value))[0]
        parts = urlsplit(url)
        host = parts.hostname
        if parts.scheme not in ("http", "https") or not host or parts.username or parts.password:
            return ""
        if host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
            return ""
        try:
            if not ipaddress.ip_address(host).is_global:
                return ""
        except ValueError:
            pass
        return url
    except ValueError:
        return ""


class _HtmlImages(HTMLParser):
    def __init__(self, base):
        super().__init__()
        self.base, self.image = base, ""

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag != "img" or self.image or values.get("width") == "1" or values.get("height") == "1":
            return
        self.image = next((url for name in ("src", "data-src")
                           if (url := image_address(values.get(name), self.base))), "")


def _media_image(node, base):
    for child in node.iter():
        tag = child.tag.rsplit("}", 1)[-1] if isinstance(child.tag, str) else ""
        media = "search.yahoo.com/mrss" in str(child.tag) or tag.startswith("media_")
        local = tag.removeprefix("media_")
        picture = local == "thumbnail" or (local in ("content", "enclosure", "link") and
                  (child.get("medium") == "image" or child.get("type", "").startswith("image/") or
                   media and child.get("medium", "image") == "image"))
        if picture and (url := image_address(child.get("url") or child.get("href"), base)):
            return url
    return ""


def article_image(node, base):
    media = _media_image(node, base)
    if media:
        return media
    for child in node:
        tag = child.tag.rsplit("}", 1)[-1] if isinstance(child.tag, str) else ""
        if tag not in HTML_FIELDS:
            continue
        parser = _HtmlImages(base)
        parser.feed(child.text or "")
        if parser.image:
            return parser.image
        for image in child.iter():
            if str(image.tag).rsplit("}", 1)[-1] == "img" and (url := image_address(image.get("src"), base)):
                return url
    return ""
