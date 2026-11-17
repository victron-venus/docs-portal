#!/usr/bin/env python3
"""Aggregate project documentation from the catalog into this portal.

Nothing is copied into git. The catalog lives in the organization site
repository as `assets/catalog.json`; each project's `README.md` and `docs/`
tree is read from a shallow checkout under `.sources/` and rendered into
`docs/projects/`. Re-running the script is idempotent.

Usage:
    python3 scripts/sync_sources.py --checkout-dir .sources --catalog <path>
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

# Shared repository boilerplate that is not project documentation. It exists in
# dozens of copies with diverging content, so the portal links the canonical
# source once instead of rendering every copy.
BOILERPLATE = {
    'release-workflow.md', 'quality.md', 'openssf-evidence.md',
    'runner-preflight.md', 'release-read-safety.md', 'VERSIONING.md',
    'rc-fuzzing.md', 'fuzzing.md', 'transport-security.md',
}

GROUP_TITLES = {
    'dbus': 'D-Bus services',
    'control': 'Control',
    'dashboards': 'Dashboards',
    'sensing': 'Sensing',
    'gateways': 'Gateways',
    'voice': 'Voice',
    'observability': 'Observability',
    'ai': 'Forecasting and analysis',
    'tooling': 'Tooling',
    'archived': 'Archived',
}

LINK = re.compile(r'\]\((?P<target>[^)\s]+)(?P<rest>\s+"[^"]*")?\)')


def slug(repo: str) -> str:
    return repo.split('/', 1)[-1]


def rewrite_links(text: str, source_repo: str, depth: int) -> str:
    """Point relative links at the GitHub blob view.

    A rendered page has no sibling repository files, so a relative link would
    break. Rewriting to the repository's blob view keeps every link correct and
    makes the portal a reader, not a fork, of the source.
    """
    base = f'https://github.com/{source_repo}/blob/main/'

    def replace(match: re.Match[str]) -> str:
        target = match.group('target')
        if target.startswith(('http://', 'https://', 'mailto:', '#', '/')):
            return match.group(0)
        anchor = ''
        path = target
        if '#' in target:
            path, anchor = target.split('#', 1)
            anchor = '#' + anchor
        prefix = '../' * depth
        return f']({base}{path}{anchor}{match.group("rest") or ""})'

    return LINK.sub(replace, text)


def copy_tree(source: Path, destination: Path, repo: str, depth: int) -> int:
    written = 0
    destination.mkdir(parents=True, exist_ok=True)
    for entry in sorted(source.rglob('*.md')):
        relative = entry.relative_to(source)
        if entry.name in BOILERPLATE:
            continue
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        text = entry.read_text(encoding='utf-8')
        text = rewrite_links(text, repo, depth + len(relative.parts) - 1)
        target.write_text(text, encoding='utf-8')
        written += 1
    return written


def build_entry(entry: dict, checkout: Path, out: Path) -> dict:
    name = slug(str(entry['repo']))
    repo = str(entry['repo'])
    project_dir = out / name
    project_dir.mkdir(parents=True, exist_ok=True)

    readme = checkout / 'README.md'
    pages = 0
    if readme.is_file():
        body = rewrite_links(readme.read_text(encoding='utf-8'), repo, 1)
        (project_dir / 'index.md').write_text(
            f'# {entry["name"]}\n\n'
            f'{entry["summary"]}\n\n'
            f'[Source repository]({entry["url"]}){{ .md-button }}\n\n'
            f'---\n\n{body}',
            encoding='utf-8',
        )
        pages += 1
    else:
        (project_dir / 'index.md').write_text(
            f'# {entry["name"]}\n\n{entry["summary"]}\n\n'
            f'[Source repository]({entry["url"]}){{ .md-button }}\n',
            encoding='utf-8',
        )
        pages += 1

    docs = checkout / 'docs'
    if docs.is_dir():
        pages += copy_tree(docs, project_dir / 'docs', repo, 1)

    return {'name': entry['name'], 'dir': name, 'pages': pages}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--catalog', required=True, help='path to assets/catalog.json')
    parser.add_argument('--checkout-dir', default='.sources', help='shallow checkouts root')
    parser.add_argument('--clone', action='store_true',
                        help='shallow-clone missing repositories before aggregating')
    args = parser.parse_args()

    catalog_path = Path(args.catalog)
    if not catalog_path.is_file():
        print(f'catalog not found: {catalog_path}', file=sys.stderr)
        return 2
    catalog = json.loads(catalog_path.read_text(encoding='utf-8'))

    root = Path(__file__).resolve().parents[1]
    out = root / 'docs' / 'projects'
    checkouts = root / args.checkout_dir
    checkouts.mkdir(parents=True, exist_ok=True)

    results: list[dict] = []
    missing: list[str] = []
    out.mkdir(parents=True, exist_ok=True)
    for entry in catalog['projects']:
        name = slug(str(entry['repo']))
        checkout = checkouts / name
        if not checkout.is_dir():
            # Reuse the working checkout in the workspace when there is one, so
            # a local build does not clone 41 repositories.
            local = root.parent / name
            if local.is_dir() and (local / '.git').exists():
                checkout = local
        if not checkout.is_dir():
            if not args.clone:
                missing.append(name)
                continue
            subprocess.run(
                ['git', 'clone', '--depth', '1', '--filter=blob:none',
                 f'https://github.com/{entry["repo"]}.git', str(checkout)],
                check=False, capture_output=True,
            )
            if not checkout.is_dir():
                missing.append(name)
                continue
        results.append(build_entry(entry, checkout, out))

    by_group: dict[str, list[dict]] = {}
    for entry, built in zip(
        [e for e in catalog['projects'] if slug(str(e['repo'])) not in missing], results
    ):
        by_group.setdefault(str(entry['group']), []).append({**built, 'group': entry['group'],
                                                            'summary': entry['summary'],
                                                            'url': entry['url']})

    lines = ['# Projects', '',
             'Every maintained project, grouped the same way as the public catalog. '
             'Pages are generated from each repository; the repository remains the '
             'source of truth.', '']
    for group in catalog['groups']:
        items = by_group.get(group, [])
        if not items:
            continue
        lines += [f'## {GROUP_TITLES.get(group, group.title())}', '',
                  '| Project | What it does |', '| --- | --- |']
        for item in sorted(items, key=lambda i: str(i['name'])):
            lines.append(f"| [{item['name']}]({item['dir']}/index.md) | {item['summary']} |")
        lines.append('')
    (out / 'index.md').write_text('\n'.join(lines), encoding='utf-8')

    total = sum(r['pages'] for r in results)
    print(f'aggregated {len(results)} projects, {total} pages')
    if missing:
        print(f'skipped {len(missing)} without a checkout: {", ".join(sorted(missing))}',
              file=sys.stderr)
    return 0 if not missing or not args.clone else 1


if __name__ == '__main__':
    raise SystemExit(main())
