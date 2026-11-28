"""Reconnaissance des images binaires, indépendante des en-têtes envoyés par les sites."""

SIGNATURES = ((b"\x89PNG\r\n\x1a\n", "image/png"), (b"\xff\xd8\xff", "image/jpeg"), (b"RIFF", "image/webp"),
              (b"GIF87a", "image/gif"), (b"GIF89a", "image/gif"))


def image_type(data):
    for signature, mime in SIGNATURES:
        if data.startswith(signature) and (mime != "image/webp" or data[8:12] == b"WEBP"):
            return mime
    return None
