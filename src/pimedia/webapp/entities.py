"""Entités de l'édition PC. Les dépôts les renvoient ; to_api() donne le JSON envoyé à la page."""
import json
from dataclasses import dataclass, field
from typing import Optional

GENERAL_TOPIC = "general"
ALBUM_TOPIC_PREFIX = "album:"


def album_topic(album_id):
    return ALBUM_TOPIC_PREFIX + album_id


def album_of_topic(topic):
    return topic[len(ALBUM_TOPIC_PREFIX):] if topic.startswith(ALBUM_TOPIC_PREFIX) else None


# Droits d'un compte Subsonic (réponse de getUser) -> nom court utilisé par le site et la page.
SUBSONIC_ROLES = {"adminRole": "admin", "settingsRole": "settings", "streamRole": "stream", "downloadRole": "download",
                  "uploadRole": "upload", "playlistRole": "playlist", "coverArtRole": "coverArt",
                  "commentRole": "comment", "podcastRole": "podcast", "jukeboxRole": "jukebox", "shareRole": "share",
                  "videoConversionRole": "videoConversion", "scrobblingEnabled": "scrobble"}


def roles_of_subsonic(user):
    """Droits accordés dans la réponse de getUser."""
    return frozenset(name for field, name in SUBSONIC_ROLES.items() if user.get(field) is True)


def roles_of_text(value):
    return frozenset(r for r in (value or "").split(",") if r in SUBSONIC_ROLES.values())


def roles_to_text(roles):
    return ",".join(sorted(roles))


@dataclass
class User:
    id: int
    username: str
    subsonic_salt: str
    subsonic_token: str
    is_admin: bool = False
    created_at: int = 0
    last_seen_at: int = 0
    roles: frozenset = frozenset()         # droits du compte Subsonic (SUBSONIC_ROLES), relus à chaque page

    @classmethod
    def from_row(cls, row):
        return cls(row["id"], row["username"], row["subsonic_salt"], row["subsonic_token"], bool(row["is_admin"]),
                   row["created_at"], row["last_seen_at"], roles_of_text(row["roles"]))

    def can(self, role):
        return role in self.roles

    def to_api(self):
        """Jamais le jeton Subsonic."""
        return {"id": self.id, "username": self.username, "isAdmin": self.is_admin, "roles": sorted(self.roles)}


@dataclass
class Attachment:
    """Album ou titre partagé dans un message (carte cliquable)."""
    kind: str                 # « album » ou « song »
    id: str
    title: str
    artist: str = ""
    album_id: str = ""
    cover_id: str = ""

    KINDS = ("album", "song")

    @classmethod
    def parse(cls, data):
        """Depuis la page : None si absent ou invalide. Les textes sont bornés."""
        if not isinstance(data, dict) or data.get("kind") not in cls.KINDS or not data.get("id"):
            return None

        def text(key, limit=200):
            return str(data.get(key) or "")[:limit]
        return cls(data["kind"], text("id", 100), text("title") or "?", text("artist"), text("albumId", 100),
                   text("coverId", 100))

    @classmethod
    def from_json(cls, raw):
        if not raw:
            return None
        data = json.loads(raw)
        return cls(data["kind"], data["id"], data["title"], data.get("artist", ""), data.get("albumId", ""),
                   data.get("coverId", ""))

    def to_api(self):
        return {"kind": self.kind, "id": self.id, "title": self.title, "artist": self.artist,
                "albumId": self.album_id, "coverId": self.cover_id}

    def to_json(self):
        return json.dumps(self.to_api(), ensure_ascii=False)


@dataclass
class ReplyPreview:
    id: int
    author: str
    excerpt: str
    deleted: bool = False

    def to_api(self):
        return {"id": self.id, "author": self.author, "excerpt": self.excerpt, "deleted": self.deleted}


@dataclass
class ChatMessage:
    id: int
    topic: str
    user_id: int
    author: str
    body: str
    created_at: int
    edited_at: Optional[int] = None
    deleted_at: Optional[int] = None
    attachment: Optional[Attachment] = None
    reply_to: Optional[ReplyPreview] = None
    reactions: dict = field(default_factory=dict)       # emoji -> [noms]
    mentions: list = field(default_factory=list)        # noms mentionnés

    @property
    def deleted(self):
        return self.deleted_at is not None

    def to_api(self):
        data = {"id": self.id, "topic": self.topic, "userId": self.user_id, "author": self.author,
                "createdAt": self.created_at, "editedAt": self.edited_at, "deleted": self.deleted,
                "replyTo": self.reply_to.to_api() if self.reply_to else None}
        if self.deleted:                  # contenu d'un message supprimé : jamais renvoyé
            data.update(body="", attachment=None, reactions={}, mentions=[])
        else:
            data.update(body=self.body, attachment=self.attachment.to_api() if self.attachment else None,
                        reactions=self.reactions, mentions=self.mentions)
        return data


@dataclass
class RatingSummary:
    """Note d'un album dans Subsonic : la mienne (userRating) et la moyenne de tous les comptes (averageRating)."""
    album_id: str
    mine: int = 0              # 0 : pas noté
    average: float = 0.0       # 0 : personne n'a noté

    def to_api(self):
        return {"albumId": self.album_id, "mine": self.mine, "average": round(self.average, 2)}


@dataclass
class DiscussedAlbum:
    album_id: str
    title: str
    artist: str
    cover_id: str
    last_message_at: int
    comments: int = 0

    def to_api(self):
        return {"id": self.album_id, "title": self.title, "artist": self.artist, "coverId": self.cover_id,
                "lastMessageAt": self.last_message_at, "comments": self.comments}


