"""Envoi de fichiers audio (ou d'un zip, décompressé) dans le dossier Incoming de Subsonic."""
from ...server.transport import Reply
from ..uploads import UploadError
from .base import ok


class UploadController:
    def __init__(self, uploads):
        self.uploads = uploads

    def status(self, request, user):
        return ok(self.uploads.status(user))

    def upload(self, request, user):
        """Corps brut = le fichier ; son nom dans ?name=. Un refus ferme la connexion : le corps n'est pas lu."""
        request.set_timeout(300)                         # un gros zip : décompression comprise
        try:
            saved = self.uploads.save(user, request.rfile, request.content_length, request.param("name"))
        except UploadError as error:
            reply = Reply.error(400, error.args[0])
            reply.close_connection = True
            return reply
        return ok(saved)

    def finish(self, request, user, body):
        """Après un lot de fichiers : Subsonic scanne pour les faire apparaître."""
        return ok({"scanning": self.uploads.scan(user)})
