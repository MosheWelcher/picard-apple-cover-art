# Apple Music cover art for MusicBrainz Picard

A cover art provider plugin for [MusicBrainz Picard](https://picard.musicbrainz.org/)
that fetches front covers from the public **iTunes Search API**.

No account, no API key, no registration.

## Why

Picard gets cover art from the [Cover Art Archive](https://coverartarchive.org/)
by default, which serves its images from `archive.org`. If either host is
unreachable on your network — a content filter, a school or workplace proxy, a
country-level block — Picard tags everything correctly but silently fails on
artwork. The symptom is usually a message like this on the Album Info → Error tab:

```
CAA JSON error: Unknown error
```

That error means Picard asked `coverartarchive.org` for JSON and got something
else back (typically a filter's HTML block page).

This plugin adds Apple's catalogue as an alternative source. It talks to
`itunes.apple.com` and downloads images from `mzstatic.com`, so it works
wherever those two hosts are reachable.

It is also just a useful fallback in general: Apple's catalogue covers a lot of
recent and independent releases that have no art in the Cover Art Archive.

## Requirements

- MusicBrainz Picard **3.x** (plugin API 3.0)
- Network access to `itunes.apple.com` and `is1-ssl.mzstatic.com`

> **Using Picard 2.x?** The original single-file plugin lives on the
> [`picard-v2` branch](https://github.com/MosheWelcher/picard-apple-cover-art/tree/picard-v2).
> Download `applecoverart.py` from there and follow the install steps in that
> branch's README.

## Installation

### Option A — from inside Picard (recommended)

1. **Options → Options… → Plugins**.
2. Choose **Install from URL** and enter
   `https://github.com/MosheWelcher/picard-apple-cover-art`.
3. Enable **Apple Music cover art** in the plugin list.

### Option B — command line

```
picard-cli plugins install https://github.com/MosheWelcher/picard-apple-cover-art
```

## Enabling it as a cover art source

Installing the plugin is not enough — you also have to turn on the provider and
put it in the right order.

1. **Options → Options… → Cover Art**
2. Tick **Apple Music** in the *Cover Art Providers* list.
3. Move it with the arrow buttons. Below **Cover Art Archive** makes it a
   fallback; above makes it take precedence.

If the Cover Art Archive is unreachable on your network, untick **Cover Art
Archive** and **CAA Release Group** as well. They will otherwise be tried first,
fail, and leave the "CAA JSON error" on the Error tab even though the artwork
itself is arriving from Apple.

Providers run in list order and the plugin stops as soon as another provider has
already supplied a front cover, so it is safe to leave several enabled as
fallbacks.

## Tuning

There is no settings page. The defaults are constants at the top of
[`__init__.py`](__init__.py):

| Constant | Default | What it does |
|---|---|---|
| `IMAGE_SIZE` | `1200` | Square image size requested from Apple. 600, 1200, 1400 and 3000 all work. |
| `STORE_COUNTRY` | `US` | Which country's store to search. Catalogues differ slightly by region. |
| `MATCH_THRESHOLD` | `90` | Minimum score a candidate must reach before its art is used. Higher is stricter. |

## How matching works

The Cover Art Archive is keyed on MusicBrainz IDs, so its matches are exact.
Apple has no MBIDs, so this plugin has to match on text — and naive text
matching attaches the wrong cover surprisingly often, usually the deluxe edition
of the album you actually have.

To avoid that, every search result is scored against tags Picard already holds:

- **Album title** — exact match, match ignoring a bracketed suffix, or a prefix
  match, in descending order of confidence. Titles are casefolded with accents
  and punctuation stripped, so `Beyoncé` and `Beyonce` compare equal.
- **Edition words** — `Deluxe`, `Remastered`, `Live`, `EP` and similar inside
  brackets. A candidate whose edition markers match yours scores higher, so a
  plain album does not get the deluxe cover when both exist.
- **Artist** — exact or substring match against `albumartist`, falling back to
  `artist`.
- **Track count** — compared against `totaltracks`. A strong signal for picking
  the right edition.

Only the highest scoring candidate is considered, and only if it clears the
confidence threshold. **If nothing is confident enough, the plugin attaches
nothing** and lets the next provider try, rather than guessing.

Set the log level to Debug (**Help → View Error/Debug Log**) to see the score
and reasoning for every lookup.

## Limitations

- **Apple's catalogue has gaps.** Some albums are not in the Search API at all,
  in any regional store — Pink Floyd's *The Dark Side of the Moon* is a
  well-known example. There is no query that finds them. Keep another provider
  enabled below this one as a fallback.
- **Matching is textual, not MBID-based.** The scoring is conservative and
  rejects uncertain matches, but it cannot be perfect the way a
  Cover Art Archive lookup is. Unusual or heavily-retitled releases may be
  skipped.
- **Front covers only.** The plugin does not fetch back covers, booklets, or
  disc images.
- Artwork is square, as Apple stores it. Non-square original packaging is not
  preserved.

## License

GPL-2.0-or-later — see [LICENSE](LICENSE).

Not affiliated with Apple or with the MusicBrainz project. "Apple Music" and
"iTunes" are trademarks of Apple Inc.