@dataclass(frozen=True)
class LibraryStatistics:
    """Collection globale du serveur : valeurs persistées par Subsonic, date du scan en millisecondes."""
    artists: int
    albums: int
    songs: int
    total_bytes: int
    duration_seconds: int
    last_scan: int

    def to_api(self):
        return {"artists": self.artists, "albums": self.albums, "songs": self.songs,
                "bytes": self.total_bytes, "seconds": self.duration_seconds, "lastScan": self.last_scan}


@dataclass
class ArtistIndex:
    """Liste des artistes de la barre, la même pour tous les comptes qui voient les mêmes dossiers de musique."""
    folders: str                 # dossiers de musique visibles (« 1,2 ») : la liste en dépend
    artists: list                # [{"letter", "artists": [{"id", "name", "albumCount"}]}]
    since: int                   # date Subsonic (ms) à comparer au dernier scan (getIndexes ifModifiedSince)
    built_at: int


@dataclass
class NewsFeed:
    """Flux RSS ou Atom d'un webzine, suivi par tout le site (page Actualité, articles d'un artiste)."""
    id: int
    url: str
    title: str
    site_url: str
    added_by: Optional[int]
    added_at: int
    checked_at: Optional[int] = None
    error: str = ""                  # dernier problème de lecture (vide si le flux a été lu)
    articles: int = 0

    @classmethod
    def from_row(cls, row):
        return cls(row["id"], row["url"], row["title"], row["site_url"], row["added_by"], row["added_at"],
                   row["checked_at"], row["error"], row["articles"])

    def to_api(self, can_remove=False, shown=True):
        return {"id": self.id, "url": self.url, "title": self.title, "siteUrl": self.site_url,
                "checkedAt": self.checked_at, "error": self.error, "articles": self.articles, "canRemove": can_remove,
                "shown": shown}


@dataclass
class NewsArticle:
    """Un article d'un flux : seulement de quoi faire un lien (rien n'est copié à part le début du résumé)."""
    id: int
    feed_id: int
    feed_title: str
    link: str
    title: str
    summary: str
    published_at: int

    @classmethod
    def from_row(cls, row):
        return cls(row["id"], row["feed_id"], row["feed_title"], row["link"], row["title"], row["summary"],
                   row["published_at"])

    def to_api(self):
        return {"id": self.id, "feedId": self.feed_id, "feed": self.feed_title, "link": self.link, "title": self.title,
                "summary": self.summary, "publishedAt": self.published_at}


@dataclass
class ExtFavorite:
    """Titre d'ailleurs (YouTube, SoundCloud, Jamendo) mis en favori par une personne."""
    source: str
    item_id: str
    title: str
    artist: str
    image_url: str
    duration: int
    play_url: str
    page_url: str
    added_at: int

    @classmethod
    def from_row(cls, row):
        return cls(row["source"], row["item_id"], row["title"], row["artist"], row["image_url"], row["duration"],
                   row["play_url"], row["page_url"], row["added_at"])

    def to_api(self):
        """Au format commun des titres d'ailleurs (celui des résultats de recherche), que le lecteur sait lire."""
        track = {"title": self.title, "artist": self.artist, "album": "", "duration": self.duration,
                 "imageUrl": self.image_url, "ext": self.source, "addedAt": self.added_at}
        if self.source == "youtube":
            return dict(track, id="yt-" + self.item_id, youtubeId=self.item_id)
        if self.source == "soundcloud":
            return dict(track, id="sc-" + self.item_id, soundcloudUrl=self.play_url, pageUrl=self.page_url)
        return dict(track, id="jamendo-" + self.item_id, streamUrl=self.play_url)


@dataclass
class PlaylistExtTrack(ExtFavorite):
    """Titre d'ailleurs placé dans une playlist Subsonic (gardé par le site : Subsonic ne connaît que ses titres)."""
    row_id: int = 0
    after_songs: int = 0
    added_by: Optional[int] = None
    added_by_name: str = ""

    @classmethod
    def from_row(cls, row):
        return cls(row["source"], row["item_id"], row["title"], row["artist"], row["image_url"], row["duration"],
                   row["play_url"], row["page_url"], row["added_at"], row["id"], row["after_songs"], row["added_by"],
                   row["added_by_name"] or "")

    def to_api(self):
        return dict(super().to_api(), extId=self.row_id, addedBy=self.added_by_name)


@dataclass(frozen=True)
class ImportedTrack:
    """Titre d'une playlist venue d'ailleurs (Deezer, Spotify, Apple Music…), à retrouver dans la bibliothèque."""
    title: str
    artist: str = ""
    album: str = ""
    duration: int = 0                      # secondes, 0 si inconnue

    @classmethod
    def from_api(cls, item):
        """Titre renvoyé par la page (elle l'a reçu de /api/import/read) : revérifié, rien n'est pris tel quel."""
        if not isinstance(item, dict) or not isinstance(item.get("title"), str) or not item["title"].strip():
            raise ValueError("request.invalid")
        duration = item.get("duration", 0)
        text = lambda key: item.get(key)[:300] if isinstance(item.get(key), str) else ""
        return cls(item["title"].strip()[:300], text("artist"), text("album"),
                   duration if isinstance(duration, int) and not isinstance(duration, bool) and 0 <= duration < 86400 else 0)

    def to_api(self):
        return {"title": self.title, "artist": self.artist, "album": self.album, "duration": self.duration}
