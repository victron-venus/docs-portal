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
import os
import posixpath
import shutil
import tempfile
from urllib.parse import quote, urlsplit
import re
import subprocess
import sys
from pathlib import Path

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

LINK = re.compile(r'(?P<image>!?)\[(?P<label>[^\[\]\n]*)\]\((?P<target><[^>\n]+>|[^)\s]+)(?P<rest>\s+[\"\'][^\n]*?[\"\'])?\)')
REPO = re.compile(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+')


def slug(repo: str) -> str:
    if not REPO.fullmatch(repo) or any(p in {'.', '..'} for p in repo.split('/')):
        raise ValueError(f'invalid repository name: {repo!r}')
    name = repo.split('/', 1)[-1]
    return 'org-' + name.lstrip('.') if name.startswith('.') else name


def rewrite_links(text: str, source_repo: str, source_path: str,
                  revision: str = 'main') -> str:
    """Resolve inline links from their actual source page; images use raw bytes.

    Absolute URLs, custom schemes and same-page anchors retain their meaning.
    Reference-style links and HTML href/src attributes are handled too; fenced
    examples retain their literal content.
    """
    def resolve(target: str, image: bool = False) -> str:
        target = target.removeprefix('<').removesuffix('>')
        parsed = urlsplit(target)
        if parsed.scheme or parsed.netloc or target.startswith('#'):
            return target
        path = (posixpath.normpath(posixpath.join(
            posixpath.dirname(source_path) if not target.startswith('/') else '',
            parsed.path.lstrip('/'))) if parsed.path else source_path)
        if path == '..' or path.startswith('../'):
            raise ValueError(f'link escapes repository: {source_path}: {target}')
        base = (f'https://raw.githubusercontent.com/{source_repo}/{revision}/' if image
                else f'https://github.com/{source_repo}/blob/{revision}/')
        suffix = ('?' + parsed.query if parsed.query else '') + ('#' + parsed.fragment if parsed.fragment else '')
        return base + quote(path, safe='/%:@') + suffix

    def replace(match: re.Match[str]) -> str:
        target = resolve(match.group('target'), bool(match.group('image')))
        return (f'{match.group("image")}[{match.group("label")}]('
                f'{target}{match.group("rest") or ""})')

    image_refs = {m.casefold() for m in re.findall(r'!\[[^\]]*\]\[([^\]]+)\]', text)}
    references = re.compile(r'^(?P<prefix> {0,3}\[(?P<id>[^\]]+)\]:\s*)(?P<target><[^>]+>|\S+)')
    attributes = re.compile(r'(?P<prefix>\b(?P<kind>src|href)=[\"\'])(?P<target>[^\"\']+)', re.I)
    lines = []
    fence = ''
    for line in text.splitlines(keepends=True):
        marker = re.match(r'^ {0,3}(`{3,}|~{3,})', line)
        if marker:
            token = marker[1]
            if not fence:
                fence = token
            elif token[0] == fence[0] and len(token) >= len(fence) and not line[marker.end():].strip():
                fence = ''
            lines.append(line)
            continue
        if fence:
            lines.append(line)
            continue
        line = LINK.sub(replace, line)
        # Linked images have an outer ](target) after the inner image rewrite.
        line = re.sub(r'\]\((?P<target><[^>\n]+>|[^)\s]+)(?P<rest>\s+[\"\'][^\n]*?[\"\'])?\)',
                      lambda m: '](' + resolve(m['target']) + (m['rest'] or '') + ')', line)
        line = references.sub(lambda m: m['prefix'] + resolve(m['target'], m['id'].casefold() in image_refs), line)
        line = attributes.sub(lambda m: m['prefix'] + resolve(m['target'], m['kind'].lower() == 'src'), line)
        lines.append(line)
    return ''.join(lines)


def git_environment() -> dict[str, str]:
    # Git-specific routing, config injection and askpass must not escape a caller.
    environment = {key: value for key, value in os.environ.items()
                   if not key.startswith('GIT_') and key not in
                   {'SSH_ASKPASS', 'GH_TOKEN', 'GITHUB_TOKEN'}}
    environment.update(GIT_TERMINAL_PROMPT='0', GIT_CONFIG_NOSYSTEM='1',
                       GIT_CONFIG_GLOBAL=os.devnull)
    return environment


def git(checkout: Path, *args: str, data: bytes | None = None) -> bytes:
    return subprocess.run(['git', '-C', str(checkout), *args], input=data,
                          check=True, capture_output=True, timeout=120, env=git_environment()).stdout


def committed_pages(checkout: Path, repo: str) -> tuple[str, dict[str, str]]:
    # Never read sibling working files, ignored documents or symlink targets.
    origin = git(checkout, 'config', '--local', '--get', 'remote.origin.url').decode().strip()
    if origin not in {f'https://github.com/{repo}', f'https://github.com/{repo}.git'}:
        raise ValueError(f'checkout origin does not match public catalog: {repo}')
    revision = git(checkout, 'rev-parse', '--verify', 'HEAD^{commit}').decode().strip()
    entries = []
    for row in git(checkout, 'ls-tree', '-rz', revision, '--', 'README.md', 'docs').split(b'\0'):
        if not row:
            continue
        meta, name = row.split(b'\t', 1)
        mode, kind, oid = meta.split()
        path = name.decode('utf-8')
        if mode in {b'100644', b'100755'} and kind == b'blob' and path.endswith('.md'):
            entries.append((path, oid))
    payload = git(checkout, 'cat-file', '--batch',
                  data=b''.join(oid + b'\n' for _, oid in entries)) if entries else b''
    pages = {}
    offset = 0
    for path, oid in entries:
        end = payload.index(b'\n', offset)
        actual_oid, kind, size = payload[offset:end].split()
        if actual_oid != oid or kind != b'blob':
            raise ValueError('unexpected Git batch response')
        size = int(size)
        offset = end + 1
        pages[path] = payload[offset:offset + size].decode('utf-8')
        offset += size + 1
    if offset != len(payload):
        raise ValueError('unexpected trailing Git batch response')
    return revision, pages


def build_entry(entry: dict, checkout: Path, out: Path) -> dict:
    repo = str(entry['repo'])
    name = slug(repo)
    revision, sources = committed_pages(checkout, repo)
    project_dir = out / name
    project_dir.mkdir(parents=True, exist_ok=True)
    body = rewrite_links(sources.get('README.md', ''), repo, 'README.md', revision)
    (project_dir / 'index.md').write_text(
        f'# {entry["name"]}\n\n{entry["summary"]}\n\n'
        f'[Source repository](https://github.com/{repo}){{ .md-button }}\n\n---\n\n{body}',
        encoding='utf-8')
    pages = 1
    for path, text in sources.items():
        if path == 'README.md':
            continue
        target = project_dir / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(rewrite_links(text, repo, path, revision), encoding='utf-8')
        pages += 1
    return {'name': entry['name'], 'dir': name, 'pages': pages}


def publish_generated(staging: Path, out: Path) -> None:
    """Replace only output positively owned by an earlier successful generation."""
    import hashlib
    marker = '.portal-owned.json'
    def inventory(folder: Path) -> dict[str, str]:
        result = {}
        for path in folder.rglob('*'):
            if path.is_symlink():
                raise ValueError('symlink in generated output')
            if path.is_file() and path != folder / marker:
                result[path.relative_to(folder).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
        return result
    if out.is_symlink():
        raise ValueError('generated output is a symlink')
    if out.exists() and any(out.iterdir()):
        prior = out / marker
        if not prior.is_file() or prior.is_symlink() or json.loads(prior.read_text()) != inventory(out):
            raise ValueError('generated output contains unowned or modified files; preserve it before rebuilding')
    (staging / marker).write_text(json.dumps(inventory(staging), sort_keys=True), encoding='utf-8')
    if out.exists():
        shutil.rmtree(out)
    staging.rename(out)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--catalog', required=True, help='path to assets/catalog.json')
    parser.add_argument('--checkout-dir', default='.sources', help='shallow checkouts root')
    parser.add_argument('--clone', action='store_true',
                        help='shallow-clone missing repositories before aggregating')
    parser.add_argument('--output-dir', help='generated output directory (default: docs/projects)')
    args = parser.parse_args()

    catalog_path = Path(args.catalog)
    if not catalog_path.is_file():
        print(f'catalog not found: {catalog_path}', file=sys.stderr)
        return 2
    catalog = json.loads(catalog_path.read_text(encoding='utf-8'))

    root = Path(__file__).resolve().parents[1]
    out = Path(args.output_dir).absolute() if args.output_dir else root / 'docs' / 'projects'
    out.parent.mkdir(parents=True, exist_ok=True)
    checkouts = root / args.checkout_dir
    checkouts.mkdir(parents=True, exist_ok=True)
    if checkouts.is_symlink():
        raise ValueError('checkout directory must not be a symlink')
    # Validate before network or filesystem writes based on catalog names.
    names = [slug(str(e['repo'])) for e in catalog['projects']]
    if len(names) != len(set(names)):
        raise ValueError('duplicate repository slug in catalog')
    staging_context = tempfile.TemporaryDirectory(prefix='.portal-', dir=out.parent)
    staging = Path(staging_context.name)

    results: list[dict] = []
    missing: list[str] = []
    for entry in catalog['projects']:
        name = slug(str(entry['repo']))
        checkout = checkouts / str(entry['repo']).split('/', 1)[1]
        if not checkout.is_dir():
            if not args.clone:
                missing.append(name)
                continue
            # Only anonymous public clones; never offer the runner's credentials.
            environment = git_environment()
            subprocess.run(
                ['git', '-c', 'credential.helper=', '-c', 'core.hooksPath=/dev/null',
                 '-c', 'core.askPass=', 'clone', '--depth', '1', '--filter=blob:none',
                 f'https://github.com/{entry["repo"]}.git', str(checkout)],
                env=environment, timeout=120, check=True, capture_output=True,
            )
            if not checkout.is_dir():
                missing.append(name)
                continue
        if checkout.is_symlink():
            raise ValueError('checkout must not be a symlink')
        results.append(build_entry(entry, checkout, staging))

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
    (staging / 'index.md').write_text('\n'.join(lines), encoding='utf-8')

    if missing:
        staging_context.cleanup()
        print('missing source checkouts: ' + ', '.join(missing), file=sys.stderr)
        return 1
    publish_generated(staging, out)
    staging_context.cleanup()
    total = sum(r['pages'] for r in results)
    print(f'aggregated {len(results)} projects, {total} pages')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
