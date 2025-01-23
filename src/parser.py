"""Ugly code for an ugly job."""

import sys

from dataclasses import dataclass
from abc import ABCMeta

import json
import re
from pathlib import Path
from html.parser import HTMLParser

from argparse import ArgumentParser, FileType

from typing import Callable, Optional, Tuple


def string2html(s):
    """Escape "unicode" characters"""
    def gen():
        for c in s:
            if (c.isascii() and c.isprintable()) or c in "\n\r\t":
                yield c
            else:
                yield f"&#{ord(c)};"
    return "".join(gen())


def warn(*args, **kwargs):
    print("[WARN]", *args, **kwargs, file=sys.stderr)


# Part 1: Building Trees

class Node(metaclass=ABCMeta):
    def html(self):
        ...
    def json(self):
        ...


@dataclass
class ElementNode(Node):
    tag: str
    attrs: dict[str, Optional[str]]
    children: list
    self_closing: bool = False

    def html(self):
        attrs_str = " ".join(f'{k}="{v}"' if v is not None else k for k, v in self.attrs.items())
        if self.self_closing:
            return f"<{self.tag} {attrs_str} />"
        else:
            content_str = "".join(ch.html() for ch in self.children)
            return f"<{self.tag} {attrs_str}>{content_str}</{self.tag}>"

    def json(self):
        return {
            "tag": self.tag,
            "attrs": self.attrs,
            "children": [ch.json() for ch in self.children]
        }

@dataclass
class TextNode(Node):
    text: str

    def html(self):
        return string2html(self.text)

    def json(self):
        return self.text

class HTMLStructureParser(HTMLParser):

    VOID_ELEMENTS = (
        "area", "base", "br", "col", "embed", "hr", "img",
        "input", "link", "meta", "source", "track", "wbr"
    )

    HEADER_RE = re.compile("h[0-9]+")

    @classmethod
    def is_header_tag(cls, tag: str):
        return bool(HTMLStructureParser.HEADER_RE.fullmatch(tag))

    def __init__(self):
        super().__init__()

        self.stack = []

        self.element = None
        self.children = []

    def _path(self, extras=()):
        # TODO: make this less messy
        st = self.stack + [(self.element, self.children[:-1])] + list(extras)
        def pos(chs):
            return 1 + len([c for c in chs if not isinstance(c, TextNode)])
        return "/".join(
            f"{pos(ch)}:{el.tag if el is not None else '_'}"
            for (_, ch), (el, _) in zip(st, st[1:])
        )

    def handle_starttag(self, tag: str, attrs: list[tuple[str, Optional[str]]]):
        if tag in self.VOID_ELEMENTS:
            return self.handle_startendtag(tag, attrs)
        self.stack.append((self.element, self.children))

        self.element = ElementNode(tag=tag, attrs=dict(attrs), children=None)
        self.children = []

    def handle_endtag(self, tag: str):
        if tag in self.VOID_ELEMENTS:
            # the HTML contains loads of </br> tags
            return self.handle_startendtag(tag, attrs=[])

        while True:
            if self.element is None:
                break

            # ignore stray </a> and </tr>, this isn't really nice but it works
            if tag in ("a", "tr") and tag != self.element.tag:
                warn(
                    f"pos={self.getpos()[0]}:{self.getpos()[1]} path={self._path()}",
                    f"ignored stray {tag!r} tag",
                )
                break

            self.element.children = self.children

            el = self.element
            self.element, self.children = self.stack.pop()
            self.children.append(el)

            if (
                tag == el.tag
                # headers are sometimes closed by the wrong level of header
                or (self.is_header_tag(tag) and self.is_header_tag(el.tag))
            ):
                break

            warn(
                f"pos={self.getpos()[0]}:{self.getpos()[1]} path={self._path(extras=[(el, [])])}",
                f"tag {el.tag!r} not closed, got {tag!r} instead",
            )

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, Optional[str]]]):
        self.children.append(ElementNode(
            tag=tag, attrs=dict(attrs),
            children=[],
            self_closing=True,
        ))

    def handle_data(self, data: str):
        self.children.append(TextNode(data))


