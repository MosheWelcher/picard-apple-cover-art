# Apple Music cover art provider for MusicBrainz Picard.
#
# Uses the public iTunes Search API, which needs no account and no API key.
# Written for environments where coverartarchive.org / archive.org are not
# reachable.
#
# Copyright (C) 2026 Moshe Welcher
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.

import re
import unicodedata
from functools import partial

from picard.plugin3.api import (
    CoverArtImage,
    CoverArtProvider,
    PluginApi,
    t_,
)
from PyQt6.QtNetwork import QNetworkReply

ITUNES_SEARCH_URL = "https://itunes.apple.com/search"

# Matching and image defaults. There is no options page; edit these to tune.
IMAGE_SIZE = 1200  # Apple serves any square size, e.g. 600, 1200, 1400, 3000
STORE_COUNTRY = "US"  # two-letter iTunes store code
MATCH_THRESHOLD = 90  # roughly an exact title plus a matching artist
SEARCH_LIMIT = 25

# Apple serves any square size by swapping the trailing segment of the URL.
_SIZE_RE = re.compile(r"/\d+x\d+(bb)?\.(jpg|png|jpeg)$", re.IGNORECASE)
_PAREN_RE = re.compile(r"[\(\[][^\)\]]*[\)\]]")
_PUNCT_RE = re.compile(r"[^\w\s]", re.UNICODE)
_WS_RE = re.compile(r"\s+", re.UNICODE)

# Suffixes that mark a different edition of the same album. Used only to
# break ties, never to reject a release outright.
_EDITION_WORDS = frozenset([
    "deluxe", "expanded", "remaster", "remastered", "anniversary",
    "explicit", "clean", "edition", "version", "bonus", "single",
    "ep", "live", "instrumental", "acoustic",
])


def _normalize(text):
    """Casefold, strip accents and punctuation, collapse whitespace."""
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", str(text))
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.casefold()
    text = _PUNCT_RE.sub(" ", text)
    return _WS_RE.sub(" ", text).strip()


def _base_title(text):
    """Normalized title with any bracketed suffix removed."""
    return _normalize(_PAREN_RE.sub(" ", text or ""))


def _edition_tokens(text):
    """Edition-ish words appearing in a title's bracketed suffixes."""
    tokens = set()
    for chunk in _PAREN_RE.findall(text or ""):
        tokens |= {t for t in _normalize(chunk).split() if t in _EDITION_WORDS}
    return tokens


def upscale_artwork_url(url, size):
    """Rewrite a 100x100 thumbnail URL to the requested square size."""
    return _SIZE_RE.sub("/%dx%dbb.jpg" % (size, size), url)


def score_candidate(result, album, artist, totaltracks):
    """Score an iTunes result against the tags Picard already has.

    Returns (score, reason). Scores below MATCH_THRESHOLD are discarded so
    a wrong cover is never silently attached.
    """
    cand_album = result.get("collectionName") or ""
    cand_artist = result.get("artistName") or ""

    want_album, got_album = _normalize(album), _normalize(cand_album)
    want_base, got_base = _base_title(album), _base_title(cand_album)

    if not got_album or not want_album:
        return (0, "missing title")

    # --- album title ---
    if got_album == want_album:
        score, reason = 100, "exact title"
    elif got_base and got_base == want_base:
        score, reason = 80, "title matches ignoring edition"
    elif got_base and want_base and (
            got_base.startswith(want_base) or want_base.startswith(got_base)):
        score, reason = 60, "title prefix"
    else:
        return (0, "title mismatch (%r vs %r)" % (cand_album, album))

    # Prefer the edition whose bracketed suffix matches ours, so a plain
    # album does not get the deluxe cover when both exist.
    want_ed, got_ed = _edition_tokens(album), _edition_tokens(cand_album)
    if want_ed == got_ed:
        score += 12
    else:
        score -= 6 * len(want_ed ^ got_ed)

    # --- artist ---
    want_artist, got_artist = _normalize(artist), _normalize(cand_artist)
    if want_artist and got_artist:
        if want_artist == got_artist:
            score += 25
        elif want_artist in got_artist or got_artist in want_artist:
            score += 12
        else:
            score -= 25
            reason += ", artist mismatch"

    # --- track count, a strong signal for picking the right edition ---
    try:
        want_tracks = int(totaltracks) if totaltracks else 0
    except (TypeError, ValueError):
        want_tracks = 0
    got_tracks = result.get("trackCount") or 0
    if want_tracks and got_tracks:
        if want_tracks == got_tracks:
            score += 20
            reason += ", %d tracks match" % want_tracks
        else:
            score -= 10
            reason += ", track count %d vs %d" % (got_tracks, want_tracks)

    return (score, reason)


