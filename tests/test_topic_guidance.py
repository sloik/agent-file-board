import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import boardctl
from message_extensions import validate_extensions


class TopicGuidanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.board = self.root / '.agent-board'
        with contextlib.redirect_stdout(io.StringIO()):
            boardctl.main(['init', str(self.root), '--project-id', 'test', '--project-name', 'Test'])
            for who in ('alpha-agent', 'bravo-agent', 'other-agent'):
                boardctl.main(['join', who, '--path', str(self.root)])
        self.config = boardctl.board_paths(self.root)[1]
        self.room = self.board / 'rooms/general'

    def post(self, slug, at, title=None):
        args = ['post', '--path', str(self.root), '--from', 'alpha-agent', '--to', 'all', '--scope', 'room', '--room', 'general', '--thread', 'T001', '--slug', slug, '--at', at]
        if title is not None:
            args += ['--topic-title', title]
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(boardctl.main(args), 0)
        return next(self.room.glob('*_' + slug + '.txt'))

    def guidance(self, *args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = boardctl.main(['guidance', '--path', str(self.root), *args])
        return code, json.loads(out.getvalue()) if out.getvalue() else None, out.getvalue()

    def test_explicit_title_survives_later_stale_label_and_reload(self):
        self.post('original', '2026-10-15 12:00:01')
        changed = self.post('rename', '2026-10-15 12:00:02', 'Scope: café / 日本 🚀')
        self.assertEqual(boardctl.parse_message(changed)['TOPIC-TITLE'], 'Scope: café / 日本 🚀')
        stale = self.post('stale-message', '2026-10-15 12:00:03')
        text = stale.read_text().replace('THREAD: T001-scope-caf', 'THREAD: T001-old-title')
        stale.write_text(text)
        result = boardctl.resolve_topic(self.room, 'T001', self.config)
        self.assertEqual(result['title'], 'Scope: café / 日本 🚀')
        ordinary = self.post('next-message', '2026-10-15 12:01:00')
        self.assertEqual(boardctl.parse_message(ordinary)['THREAD'], boardctl.parse_message(changed)['THREAD'])
        self.assertEqual(boardctl.validate(self.root), [])

    def test_first_label_is_fallback_and_explicit_events_use_precise_date_order(self):
        first = self.post('first', '2026-10-15 12:00:01')
        second = self.post('second', '2026-10-15 12:00:02')
        self.assertEqual(boardctl.parse_message(second)['THREAD'], 'T001-first')
        self.post('zzz-rename', '2026-10-15 12:00:03.100', 'Title A')
        self.post('aaa-rename', '2026-10-15 12:00:03.200', 'Title B')
        self.assertEqual(boardctl.resolve_topic(self.room, 'T001', self.config)['title'], 'Title B')
        # DATE corrections remain authoritative over a later precise timestamp.
        self.post('corrected', '2026-10-15 11:59:59', 'Earlier title')
        self.assertEqual(boardctl.resolve_topic(self.room, 'T001', self.config)['title'], 'Title B')
        self.assertEqual(boardctl.parse_message(first)['THREAD'], 'T001-first')

    def test_legacy_ui_title_file_is_an_explicit_event(self):
        self.post('initial', '2026-10-15 12:00:01')
        legacy = self.post('topic-title-renamed', '2026-10-15 12:00:02')
        legacy.write_text(legacy.read_text().replace('THREAD: T001-initial', 'THREAD: T001-legacy-title'))
        self.post('later-stale', '2026-10-15 12:00:03')
        self.assertEqual(boardctl.resolve_topic(self.room, 'T001', self.config)['title'], 'legacy title')

    def test_title_wire_validation_unicode_and_no_partial_publication(self):
        for title in ('日本 🚀', 'a' * 199 + '🚀', 'a: b | c'):
            validate_extensions({'TOPIC-TITLE': title})
        for title in ('', ' ', '!!!', 'a'*201, 'a\nB', 'a\tB', 'a\0B', 'a\u2028b', '\ud800', ['title'], None):
            with self.subTest(title=repr(title)), self.assertRaises(ValueError):
                validate_extensions({'TOPIC-TITLE': title})
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(boardctl.main(['post', '--path', str(self.root), '--from', 'alpha-agent', '--to', 'all', '--scope', 'room', '--room', 'general', '--thread', 'T001', '--slug', 'bad', '--topic-title', '\ud800']), 2)
        self.assertEqual(list(self.room.glob('*.txt')), [])

    def test_missing_and_combined_markdown_do_not_rename_topic(self):
        code, result, _ = self.guidance('--room', 'general', '--topic', 'T001')
        self.assertEqual(code, 0)
        self.assertEqual([d['status'] for d in result['documents']], ['missing', 'missing'])
        (self.room / 'GUIDANCE.md').write_text('# General\nUse tables.\n')
        (self.room / 'topics').mkdir()
        (self.room / 'topics/T001.md').write_text('# Rules\nAsk for evidence.\n')
        _, result, _ = self.guidance('--room', 'general', '--topic', 'T001')
        self.assertEqual([d['kind'] for d in result['documents']], ['room', 'topic'])
        self.assertIn('Ask for evidence', result['documents'][1]['markdown'])
        self.assertIsNone(boardctl.resolve_topic(self.room, 'T001', self.config))
        self.assertEqual(boardctl.validate(self.root), [])

    def test_guidance_has_complete_json_byte_bound_with_emoji_and_escaping(self):
        (self.room / 'GUIDANCE.md').write_text(('🚀\\\"\n' * 5000))
        _, result, output = self.guidance('--room', 'general', '--max-bytes', '1024')
        self.assertLessEqual(len(output.encode('utf-8')), 1024)
        self.assertTrue(result['truncated'])
        self.assertTrue(result['documents'][0]['truncated'])
        self.assertTrue(result['documents'][0]['markdown'])

    def test_direct_guidance_visibility_and_no_path_traversal(self):
        pair = 'alpha-agent--bravo-agent'
        directory = self.board / 'direct' / pair
        directory.mkdir()
        (directory / 'GUIDANCE.md').write_text('PRIVATE MARKER')
        _, result, _ = self.guidance('--direct', pair, '--participant', 'alpha-agent')
        self.assertEqual(result['documents'][0]['markdown'], 'PRIVATE MARKER')
        for args in (('--direct', pair), ('--direct', pair, '--participant', 'other-agent'), ('--direct', '../general', '--participant', 'alpha-agent'), ('--room', '../direct'), ('--room', 'general', '--topic', '../T001')):
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(self.guidance(*args)[0], 2)

    def test_guidance_symlinks_invalid_utf8_read_failures_and_validation(self):
        guide = self.room / 'GUIDANCE.md'
        guide.write_bytes(b'\xff')
        _, result, _ = self.guidance('--room', 'general')
        self.assertEqual(result['documents'][0]['status'], 'error')
        self.assertTrue(boardctl.validate(self.root))
        guide.unlink()
        outside = self.root / 'outside.md'
        outside.write_text('SECRET')
        guide.symlink_to(outside)
        _, result, _ = self.guidance('--room', 'general')
        self.assertEqual(result['documents'][0]['status'], 'error')
        self.assertNotIn('SECRET', str(result))
        self.assertTrue(boardctl.validate(self.root))
        guide.unlink()
        guide.write_text('readable')
        original = Path.open
        def refused(path, *args, **kwargs):
            if path.resolve() == guide.resolve():
                raise PermissionError('denied')
            return original(path, *args, **kwargs)
        with patch.object(Path, 'open', refused):
            _, result, _ = self.guidance('--room', 'general')
        self.assertEqual(result['documents'][0]['status'], 'error')

    def test_guidance_rejects_topic_names_and_linked_parent(self):
        topics = self.room / 'topics'
        topics.mkdir()
        (topics / 'title.md').write_text('wrong route')
        self.assertTrue(any('thread ID' in e for e in boardctl.validate(self.root)))
        (topics / 'title.md').unlink()
        topics.rmdir()
        outside = self.root / 'topic-files'
        outside.mkdir()
        (outside / 'T001.md').write_text('SECRET')
        topics.symlink_to(outside, target_is_directory=True)
        _, result, _ = self.guidance('--room', 'general', '--topic', 'T001')
        self.assertEqual(result['documents'][1]['status'], 'error')
        self.assertNotIn('SECRET', str(result))
