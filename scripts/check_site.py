"""Check all generated local links and fragment targets, including project subpaths."""
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit
from common import ROOT


class Page(HTMLParser):
    def __init__(self, text):
        super().__init__()
        self.links, self.ids = [], set()
        self.feed(text)

    def handle_starttag(self, tag, attributes):
        attrs = dict(attributes)
        if attrs.get('id'):
            self.ids.add(attrs['id'])
        for name in ['href', 'src']:
            if attrs.get(name):
                self.links.append(attrs[name])


def check(directory):
    directory = Path(directory).resolve()
    pages = {p.resolve(): Page(p.read_text(encoding='utf-8')) for p in directory.rglob('*.html')}
    assert directory / 'index.html' in pages, 'Missing index'
    count = 0
    for path, page in pages.items():
        for link in page.links:
            url = urlsplit(link)
            if url.scheme or url.netloc:
                assert url.scheme in {'https', 'http'}, f'Unsafe URL in {path}'
                continue
            assert not url.path.startswith('/'), f'Root-relative link breaks project Pages: {link}'
            target = (path.parent / unquote(url.path)).resolve() if url.path else path
            if target.is_dir():
                target /= 'index.html'
            assert target.is_relative_to(directory), f'Path escapes output: {link}'
            assert target.exists(), f'Broken link: {path}: {link}'
            if url.fragment and target in pages:
                assert unquote(url.fragment) in pages[target].ids, f'Unknown fragment: {link}'
            count += 1
    print(f'Checked {len(pages)} HTML pages and {count} local links')


if __name__ == '__main__':
    check(ROOT / 'site')
