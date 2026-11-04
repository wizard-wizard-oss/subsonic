"""Page d'accueil et fichiers statiques."""
from ..transport import Reply


class PagesController:
    def __init__(self, web_files):
        self.web_files = web_files

    def index(self, request):
        return Reply.from_web_file(self.web_files.index(request.header("If-None-Match")))

    def page(self, name, request):
        return Reply.from_web_file(self.web_files.page(name, request.header("If-None-Match")))

    def static(self, request):
        web_file = self.web_files.static(request.path, request.query_string,
                                         request.header("If-None-Match"), request.header("Accept-Encoding"))
        return Reply.from_web_file(web_file)
