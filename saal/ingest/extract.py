"""HTML to sections: title, the page's own last updated date, and heading scoped text.

Uses trafilatura when it is installed, and a standard library extractor otherwise,
so a clone with nothing installed still produces a usable corpus. The heading path
is kept rather than discarded: on this site the headings carry most of the intent
signal ("Who can get it", "How to claim"), which is exactly what a situation
sentence needs to match against.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from html.parser import HTMLParser

SKIP_TAGS = {
    "script", "style", "nav", "header", "footer", "aside", "form", "noscript",
    "svg", "button", "select", "template", "iframe", "picture",
}
SKIP_CLASS = re.compile(
    r"\b(nav|breadcrumb|menu|footer|header|search|cookie|banner|related|share|"
    r"feedback|skip-link|sidebar|toc|social|subscribe)\b", re.I
)
BLOCK_TAGS = {
    "p", "li", "div", "section", "article", "br", "td", "th", "tr", "dd", "dt",
    "h1", "h2", "h3", "h4", "h5", "h6", "blockquote",
}
HEADINGS = {"h1": 1, "h2": 2, "h3": 3, "h4": 4, "h5": 5, "h6": 6}

DATE_TEXT = re.compile(
    r"(?:page\s+)?last\s+updated[:\s]*"
    r"(\d{1,2}\s+[A-Za-z]+\s+\d{4}|\d{4}-\d{2}-\d{2})", re.I
)
DATE_FORMATS = ("%d %B %Y", "%d %b %Y", "%Y-%m-%d")
TITLE_SPLIT = re.compile(r"\s+[|–-]\s+")


@dataclass
class Section:
    heading_path: str
    text: str


@dataclass
class Page:
    url: str
    title: str
    page_last_updated: str | None
    sections: list[Section]


def _parse_date(raw: str) -> str | None:
    raw = raw.strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            continue
    return None


class _SectionParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title: str | None = None
        self.h1: str | None = None
        self.og_title: str | None = None
        self.meta_date: str | None = None
        self.sections: list[Section] = []
        self._skip_depth = 0
        self._skip_tag: str | None = None
        self._in_title = False
        self._heading_level: int | None = None
        self._heading_buf: list[str] = []
        self._stack: list[tuple[int, str]] = []
        self._buf: list[str] = []
        self._in_list_item = False

    # ---- helpers -------------------------------------------------------
    def _heading_path(self) -> str:
        return " > ".join(h for _, h in self._stack)

    def _flush(self) -> None:
        text = re.sub(r"[ \t]+", " ", "".join(self._buf))
        text = re.sub(r"\n{3,}", "\n\n", text).strip()
        self._buf = []
        if not text:
            return
        path = self._heading_path()
        if self.sections and self.sections[-1].heading_path == path:
            self.sections[-1].text = (self.sections[-1].text + "\n" + text).strip()
        else:
            self.sections.append(Section(heading_path=path, text=text))

    def _push_heading(self, level: int, text: str) -> None:
        self._flush()
        while self._stack and self._stack[-1][0] >= level:
            self._stack.pop()
        self._stack.append((level, text))

    # ---- parser callbacks ----------------------------------------------
    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if self._skip_depth:
            if tag == self._skip_tag:
                self._skip_depth += 1
            return
        if tag in SKIP_TAGS or SKIP_CLASS.search(" ".join(
            filter(None, [a.get("class", ""), a.get("id", ""), a.get("role", "")])
        ) or ""):
            self._skip_tag, self._skip_depth = tag, 1
            self._flush()
            return
        if tag == "meta":
            name = (a.get("name") or a.get("property") or "").lower()
            if name in {"dcterms.modified", "article:modified_time", "last-modified"}:
                self.meta_date = _parse_date((a.get("content") or "")[:10]) or self.meta_date
            elif name == "og:title" and a.get("content"):
                self.og_title = a["content"]
            return
        if tag == "title":
            self._in_title = True
            return
        if tag in HEADINGS:
            self._flush()
            self._heading_level = HEADINGS[tag]
            self._heading_buf = []
            return
        if tag == "li":
            self._in_list_item = True
            self._buf.append("\n- ")
        elif tag in BLOCK_TAGS:
            self._buf.append("\n")

    def handle_endtag(self, tag):
        if self._skip_depth:
            if tag == self._skip_tag:
                self._skip_depth -= 1
                if self._skip_depth == 0:
                    self._skip_tag = None
            return
        if tag == "title":
            self._in_title = False
            return
        if tag in HEADINGS and self._heading_level is not None:
            text = re.sub(r"\s+", " ", "".join(self._heading_buf)).strip()
            if text:
                if self._heading_level == 1 and self.h1 is None:
                    self.h1 = text
                self._push_heading(self._heading_level, text)
            self._heading_level = None
            self._heading_buf = []
            return
        if tag == "li":
            self._in_list_item = False
        if tag in BLOCK_TAGS:
            self._buf.append("\n")

    def handle_data(self, data):
        if self._skip_depth:
            return
        if self._in_title:
            self.title = (self.title or "") + data
            return
        if self._heading_level is not None:
            self._heading_buf.append(data)
            return
        self._buf.append(data)

    def close(self):  # type: ignore[override]
        super().close()
        self._flush()


def extract(html: str, url: str) -> Page:
    parser = _SectionParser()
    parser.feed(html)
    parser.close()

    # The h1 comes last. Most payment subpages have an h1 of "Who can get it" or
    # "How to claim", and the payment it belongs to is only in og:title and the
    # document title ("Who can get JobSeeker Payment - JobSeeker Payment - ...").
    # A chunk titled "Who can get it" is anonymous to retrieval. See D16.
    doc_title = TITLE_SPLIT.split(parser.title or "")[0].strip()
    title = parser.og_title or doc_title or parser.h1 or url
    title = re.sub(r"\s+", " ", title).strip()

    date_iso = parser.meta_date
    if not date_iso:
        blob = "\n".join(s.text for s in parser.sections)
        m = DATE_TEXT.search(blob) or DATE_TEXT.search(html)
        if m:
            date_iso = _parse_date(m.group(1))

    sections = [
        Section(s.heading_path, _strip_boilerplate(s.text))
        for s in parser.sections
    ]
    sections = [s for s in sections if s.text]
    return Page(url=url, title=title, page_last_updated=date_iso, sections=sections)


BOILERPLATE_LINE = re.compile(
    r"^\s*(page last updated.*|print this page|share this page|was this page useful\??|listen|"
    r"we acknowledge the traditional custodians.*|read more about.*cookies.*)\s*$", re.I
)


def _strip_boilerplate(text: str) -> str:
    kept = [ln for ln in text.splitlines() if not BOILERPLATE_LINE.match(ln)]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(kept)).strip()
