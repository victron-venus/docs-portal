# Contributing to the documentation

## Where a document belongs

| You are writing | Put it in |
| --- | --- |
| How a specific project works, installs or is configured | that project's `docs/` |
| A contract several projects share (D-Bus, MQTT, CI, release) | the canonical repository named in [Reference](reference/index.md) |
| A hand-written guide for the public site | [victron-venus.github.io](https://github.com/victron-venus/victron-venus.github.io) |
| Shared boilerplate (quality evidence, preflight, versioning) | [venus-os-ci-toolkit](https://github.com/victron-venus/venus-os-ci-toolkit) |

## Rules

1. **Every `docs/` directory has a `docs/README.md` index.** Group by what the
   reader wants to do; link every user-facing page. A document nobody links is a
   document nobody finds.
2. **No vendored copies of shared boilerplate.** If a repository must carry one,
   its first line names the canonical source.
3. **Diagrams are mermaid by default.** This portal renders mermaid, so a
   diagram is visible without a build step or a raster export. Use a committed
   SVG only for something mermaid cannot express, and keep the source.
4. **Wiki content is generated, never hand-edited.** The source of truth is
   `docs/` in the repository.
5. **A translation is a translation.** If a translated README is a shortened
   summary, say so at the top; do not present an abridged page as a translation
   of the English one.

## Building this portal locally

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python scripts/sync_sources.py --catalog ../victron-venus.github.io/assets/catalog.json --clone
.venv/bin/mkdocs build --strict
.venv/bin/mkdocs serve
```

`--clone` shallow-clones each catalogued repository into `.sources/`, which is
ignored by git. The build fails on a broken relative link, a missing page or a
malformed mermaid block, so a mistake is caught before publication.