# Part 2: Parsing Trees


## Parsing Nodes


class P[A, T](metaclass=ABCMeta):
    def parse(self, x: A) -> Optional[T]:
        ...


class ElementNodeP[T](P[Node, T]):
    def __init__(self, content: P[list[Node], T], tag: str = None, attrs: dict[str, Optional[str]] = ()):
        self._content = content
        self._tag = tag
        self._attrs = dict(attrs)

    def parse(self, el: Node) -> Optional[list[T]]:
        if not isinstance(el, ElementNode): return None
        if self._tag is not None and el.tag != self._tag: return None
        for k, v in self._attrs.items():
            if k not in el.attrs: return None
            if v != el.attrs[k]: return None
        return self._content.parse(el.children)


class ElementDescendP[T](P[Node, list[T]]):
    def __init__(self, until: P[Node, T]):
        self._until = until

    def parse(self, element: Node) -> Optional[list[T]]:
        found = []
        def dfs(el):
            r = self._until.parse(el)
            if r is not None:
                found.append(r)
                return
            if not isinstance(el, ElementNode): return
            for ch in el.children:
                dfs(ch)
        dfs(element)
        return found


class TextNodeP[T](P[Node, T]):
    def __init__(self, content: P[str, T]):
        self._content = content
    def parse(self, el: Node):
        if not isinstance(el, TextNode): return None
        return self._content.parse(el.text)


## Parsing Combinators


class IdentityP[A](P[A, A]):
    def parse(self, x: A) -> Optional[A]:
        return x


class MapP[A, T1, T2](P[A, T2]):
    def __init__(self, base: P[A, T1], f: Callable[[T1], Optional[T2]]):
        self._base = base
        self._f = f
    def parse(self, x: A) -> Optional[T2]:
        r = self._base.parse(x)
        if r is None: return None
        return self._f(r)


pure_parser = lambda x: MapP(IdentityP(), lambda _: x)
fail_parser = pure_parser(None)


class Lift2P[A, T1, T2, T](P[A, T]):
    def __init__(self, base1: P[A, T1], base2: P[A, T2], f: Callable[[T1, T2], Optional[T]]):
        self._base1 = base1
        self._base2 = base2
        self._f = f
    def parse(self, x: A) -> Optional[T2]:
        r1 = self._base1.parse(x)
        if r1 is None: return None
        r2 = self._base2.parse(x)
        if r2 is None: return None
        return self._f(r1, r2)


const_parser = lambda base, x: MapP(base, lambda _: x)


class AnyP[A, T](P[A, T]):
    def __init__(self, *base: [A, T]):
        self._bases = base
    def parse(self, x: A):
        for b in self._bases:
            r = b.parse(x)
            if r is not None:
                return r


class ConditionalP[A, T](P[A, T]):
    def __init__(self, base: P[A, T], p: Callable[[T], bool]):
        self._parser = MapP(base, lambda x: x if p(x) else None)
    def parse(self, x: A) -> Optional[A]:
        return self._parser.parse(x)


## Parsing Lists/Tuples


class ListRepeatP[A, T](P[list[A], list[T]]):
    def __init__(self, item: P[A, T], ignoring=fail_parser):
        self._item = item
        self._ignoring = ignoring

    def parse(self, items: list[A]) -> Optional[list[T]]:
        result = []
        for item in items:
            r_ign = self._ignoring.parse(item)
            if r_ign is not None: continue
            r = self._item.parse(item)
            if r is None: return None
            result.append(r)
        return result


class TupleP[A, T](P[list[A], list[T]]):
    def __init__(self, *p: list[P[A, T]], ignoring=fail_parser):
        self._ignoring = ignoring
        self._ps = p

    def parse(self, xs: list[A]) -> Optional[list[T]]:
        xs_iter = iter(xs)
        result = []
        for p in self._ps:
            for x in xs_iter:
                r_ign = self._ignoring.parse(x)
                if r_ign is not None: continue
                r = p.parse(x)
                if r is None: return None
                result.append(r)
                break
            # if we've exhausted the loop (no break), then nothing parsed for p
            else:
                return None
        # fail if anything left of xs can't be ignored
        for x in xs_iter:
            if self._ignoring.parse(x) is None: return None
        return result


