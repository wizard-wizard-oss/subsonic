"""Shared SQL projection for a saved musical reference."""
COLUMNS = "kind, source, library_key, source_id, title, artist, image_ref"


def values(target):
    return target.key + (target.title, target.artist, target.image_ref)
