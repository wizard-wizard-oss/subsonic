"""Sorties annoncées dans MusicBrainz et styles suivis par compte."""
from dataclasses import replace
from datetime import date, timedelta

from .musicbrainz import mbid


class WeeklyReleases:
    PAGE_SIZE = 24

    def __init__(self, musicbrainz, repository):
        self.musicbrainz = musicbrainz
        self.repository = repository

    def genres(self):
        return self.musicbrainz.release_genres()

    def genre(self, identity):
        identity = mbid(identity)
        match = next((genre for genre in self.genres() if genre.id == identity), None)
        if match is None:
            raise ValueError("genre")
        return match

    def followed(self, user):
        return self.repository.for_user(user.id)

    def follow(self, user, identity, enabled):
        if not isinstance(enabled, bool):
            raise ValueError("follow")
        if enabled:
            self.repository.follow(user.id, self.genre(identity))
        else:
            self.repository.unfollow(user.id, mbid(identity))

    def week(self, identity, start, offset):
        monday = date.fromisoformat(start or "")
        if monday.weekday() or not 0 <= offset <= 100000 or monday.year >= 9999:
            raise ValueError("week")
        sunday = monday + timedelta(days=6)
        genre = self.genre(identity)
        page = self.musicbrainz.weekly_groups(genre.name, monday, sunday, self.PAGE_SIZE, offset)
        return replace(page, albums=tuple(album for album in page.albums if monday <= album.released_on <= sunday))