## Misc. helpers


concat_parser = lambda base: MapP(base=base, f=lambda xss: [x for xs in xss for x in xs])
str_concat_parser = lambda base: MapP(base=base, f="".join)

singleton_parser = lambda base, ignoring=fail_parser: MapP(
    base=TupleP(base, ignoring=ignoring),
    f=lambda xs: xs[0],
)


# text, line breaks, TODO: maybe more?
textish_node_parser = AnyP(
    TextNodeP(content=IdentityP()),
    MapP(
        f=lambda _: "\n",
        base=ElementNodeP(
            tag="br",
            content=IdentityP(),
        )
    ),
)

textish_parser = str_concat_parser(ListRepeatP(textish_node_parser))

link_parser = Lift2P(
    base1=ElementNodeP(
        tag="a",
        content=textish_parser,
    ),
    base2=MapP(IdentityP(), f=lambda node: node.attrs.get("href", None)),
    f=lambda text, target: {
        "text": text,
        "target": target,
    },
)

linky_text_parser = ListRepeatP(
    AnyP(
        textish_node_parser,
        link_parser,
    )
)


## Now defining parsers is easy ;)

def definitions_parser():
    """Put this in a function to keep things tidy"""

    # label: word, article, anchor
    def_label_parser = Lift2P(
        base1=link_parser,
        base2=MapP(IdentityP(), f=lambda node: node.attrs.get("id", None)),
        f=lambda link, node_id: {
            "title": link["text"],
            "target": link["target"],
            "id": node_id,
        }
    )

    # a single numbered sub-definition
    multi_def_parser1 = ElementNodeP(
        tag="tr",
        content=MapP(
            TupleP(
                ElementNodeP(tag="td", content=IdentityP()),
                ElementNodeP(
                    tag="td",
                    content=linky_text_parser,
                ),
                ignoring=textish_node_parser,
            ),
            f=lambda t: t[1],
        ),
    )

    # table of numbered sub-definitions
    multi_def_parser = singleton_parser(
        ElementNodeP(
            tag="table",
            content=ListRepeatP(
                multi_def_parser1,
                ignoring=textish_node_parser,
            ),
        ),
        ignoring=textish_node_parser,
    )

    def_body_parser = AnyP(
        MapP(linky_text_parser, f=lambda d: {"kind": "single", "definition": d}),
        MapP(multi_def_parser, f=lambda d: {"kind": "list", "definitions": d}),
    )

    # full definition
    def1_parser = ElementNodeP(
        tag="tr",
        content=MapP(
            f=lambda ts: {"meta": ts[0], "definition": ts[1]},
            base=TupleP(
                ElementNodeP(
                    tag="td",
                    attrs={"valign": "top"},
                    content=singleton_parser(
                        def_label_parser,
                        ignoring=textish_node_parser
                    ),
                ),
                ElementNodeP(
                    tag="td",
                    attrs={"valign": "top"},
                    content=def_body_parser,
                ),
                ignoring=textish_node_parser,
            )
        )
    )

    return concat_parser(base=ListRepeatP(ElementDescendP(def1_parser)))


# overrides, to redirect the target of missing links
definition_id_overrides = {
    "ao": "alkopop",
}

