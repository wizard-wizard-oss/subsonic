"""Sorties annoncées dans MusicBrainz et styles suivis par compte."""
from dataclasses import replace
from datetime import date, timedelta

from ...shared.providers.musicbrainz.entities import ReleaseGenre


class WeeklyReleases:
    PAGE_SIZE = 24
    DEFAULT_GENRE = "noise rock"          # style proposé à qui n'en suit encore aucun
    MAX_OFFSET = 10 * PAGE_SIZE
    WINDOW = timedelta(days=366)        # semaines consultables autour d'aujourd'hui

    def __init__(self, musicbrainz, repository, today=date.today):
        self.musicbrainz = musicbrainz
        self.repository = repository
        self.today = today

    def genres(self):
        return self.musicbrainz.release_genres()

    def genre(self, name):
        match = next((genre for genre in self.genres() if genre.name == name), None)
        if match is None:
            raise ValueError("genre")
        return match

    def followed(self, user):
        return tuple(ReleaseGenre(name) for name in self.repository.for_user(user.id))

    def follow(self, user, name, enabled):
        if not isinstance(enabled, bool) or not isinstance(name, str) or not name:
            raise ValueError("follow")
        if enabled:
            self.repository.follow(user.id, self.genre(name).name)
        else:
            self.repository.unfollow(user.id, name)

    def week(self, name, start, offset):
        monday = date.fromisoformat(start or "")
        if monday.weekday() or abs(monday - self.today()) > self.WINDOW:
            raise ValueError("week")
        if offset % self.PAGE_SIZE or not 0 <= offset <= self.MAX_OFFSET:
            raise ValueError("week")
        sunday = monday + timedelta(days=6)
        genre = self.genre(name)
        page = self.musicbrainz.weekly_groups(genre.name, monday, sunday, self.PAGE_SIZE, offset)
        return replace(page, albums=tuple(album for album in page.albums if monday <= album.released_on <= sunday))
