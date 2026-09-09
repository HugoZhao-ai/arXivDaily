import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from common import ROOT, arxiv_id, classify, read_json, term_matches, write_json
from sync import fetch_stream, merge, parse_feed
from sync import run as sync_run
from build import build, card
from check_site import check
from enrich import ArticleParser, image_extension, validate_summary
from datetime import datetime, timezone

FEED = '''<feed xmlns="http://www.w3.org/2005/Atom" xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/">
<opensearch:totalResults>{total}</opensearch:totalResults>{entry}</feed>'''
ENTRY = '''<entry><id>http://arxiv.org/abs/2601.12345v2</id><title>Quantization for language models and agents</title>
<summary>Low-bit quantization for multi-step reasoning with a KV cache.</summary><published>2026-01-01T00:00:00Z</published>
<updated>2026-02-01T00:00:00Z</updated><author><name>Song Han</name></author><category term="cs.LG"/></entry>'''


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.config = read_json(ROOT / 'config.json')
        self.paper = parse_feed(FEED.format(total=1, entry=ENTRY))[0][0]

    def test_version_and_legacy_id(self):
        self.assertEqual(arxiv_id('https://arxiv.org/pdf/2306.00978v3.pdf'), '2306.00978')
        self.assertEqual(arxiv_id('http://arxiv.org/abs/cs/0601001v2'), 'cs/0601001')
        with self.assertRaises(ValueError):
            arxiv_id('../../index')
        self.assertEqual(self.paper['version'], 2)

    def test_topic_groups_and_author_identity(self):
        self.assertTrue(classify(self.paper, self.config))
        self.assertIn('agent-quantization', self.paper['topics'])
        self.assertEqual(self.paper['researchers'], [{'id': 'song-han', 'status': 'name-match'}])
        self.paper['title'], self.paper['abstract'] = 'An unrelated paper', 'Other work'
        classify(self.paper, self.config)
        self.assertEqual(self.paper['topics'], [])
        self.assertEqual(len(self.paper['researchers']), 1)
        classify(self.paper, self.config, {'song-han': [self.paper['id']]})
        self.assertEqual(self.paper['researchers'][0]['status'], 'verified')

    def test_no_partial_author_name_or_agent_substring_match(self):
        self.paper['authors'] = ['Song Han Li', 'Han Songlin']
        self.paper['title'], self.paper['abstract'] = 'Quantization of reagent compounds', 'A chemical experiment'
        self.assertFalse(classify(self.paper, self.config))
        self.assertFalse(term_matches('agent', 'reagent'))
        self.assertFalse(term_matches('llm', 'allman'))

    def test_related_topics_are_not_direct(self):
        self.paper.update(title='Efficient KV cache', abstract='Memory compression for long-context language model inference', authors=['A Person'])
        classify(self.paper, self.config)
        self.assertEqual(self.paper['topics'], ['long-context'])
        self.assertTrue(self.paper['related_only'])

    def test_generic_reasoning_and_diffusion_are_not_agent_quantization(self):
        self.paper.update(title='Quantization of diffusion transformers', abstract='A multi-step image generation model', authors=['A Person'])
        classify(self.paper, self.config)
        self.assertNotIn('agent-quantization', self.paper['topics'])
        self.paper.update(title='Quantized language model evaluation', abstract='Free-text reasoning in political questionnaires')
        classify(self.paper, self.config)
        self.assertNotIn('agent-quantization', self.paper['topics'])

    def test_revision_replaces_metadata_and_invalidates_summary(self):
        previous = {**self.paper, 'updated': '2026-01-01T00:00:00Z', 'summary': {'tldr': 'old'}, 'image': {}, 'first_seen': '2026-01-01'}
        existing = {previous['id']: previous}
        merge(existing, self.paper)
        self.assertNotIn('summary', existing[previous['id']])
        self.assertEqual(existing[previous['id']]['first_seen'], '2026-01-01')
        merge(existing, previous)
        self.assertEqual(existing[previous['id']]['version'], 2)

    def test_same_revision_preserves_enrichment(self):
        existing = {self.paper['id']: {**self.paper, 'summary': {'tldr': 'keep'}}}
        merge(existing, self.paper)
        self.assertEqual(existing[self.paper['id']]['summary']['tldr'], 'keep')

    def test_pagination_and_truncation_are_not_silent(self):
        client = Mock()
        client.get.side_effect = [FEED.format(total=2, entry=ENTRY), FEED.format(total=2, entry=ENTRY.replace('12345', '12346'))]
        settings = {'page_size': 1, 'max_pages': 2}
        dt = datetime(2026, 1, 1, tzinfo=timezone.utc)
        papers = fetch_stream(client, 'abs:quantization', dt, dt, settings)
        self.assertEqual(len(papers), 2)
        self.assertIn('start=1', client.get.call_args.args[0])
        client.get.side_effect = [FEED.format(total=3, entry=ENTRY)] * 2
        with self.assertRaisesRegex(RuntimeError, 'exceeds'):
            fetch_stream(client, 'abs:quantization', dt, dt, settings)
        client.get.side_effect = [FEED.format(total=2, entry='')]
        with self.assertRaisesRegex(RuntimeError, 'Empty page'):
            fetch_stream(client, 'x', dt, dt, settings)

    def test_api_error_and_invalid_payload(self):
        with self.assertRaises(ValueError):
            parse_feed(FEED.format(total=1, entry=ENTRY.replace('http://arxiv.org/abs/2601.12345v2', 'http://arxiv.org/api/errors#bad')))
        with self.assertRaises(ValueError):
            parse_feed('<html>Failure</html>')

    def test_failed_stream_keeps_checkpoint_and_other_streams_advance(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = copy.deepcopy(self.config)
            config['seed_ids'] = []
            write_json(root / 'config.json', config)
            write_json(root / 'data/papers.json', {'papers': []})
            write_json(root / 'data/state.json', {'streams': {}, 'last_success': None})
            with patch('sync.ROOT', root), patch('sync.HttpClient') as client, patch('sync.fetch_stream') as fetch:
                client.return_value.get.return_value = b'<html></html>'
                fetch.side_effect = [RuntimeError('rate limit'), [self.paper], [], [self.paper]]
                self.assertEqual(sync_run(), 1)
            state = read_json(root / 'data/state.json')
            self.assertNotIn('topic:llm-quantization', state['streams'])
            self.assertEqual(len(state['streams']), 3)
            self.assertIsNone(state['last_success'])
            self.assertEqual(state['last_run']['status'], 'partial')
            self.assertEqual(len(read_json(root / 'data/papers.json')['papers']), 1)

    def test_untrusted_content_is_escaped(self):
        self.paper['title'] = '<script>alert(1)</script>'
        self.paper['abstract'] = '\" onmouseover=\"alert(1)'
        classify(self.paper, self.config)
        rendered = card(self.paper, self.config)
        self.assertNotIn('<script>', rendered)
        self.assertIn('&lt;script&gt;', rendered)
        self.assertNotIn('data-search="\"', rendered)

    def test_summary_schema_and_image_content(self):
        with self.assertRaises(ValueError):
            validate_summary({'title_zh': 'partial'})
        self.assertIsNone(image_extension(b'<svg><script>evil</script></svg>'))
        parser = ArticleParser()
        parser.feed('<script>evil</script><article>Hello<figure><img src="x.png"></figure></article>')
        self.assertNotIn('evil', parser.parts)
        self.assertEqual(parser.image, 'x.png')

    def test_build_links_and_atomic_json(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'data.json'
            write_json(path, {'中文': True})
            self.assertEqual(read_json(path), {'中文': True})
            self.assertFalse(path.with_suffix('.json.tmp').exists())
            output = build(Path(temporary) / 'site')
            check(output)


if __name__ == '__main__':
    unittest.main()
