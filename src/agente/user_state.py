"""Contratto condiviso della gestione utenti (spec 08).

Tipi e limiti usati da C-31 e C-32. Il modulo importa solo il tipo ``User``
da C-02: nessun accesso a SQL e nessun import dei componenti, così i due
componenti possono importarlo senza cicli.
"""

from __future__ import annotations

from dataclasses import dataclass

from .storage.repositories import User

# BR-16: fino a 5 utenti autorizzati (D5 del piano 08).
MAX_AUTHORIZED_USERS = 5


@dataclass(frozen=True)
class UserView:
    """Vista di elenco: utente e compiti a cui è iscritto."""

    user: User
    task_names: tuple[str, ...] = ()


@dataclass(frozen=True)
class UserResult:
    """Esito di un'operazione sugli utenti.

    ``note`` è il messaggio pronto per il destinatario (admin o utente):
    C-14 lo inoltra senza ricomporlo. ``changed`` è vero solo se stato o
    iscrizioni sono cambiati su disco; ``notice_sent`` solo se questa
    chiamata ha inviato l'informativa.
    """

    user: User
    changed: bool
    note: str
    notice_sent: bool = False
