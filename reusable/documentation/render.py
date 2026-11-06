"""Allow-list HTML sanitizing and published-link rewriting. No network requests."""
from html import escape
from html.parser import HTMLParser
import posixpath
from urllib.parse import unquote, urlsplit

TAGS = {'p','br','hr','h1','h2','h3','h4','h5','h6','ul','ol','li','strong','em',
        'b','i','del','blockquote','pre','code','table','thead','tbody','tr','th','td',
        'a','img','div','span','details','summary','kbd','sup','sub'}


class LinkRewriter(HTMLParser):
    def __init__(self, library, current, document_url, asset_url):
        super().__init__(convert_charrefs=True)
        self.library, self.current = library, current
        self.document_url, self.asset_url = document_url, asset_url
        self.output = []

    def url(self, value, image=False):
        if not value or '\\' in value or any(ord(c) < 32 for c in value):
            return None
        try:
            parsed = urlsplit(value)
        except ValueError:
            return None
        if parsed.scheme:
            return value if not image and parsed.scheme.lower() in ('https','http','mailto') else None
        if parsed.netloc or parsed.path.startswith('/') or parsed.query:
            return None
        if not parsed.path:
            return '#' + parsed.fragment if parsed.fragment and not image else None
        relative = posixpath.normpath(posixpath.join(posixpath.dirname(self.current), unquote(parsed.path)))
        try:
            self.library.read_bytes(relative, asset=image)
        except (ValueError, OSError):
            return None
        target = self.asset_url(relative) if image else self.document_url(relative)
        return target + ('#' + parsed.fragment if parsed.fragment and not image else '')

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'a':
            target = self.url(attrs.get('href'))
            attrs.pop('href', None)
            if target:
                attrs['href'] = target
                if urlsplit(target).scheme:
                    attrs.update(target='_blank', rel='noopener noreferrer')
            else:
                attrs['title'] = 'Link indisponível no catálogo local'
        if tag == 'img':
            target = self.url(attrs.get('src'), image=True)
            if not target:
                self.output.append('<span>[Imagem indisponível no catálogo local]</span>')
                return
            attrs['src'] = target
        self.output.append('<' + tag + ''.join(' ' + k + '="' + escape(v or '', quote=True) + '"' for k,v in attrs.items()) + '>')

    def handle_endtag(self, tag):
        if tag not in ('img','br','hr'):
            self.output.append('</' + tag + '>')

    def handle_data(self, data):
        self.output.append(escape(data))


def render_document(library, document, *, document_url, asset_url):
    import markdown
    import bleach
    parser = markdown.Markdown(extensions=['fenced_code','tables','toc','sane_lists'])
    html = parser.convert(document.text)
    def cleaned(value):
        value = bleach.clean(value, tags=TAGS,
            attributes={'*':['id'], 'a':['href','title'], 'img':['src','alt','title'],
                        'code':['class'], 'div':['class'], 'ol':['start'], 'td':['colspan','rowspan'], 'th':['colspan','rowspan']},
            protocols=['http','https','mailto'], strip=True, strip_comments=True)
        links = LinkRewriter(library, document.path, document_url, asset_url)
        links.feed(value)
        links.close()
        return ''.join(links.output)
    return dict(html=cleaned(html), toc=cleaned(parser.toc))