class AppleMusicCoverArtImage(CoverArtImage):

    """Image from the iTunes/Apple Music catalogue."""

    support_types = True
    sourceprefix = "APPL"


class CoverArtProviderAppleMusic(CoverArtProvider):

    """Use the iTunes Search API to find front cover art."""

    TITLE = t_("provider.title", "Apple Music")

    def enabled(self):
        return super().enabled() and not self.coverart.front_image_found

    def queue_images(self):
        album = self.metadata["album"]
        artist = self.metadata["albumartist"] or self.metadata["artist"] or ""
        if not album:
            self.api.logger.debug("No album title, skipping")
            return CoverArtProvider.QueueState.FINISHED

        term = f"{artist} {album}".strip()
        task_id = f"search:{self.album.id}"
        self.api.logger.debug(f"Searching for {term!r}")

        def create_request():
            return self.api.web_service.get_url(
                url=ITUNES_SEARCH_URL,
                queryargs={
                    "entity": "album",
                    "limit": str(SEARCH_LIMIT),
                    "media": "music",
                    "country": STORE_COUNTRY,
                },
                unencoded_queryargs={"term": term},
                handler=partial(self._json_downloaded, task_id, album, artist),
                priority=True,
                important=False,
                parse_response_type="json",
            )

        self.api.add_album_task(
            self.album,
            task_id,
            f"Apple Music search: {term}",
            request_factory=create_request,
        )
        return CoverArtProvider.QueueState.WAIT

    def _json_downloaded(self, task_id, album, artist, data, reply, error):
        self.api.complete_album_task(self.album, task_id)

        if error:
            if error == QNetworkReply.NetworkError.ContentNotFoundError:
                self.api.logger.debug(f"Request failed: {error}")
            else:
                self.api.logger.error(f"Request failed: {error}")
        else:
            try:
                self._process(data, album, artist)
            except (AttributeError, KeyError, TypeError):
                self.api.logger.exception("Failed to process response")

        self.next_in_queue()

    def _process(self, data, album, artist):
        results = data.get("results") or []
        if not results:
            self.api.logger.debug(f"No results for {album!r}")
            return

        totaltracks = self.metadata["totaltracks"]
        scored = []
        for r in results:
            if not r.get("artworkUrl100"):
                continue
            score, reason = score_candidate(r, album, artist, totaltracks)
            scored.append((score, reason, r))

        if not scored:
            self.api.logger.debug("No candidates carried artwork")
            return

        scored.sort(key=lambda x: x[0], reverse=True)
        score, reason, best = scored[0]

        if score < MATCH_THRESHOLD:
            self.api.logger.debug(
                f"Best candidate {best.get('collectionName')!r} scored "
                f"{score} < {MATCH_THRESHOLD} ({reason}), rejected")
            return

        url = upscale_artwork_url(best["artworkUrl100"], IMAGE_SIZE)
        self.api.logger.debug(
            f"Matched {best.get('collectionName')!r} by "
            f"{best.get('artistName')!r}, score {score} ({reason}): {url}")
        self.queue_put(AppleMusicCoverArtImage(url, types=["front"]))


def enable(api: PluginApi):
    """Called when plugin is enabled."""
    api.register_cover_art_provider(CoverArtProviderAppleMusic)
