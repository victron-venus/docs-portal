import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

SPEC = importlib.util.spec_from_file_location('sync', Path(__file__).parents[1] / 'scripts/sync_sources.py')
sync = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(sync)


class Links(unittest.TestCase):
    def test_nested_page_and_parent(self):
        text = sync.rewrite_links('[next](../setup.md#run)', 'org/repo', 'docs/deep/page.md', 'abc')
        self.assertEqual(text, '[next](https://github.com/org/repo/blob/abc/docs/setup.md#run)')

    def test_readme_image_root_and_external(self):
        result = sync.rewrite_links('![map](docs/map.svg) [root](/LICENSE) [web](https://a/b) [call](tel:123) [anchor](#x)', 'o/r', 'README.md', 'abc')
        self.assertIn('https://raw.githubusercontent.com/o/r/abc/docs/map.svg', result)
        self.assertIn('https://github.com/o/r/blob/abc/LICENSE', result)
        self.assertTrue(result.endswith('[web](https://a/b) [call](tel:123) [anchor](#x)'))

    def test_titles_spaces_and_escaping(self):
        self.assertEqual(sync.rewrite_links('[a](<my page.md> "Title")', 'o/r', 'docs/a.md', 'abc'), '[a](https://github.com/o/r/blob/abc/docs/my%20page.md "Title")')
        with self.assertRaises(ValueError):
            sync.rewrite_links('[a](../../secret.md)', 'o/r', 'docs/a.md')

    def test_references_html_and_fenced_examples(self):
        text = ('![plot][image]\n[manual]: ../guide.md\n[image]: img.png\n'
                '<img src="img.png"><a href="next.md">x</a>\n'
                '```md\n[example](local.md)\n```\n')
        result = sync.rewrite_links(text, 'o/r', 'docs/page.md', 'abc')
        self.assertIn('[manual]: https://github.com/o/r/blob/abc/guide.md', result)
        self.assertIn('[image]: https://raw.githubusercontent.com/o/r/abc/docs/img.png', result)
        self.assertIn('src="https://raw.githubusercontent.com/o/r/abc/docs/img.png"', result)
        self.assertIn('href="https://github.com/o/r/blob/abc/docs/next.md"', result)
        self.assertIn('[example](local.md)', result)

    def test_linked_image_preserves_raw_image_and_outer_link(self):
        result = sync.rewrite_links('[![demo](image.png)](full.png)', 'o/r', 'docs/page.md', 'abc')
        self.assertEqual(result, '[![demo](https://raw.githubusercontent.com/o/r/abc/docs/image.png)](https://github.com/o/r/blob/abc/docs/full.png)')

    def test_dot_repository_is_not_a_hidden_page(self):
        self.assertEqual(sync.slug('org/.github'), 'org-github')

    def test_invalid_catalog_identity(self):
        for name in ['../secret', 'o/..', 'o/r/extra', 'file:///tmp/x']:
            with self.subTest(name=name), self.assertRaises(ValueError):
                sync.slug(name)


class Environment(unittest.TestCase):
    def test_git_metadata_and_askpass_do_not_escape_caller(self):
        injection = {name: 'not-for-child' for name in [
            'GIT_DIR', 'GIT_COMMON_DIR', 'GIT_WORK_TREE', 'GIT_INDEX_FILE',
            'GIT_OBJECT_DIRECTORY', 'GIT_ALTERNATE_OBJECT_DIRECTORIES',
            'GIT_CONFIG_COUNT', 'GIT_CONFIG_KEY_0', 'GIT_CONFIG_VALUE_0',
            'GIT_ASKPASS', 'SSH_ASKPASS', 'GH_TOKEN', 'GITHUB_TOKEN']}
        with mock.patch.dict(sync.os.environ, injection):
            env = sync.git_environment()
        for key in injection:
            self.assertNotIn(key, env)
        self.assertEqual(env['GIT_TERMINAL_PROMPT'], '0')
        self.assertEqual(env['GIT_CONFIG_GLOBAL'], sync.os.devnull)


class Sources(unittest.TestCase):
    def test_only_committed_regular_blobs_and_quality_page(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            repo = root / 'repo'
            repo.mkdir()
            def git(*args):
                return subprocess.run(['git', '-C', str(repo), *args], check=True, capture_output=True).stdout
            git('init', '-q')
            git('remote', 'add', 'origin', 'https://github.com/o/r.git')
            (repo / 'docs').mkdir()
            (repo / 'README.md').write_text('[guide](docs/guide.md)')
            (repo / 'docs/guide.md').write_text('[root](../README.md)')
            (repo / 'docs/quality.md').write_text('Unique safety rule')
            external = root / 'private.md'
            external.write_text('DO NOT PUBLISH')
            (repo / 'docs/link.md').symlink_to(external)
            git('add', '.')
            git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', '-c', 'commit.gpgsign=false', 'commit', '-qm', 'Fixture')
            (repo / 'README.md').write_text('LOCAL SECRET')
            (repo / 'docs/ignored.md').write_text('UNCOMMITTED SECRET')
            output = root / 'out'
            sync.build_entry({'repo': 'o/r', 'name': 'R', 'summary': 'Public'}, repo, output)
            rendered = '\n'.join(p.read_text() for p in output.rglob('*.md'))
            self.assertIn('Unique safety rule', rendered)
            for private in ['LOCAL SECRET', 'UNCOMMITTED SECRET', 'DO NOT PUBLISH']:
                self.assertNotIn(private, rendered)
            self.assertFalse((output / 'r/docs/link.md').exists())
            git('remote', 'set-url', 'origin', 'https://github.com/o/different.git')
            with self.assertRaises(ValueError):
                sync.committed_pages(repo, 'o/r')


class Ownership(unittest.TestCase):
    def test_stale_files_removed_only_if_owned_and_unmodified(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            out = root / 'out'
            stage = root / 'stage'
            stage.mkdir()
            (stage / 'old.md').write_text('old')
            sync.publish_generated(stage, out)
            stage.mkdir()
            (stage / 'new.md').write_text('new')
            sync.publish_generated(stage, out)
            self.assertFalse((out / 'old.md').exists())
            self.assertEqual((out / 'new.md').read_text(), 'new')
            (out / 'new.md').write_text('manual change')
            stage.mkdir()
            with self.assertRaises(ValueError):
                sync.publish_generated(stage, out)
            self.assertEqual((out / 'new.md').read_text(), 'manual change')

    def test_unknown_output_and_symlinks_preserved(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            out = root / 'out'
            out.mkdir()
            (out / 'manual.md').write_text('keep')
            stage = root / 'stage'
            stage.mkdir()
            with self.assertRaises(ValueError):
                sync.publish_generated(stage, out)
            self.assertTrue((out / 'manual.md').is_file())
            (out / 'manual.md').unlink()
            (out / 'link').symlink_to(stage, target_is_directory=True)
            with self.assertRaises(ValueError):
                sync.publish_generated(stage, out)
