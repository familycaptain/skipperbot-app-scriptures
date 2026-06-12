# skipperbot-app-scriptures

A Skipperbot **app package** — a Bible reader with daily passages, bookmarks, and
AI-generated chapter summaries / people / places.

> **Shipped separately on purpose.** Religious content isn't something every
> household wants bundled into their assistant, so this is an opt-in package
> rather than part of the core platform.

## What it is

- **Read** the Bible by book / chapter, with bookmarks and a daily passage.
- **Summaries, people, and places** pre-generated for your bookmarked chapters
  (and a few ahead) via a nightly prefetch job.

## Install

```bash
# from a running skipperbot-platform checkout:
cd apps
git clone <this-repo> scriptures
pip install -r scriptures/requirements.txt   # pymupdf, for the one-time Bible import
cd ..   # restart the platform — the loader discovers apps/scriptures/ on boot
```

The clone target directory **must** be `scriptures` (the app id). This app has
one app-only Python dependency (`pymupdf`) used for the one-time Bible PDF import;
see `requirements.txt`.

## Layout

```
manifest.yaml     app manifest (id: scriptures)
data.py           data layer (app_scriptures schema)
import_bible.py   one-time Bible PDF -> DB import (uses pymupdf)
gbf.py            passage helpers
prefetch.py       nightly summary/people/places prefetch
routes.py         REST router, mounted at /api/apps/scriptures
migrations/       per-app SQL migrations
ui/               desktop UI (auto-discovered by Vite)
help.md
requirements.txt  app-only Python deps (pymupdf)
```

## Status

Prerelease extraction — carved out of the bundled platform so niche apps are
opt-in. MIT licensed.
