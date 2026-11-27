"""Entrées HTTP de l'édition de tags ; les règles résident dans AlbumTags."""
from .base import ok
from ..tag_entities import AlbumTagPatch, reference


class TagController:
    def __init__(self, tags):
        self.tags = tags

    def status(self, request, user):
        return ok(self.tags.status(user).to_api())

    def album(self, request, user):
        return ok(self.tags.snapshot(user, reference(request.param("id"))).to_api())

    def search(self, request, user):
        return ok(self.tags.search(user, reference(request.param("id")), request.param("source"),
                                   request.param("artist"), request.param("album")).to_api())

    def release(self, request, user):
        return ok(self.tags.release(user, reference(request.param("id")), request.param("source"),
                                    request.param("release")).to_api())

    def preview(self, request, user, body):
        return ok(self.tags.preview(user, AlbumTagPatch.parse(body)).to_api())

    def save(self, request, user, body):
        return ok(self.tags.save(user, AlbumTagPatch.parse(body)).to_api())

    def operation(self, request, user):
        return ok(self.tags.operation(user, request.param("id")).to_api())
