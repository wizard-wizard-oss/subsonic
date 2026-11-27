"""Sorties annoncées dans MusicBrainz et styles suivis par compte."""
from dataclasses import replace
from datetime import date, timedelta

from .weekly_release_entities import ReleaseGenre


class WeeklyReleases:
    PAGE_SIZE = 24

    def __init__(self, musicbrainz, repository):
        self.musicbrainz = musicbrainz
        self.repository = repository

    def genres(self):
        return self.musicbrainz.release_genres()

    def genre(self, identity):
        match = next((genre for genre in self.genres() if genre.id == identity), None)
        if match is None:
            raise ValueError("genre")
        return match

    def followed(self, user):
        names = dict.fromkeys(genre.name for genre in self.repository.for_user(user.id))
        return tuple(ReleaseGenre.from_name(name) for name in names)

    def follow(self, user, identity, enabled):
        if not isinstance(enabled, bool) or not isinstance(identity, str) or not identity:
            raise ValueError("follow")
        if enabled:
            self.repository.follow(user.id, self.genre(identity))
        else:
            subscription = next((genre for genre in self.repository.for_user(user.id)
                                 if identity in (genre.id, ReleaseGenre.from_name(genre.name).id)), None)
            if subscription is not None:
                self.repository.unfollow(user.id, subscription.name)

    def week(self, identity, start, offset):
        monday = date.fromisoformat(start or "")
        if monday.weekday() or not 0 <= offset <= 100000 or monday.year >= 9999:
            raise ValueError("week")
        sunday = monday + timedelta(days=6)
        genre = self.genre(identity)
        page = self.musicbrainz.weekly_groups(genre.name, monday, sunday, self.PAGE_SIZE, offset)
        return replace(page, albums=tuple(album for album in page.albums if monday <= album.released_on <= sunday))