def write_definitions(defs, out_dir, overrides=()):
    out_dir = Path(out_dir)
    overrides = dict(overrides)

    link_prefix = "\u2794\u202f"  # right arrow and narrow no-break space

    def make_display_title(text):
        return text.removesuffix(":")

    def make_file_title(text):
        # TODO: probably more
        return (
            make_display_title(text)
                .replace(" ", "-")
                .replace("[", "")
                .replace("]", "")
        )

    lookup = {}
    for d in defs:
        meta = d["meta"]
        target, did, title = meta["target"], meta["id"], meta["title"]
        if target != "#" + did:
            warn(
                f"in definition of {title!r}: "
                f"target={target!r} and id={did!r} don't match, using id"
            )
        if did in lookup:
            warn(f"duplicate definition for id {did!r}")
        lookup[did] = {
            "file-title": make_file_title(title)
        }

    # TODO: deal with dead links! see stderr output
    dead_links = []

    def unlinky_text(text, ctxt):
        def unlinky1(t):
            if isinstance(t, str):
                return t
            else:
                txt, tgt = t["text"], t["target"]
                # TODO: don't warn on external links
                if not txt.startswith(link_prefix):
                    warn(f"link text {txt!r} doesn't start with prefix {link_prefix!r}")
                if not tgt.startswith("#"):
                    warn(f"link target {tgt!r} doesn't start with prefix '#'")
                txt, tgt = txt.removeprefix(link_prefix), tgt.removeprefix("#")
                tgt = overrides.get(tgt, tgt)
                if tgt not in lookup:
                    warn(f"in {ctxt!r}: dead link {txt!r} to {tgt!r}")
                    dead_links.append((tgt, text))
                    # TODO: handle dead links nicely
                    return f"**{txt}**"
                return f"[[{lookup[tgt]['file-title']} | {txt}]]"
        return "".join(map(unlinky1, text))

    for d in defs:
        did, title = d["meta"]["id"], make_display_title(d["meta"]["title"])
        with (
            (out_dir / make_file_title(title))
                .with_suffix(".md").open("w") as def_file
        ):
            def_file.write(
                f"""---\n"""
                # use json.dumps to ensure titles are valid JSON (and thus YAML)
                f"""title: {json.dumps(title)}\n"""
                f"""permalink: {did}\n"""
                f"""---\n"""
            )

            match d["definition"]["kind"]:
                case "single":
                    def_text = d["definition"]["definition"]
                    def_file.write(unlinky_text(def_text, title).strip())
                    def_file.write("\n")
                case "list":
                    for n, subdef in enumerate(d["definition"]["definitions"], start=1):
                        def_file.write("\n")
                        def_file.write(f"{n}. ")
                        def_file.write(unlinky_text(subdef, title).strip())
                        def_file.write("\n")
                        # TODO: check for line breaks and other things that could break the markdown


def main(argv):
    argument_parser = ArgumentParser(prog=argv[0])
    argument_parser.add_argument("--output-parsed-html", type=Path, help="for debugging")
    argument_parser.add_argument("--output-parsed-jsonl", type=Path, help="for debugging")
    argument_parser.add_argument("--output-parsed-definitions", type=Path, help="for debugging")
    argument_parser.add_argument(
        "--input-html", type=FileType("r"),
        default="-", help="where to read Lexikon HTML"
    )
    argument_parser.add_argument(
        "output_dir", type=Path,
        help="base directory for outputting Lexikon markdown"
    )
    parsed_args = argument_parser.parse_args(argv[1:])

    html_parser = HTMLStructureParser()
    for chunk in iter(lambda: parsed_args.input_html.read(4096), ""):
        html_parser.feed(chunk)

    if parsed_args.output_parsed_html is not None:
        with parsed_args.output_parsed_html.open("w") as html_out:
            for doc in html_parser.children:
                print(doc.html(), file=html_out)
    if parsed_args.output_parsed_jsonl is not None:
        with parsed_args.output_parsed_jsonl.open("w") as jsonl_out:
            for doc in html_parser.children:
                json.dump(doc.json(), jsonl_out, indent=2)

    defintions = definitions_parser().parse(html_parser.children)

    if parsed_args.output_parsed_definitions is not None:
        with parsed_args.output_parsed_definitions.open("w") as defs_out:
            json.dump(defintions, defs_out, indent=2)

    write_definitions(defintions, parsed_args.output_dir, definition_id_overrides)

if __name__ == "__main__":
    main(sys.argv)
