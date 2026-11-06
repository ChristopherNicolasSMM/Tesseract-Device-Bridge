"""Bounded catalog of explicitly published Markdown folders and files."""
from dataclasses import dataclass
import os
from pathlib import Path, PurePosixPath
import re
import unicodedata


class DocumentError(ValueError):
    pass


def folded(text):
    return ''.join(c for c in unicodedata.normalize('NFKD', text.casefold())
                   if not unicodedata.combining(c))


@dataclass(frozen=True)
class Document:
    path: str
    title: str
    category: str
    text: str


class DocumentLibrary:
    def __init__(self, root, *, folders=('docs',), files=('README.md',), categories=(),
                 max_files=256, max_bytes=512 * 1024, max_total=16 * 1024 * 1024):
        self.root = Path(root).resolve()
        self.folders = tuple(folders)
        self.files = tuple(files)
        self.categories = tuple(categories)
        self.max_files, self.max_bytes, self.max_total = max_files, max_bytes, max_total

    def safe_file(self, relative):
        if not isinstance(relative, str) or '\\' in relative or '\x00' in relative:
            raise DocumentError('Invalid path.')
        parts = PurePosixPath(relative)
        if parts.is_absolute() or not parts.parts or any(p in ('..', '.') or p.startswith('.') for p in parts.parts):
            raise DocumentError('Invalid path.')
        path = self.root / relative
        for current in [path] + list(path.parents):
            if current == self.root:
                break
            if current.is_symlink() or getattr(current, 'is_junction', lambda: False)():
                raise DocumentError('Linked documentation rejected.')
        if not path.resolve().is_relative_to(self.root) or not path.is_file():
            raise DocumentError('Document not found.')
        return path

    def published(self, relative):
        return relative in self.files or any(relative.startswith(folder.rstrip('/') + '/') for folder in self.folders)

    def read_bytes(self, relative, *, asset=False):
        if not self.published(relative):
            raise DocumentError('Outside published scope.')
        suffix = PurePosixPath(relative).suffix.lower()
        allowed = ('.png', '.jpg', '.jpeg', '.gif', '.webp') if asset else ('.md',)
        if suffix not in allowed:
            raise DocumentError('Unsupported document format.')
        path = self.safe_file(relative)
        with path.open('rb') as stream:
            raw = stream.read(self.max_bytes + 1)
        if len(raw) > self.max_bytes:
            raise DocumentError('Document exceeds size limit.')
        return raw

    def document(self, relative):
        try:
            text = self.read_bytes(relative).decode('utf-8-sig')
        except UnicodeError as exc:
            raise DocumentError('Invalid UTF-8.') from exc
        heading = re.search(r'^#\s+(.+)$', text, re.M)
        title = re.sub(r'[*`_]', '', heading.group(1)).strip() if heading else PurePosixPath(relative).stem
        category = next((label for prefix, label in self.categories if relative.startswith(prefix)), 'Outros')
        return Document(relative, title[:200], category, text)

    def catalog(self):
        names = set(self.files)
        scanned = 0
        for folder in self.folders:
            parent = self.root / folder
            if parent.is_symlink() or getattr(parent, 'is_junction', lambda: False)():
                continue
            for directory, dirs, files in os.walk(parent, followlinks=False):
                dirs[:] = sorted(d for d in dirs if not d.startswith('.') and not (Path(directory) / d).is_symlink()
                                 and not getattr(Path(directory) / d, 'is_junction', lambda: False)())
                for name in files:
                    scanned += 1
                    if scanned > self.max_files * 16:
                        raise DocumentError('Catalog scan exceeds limit.')
                    if name.lower().endswith('.md') and not name.startswith('.'):
                        names.add((Path(directory) / name).relative_to(self.root).as_posix())
                        if len(names) > self.max_files:
                            raise DocumentError('Catalog exceeds file limit.')
        documents, total = [], 0
        for name in sorted(names):
            try:
                document = self.document(name)
            except (DocumentError, OSError):
                continue
            total += len(document.text.encode('utf-8'))
            if total > self.max_total:
                raise DocumentError('Catalog exceeds total size limit.')
            documents.append(document)
        return documents

    def search(self, query, documents=None):
        query = query.strip()[:160]
        words = folded(query).split()
        if not words:
            return []
        results = []
        for doc in documents if documents is not None else self.catalog():
            content = folded(doc.title + '\n' + doc.text)
            if all(word in content for word in words):
                # Plain-text snippets are escaped by the host template.
                lines = [line.strip() for line in doc.text.splitlines() if any(word in folded(line) for word in words)]
                results.append(dict(document=doc, snippet=' '.join(lines)[:240],
                                    rank=sum(word in folded(doc.title) for word in words)))
        return sorted(results, key=lambda r: (-r['rank'], r['document'].title))[:40]
