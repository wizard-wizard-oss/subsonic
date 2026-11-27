"""Cache des réponses publiques des services externes : une entrée par clé, avec sa date de récupération."""
from dataclasses import dataclass
from typing import Optional, Protocol


@dataclass(frozen=True)
class CachedMetadata:
    """Réponse publique conservée en cache, avec sa date de récupération d’origine."""
    key: str
    data: dict
    fetched_at: int


class MetadataStore(Protocol):
    def get(self, key) -> Optional[CachedMetadata]: ...

    def save(self, entry: CachedMetadata) -> None: ...

    def expire(self, prefix, before) -> None: ...

    def discard(self, prefix, keep) -> None: ...


class MemoryStore:
    """Cache en mémoire : le Pi, sans base du site, et les tests."""
    def __init__(self):
        self.entries = {}

    def get(self, key):
        return self.entries.get(key)

    def save(self, entry):
        self.entries[entry.key] = entry

    def expire(self, prefix, before):
        for key in [k for k, e in self.entries.items() if k.startswith(prefix) and e.fetched_at < before]:
            del self.entries[key]

    def discard(self, prefix, keep):
        for key in [k for k in self.entries if k.startswith(prefix) and k != keep]:
            del self.entries[key]
