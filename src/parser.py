"""Ugly code for an ugly job."""

import sys

from dataclasses import dataclass
from abc import ABCMeta

import json
import re

from html.parser import HTMLParser
from html.entities import name2codepoint

from html.entities import entitydefs

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

            print(
                f"[WARN] @({self._path(extras=[(el, [])])}, {self.getpos()}): "
                f"tag {el.tag!r} not closed, got {tag!r} instead",
                file=sys.stderr
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
    def __init__(self, item: P[A, T]):
        self._item = item

    def parse(self, items: list[A]) -> Optional[list[T]]:
        result = []
        for item in items:
            r = self._item.parse(item)
            if r is None:
                return None
            result.append(r)
        return result

class TupleP[A, T](P[list[A], list[T]]):
    def __init__(self, *p: list[P[A, T]], skip=False):
        self._skip = skip
        self._ps = p
    def parse(self, xs: list[A]) -> Optional[list[T]]:
        xs_iter = iter(xs)
        result = []
        for p in self._ps:
            for x in xs_iter:
                r = p.parse(x)
                if r is None:
                    if self._skip: continue
                    else: return None
                result.append(r)
                break
            # if we've exhausted the loop (no break), then nothing parsed for p
            else:
                return None
        # if not skipping, fail if anything is left of xs
        if not self._skip:
            for _ in xs_iter:
                return None
        return result

## Misc. helpers

concat_parser = lambda base: MapP(base=base, f=lambda xss: [x for xs in xss for x in xs])
str_concat_parser = lambda base: MapP(base=base, f="".join)

singleton_parser = lambda base, skip=False: MapP(
    f=lambda xs: xs[0],
    base=TupleP(base, skip=skip),
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

textish_nodes_parser = str_concat_parser(ListRepeatP(textish_node_parser))

link_parser = Lift2P(
    base1=ElementNodeP(
        tag="a",
        content=textish_nodes_parser,
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

def main():
    html_parser = HTMLStructureParser()
    with open(sys.argv[1], "r") as html_file:
        for chunk in iter(lambda: html_file.read(4096), ""):
            html_parser.feed(chunk)

    with open(sys.argv[2], "w") as out_file:
        for doc in html_parser.children:
            # json.dump(doc.json(), sys.stdout, indent=2)
            print(doc.html(), file=out_file)

    # def fail(msg):
    #     raise ValueError(msg)

    # expect_parser = lambda base, msg="failed": EitherP(
    #     base1=base,
    #     base2=MapP(IdentityP(), f=lambda _: fail(msg))
    # )

    def_label_parser = Lift2P(
        base1=link_parser,
        base2=MapP(IdentityP(), f=lambda node: node.attrs.get("id", None)),
        f=lambda link, node_id: {
            "title": link["text"],
            "target": link["target"],
            "id": node_id,
        }
    )

    def1_parser = ElementNodeP(
        tag="tr",
        content=MapP(
            f=lambda ts: {"meta": ts[0], "definition": ts[1]},
            base=TupleP(
                ElementNodeP(
                    tag="td",
                    attrs={"valign": "top"},
                    content=singleton_parser(def_label_parser, skip=True)
                ),
                ElementNodeP(
                    tag="td",
                    attrs={"valign": "top"},
                    content=AnyP(
                        MapP(linky_text_parser, f=lambda d: {"failed": False, "def": d}),
                        MapP(base=IdentityP(), f=lambda d: {"failed": True, "defstr": str(d), "def": [dd.json() for dd in d]})
                        # IdentityP(),
                        # pure_parser({})
                    )
                    # MapP(base=IdentityP(), f=lambda _: ()),
                ),
                skip=True,
            )
        )
    )

    def_parser = concat_parser(base=ListRepeatP(ElementDescendP(def1_parser)))

    # print(html_parser.children)
    defs = def_parser.parse(html_parser.children)
    json.dump(defs, sys.stdout)
    print(len(defs), file=sys.stderr)
    # 445
    
    # defs = DefinitionParser().parse_top_level(html_parser.children)
    # print(list(defs))


if __name__ == "__main__":
    main()


        # base1=ElementNodeP(
        #     tag="a",
        #     content=singleton_parser(TextNodeP(content=IdentityP())),
        # ),
        # base2=IdentityP(),
        # f=lambda lbl, a_node: {
        #     "title": lbl,
        #     "href": a_node.attrs.get("href", None),
        #     "id": a_node.attrs.get("id", None),
        # }
        
# class DefinitionParser:

#     @classmethod
#     def alt(cls, x, *p):
#         pass

#     def parse_def_tr(self, element: Node):

#         match element:
#             case ElementNode(tag="tr"):
#                 pass
        
#         return None

#     def parse_top_level1(self, element: Node):
#         def1 = self.parse_def_tr(element)
#         if def1 is not None:
#             yield def1
#         else:
#             match element:
#                 case ElementNode():
#                     yield from self.parse_top_level(element.children)
#                 case TextNode():
#                     yield from ()

#     def parse_top_level(self, elements: list[Node]):
#         for el in elements:
#             yield from self.parse_top_level1(el)