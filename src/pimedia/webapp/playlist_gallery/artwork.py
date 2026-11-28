"""Sélection stable des pochettes, commune à la galerie et au détail d'une playlist."""
MAX_COVERS = 4


def album_covers(songs):
    covers, albums = [], set()
    for song in songs:
        cover = song.get("coverId")
        album = song.get("albumId") or cover
        if song.get("ext") or not cover or album in albums:
            continue
        albums.add(album)
        covers.append(cover)
        if len(covers) == MAX_COVERS:
            break
    if len(covers) < 2:
        return covers
    return [covers[i % len(covers)] for i in range(MAX_COVERS)]
