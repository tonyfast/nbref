from bs4 import Tag
from collections.abc import Generator
from functools import wraps


def css_parsed(parsed, attrs=None, level=0):
    """lexical analysis of a parsed css selector, returning the tag name and attributes, supporting a subset of css selectors, and some custom syntax for forms"""
    from cssselect.parser import (
        Selector,
        Class,
        Element,
        Hash,
        Attrib,
        CombinedSelector,
    )

    if attrs is None:
        attrs = dict()
    match parsed:
        case Selector():
            return css_parsed(parsed.parsed_tree, attrs, level=level + 1)
        case Class():
            klasses = attrs.setdefault("klass", [])
            if parsed.class_name not in klasses:
                klasses.append(parsed.class_name)
            return css_parsed(parsed.selector, attrs, level=level + 1)
        case CombinedSelector():
            first = element_from_selector(parsed.selector, attrs, level=level + 1)
            second = element_from_selector(parsed.subselector, None, level=level + 1)
            if parsed.combinator in "> ":
                return el(first, second)
            raise NotImplementedError(f"combinator {parsed.combinator} not implemented")
        case Element():
            return el(Tag(name=parsed.element), **attrs)
        case Attrib():
            attrs.update({parsed.attrib: parsed.value.value})
            return css_parsed(parsed.selector, attrs, level=level + 1)
        case Hash():
            attrs.update(id=parsed.id)
            return css_parsed(parsed.selector, attrs, level=level + 1)
        case list():
            for tree in parsed:
                return css_parsed(tree, attrs, level=level + 1)

def parse_html(object):
    """parse html from a string, returning a Tag or a list of Tags"""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(object, "html.parser")
    # if len(soup.contents) == 1:
    #     return soup.contents[0]
    if not isinstance(soup.contents, list):
        return [soup.contents]
    return soup.contents

def el(
    tag: Tag | str,
    *content: str | Tag,
    klass: list | None = None,
    data: dict | None = None,
    aria: dict | None = None,
    on: dict | None = None,
    item: dict | None = None,
    style: dict | None = None,
    **attrs,
) -> Tag:
    """create or update tag(s) given tag as a selector, content, and attributes

    a fault tolerant way to manipulate html elements, supporting a subset of css selectors, and some custom syntax for forms, and some custom syntax for forms,
    when the tag is an `Tag`, the content and attributes will be added to the tag, otherwise a new tag will be created from the selector and content and attributes added to it.
    """

    if isinstance(tag, str):
        tag = element_from_selector(tag)

    tag.attrs.update(attrs)
    if klass is not None:
        if isinstance(klass, str):
            klass = klass.split()
        klasses = tag.attrs.setdefault("class", [])
        for k in klass:
            if k not in klasses:
                if isinstance(k, str):
                    klasses.append(k)
    classes = []
    for c in tag.attrs.get("class", []):
        if c not in classes:
            classes.append(c)
    tag.attrs["class"] = classes

    if data is not None:
        # the data dict is for custom data attributes, like {"id": "123"}
        tag.attrs.update({f"data-{k}": v for k, v in data.items()})
    if aria is not None:
        # the aria dict is for ARIA attributes, like {"checked": "true"}
        tag.attrs.update({f"aria-{k}": v for k, v in aria.items()})
    if on is not None:
        # the on dict is for event handlers, like {"click": "doSomething()"}
        tag.attrs.update({f"on{k}": v for k, v in on.items()})
    if item is not None:
        # the item dict is for microdata
        tag.attrs.update({f"item{k}": v for k, v in item.items()})

    if style is not None:
        tag.attrs.setdefault("style", "")
        if isinstance(style, dict):
            # the style dict is for inline styles, like {"color": "red"}
            # style_str = "; ".join(f"{k}: {v}" for k, v in style.items())
            
            tag.attrs["style"] = "; ".join(f"{k.replace("_", "-")}: {v}" for k, v in style.items()) + ";"
        elif isinstance(style, str):
            tag.attrs["style"] = style
            if not tag.attrs["style"].endswith(";"):
                tag.attrs["style"] += ";"

    content = [c for c in content if c is not None]
    for object in content:
        if not object:
            continue
        if isinstance(object, (list, tuple, Generator)):
            el(tag, *object)
        else:
            if isinstance(object, (int, float)):
                object = str(object)
            tag.append(object)
    return tag


def element_from_selector(selector, attrs=None, level=0) -> Tag:
    """create a Tag from a css selector, supporting a subset of css selectors, and some custom syntax for forms"""

    if attrs is None:
        attrs = dict()
    if isinstance(selector, str):
        import cssselect
        selector = cssselect.parse(selector)

    tag = css_parsed(selector, attrs)
    if tag is None:
        tag = Tag(name=attrs.pop("tag"), attrs=attrs)
    return el(tag, **attrs)

def separate_schema(func):
    @wraps(func)
    def wrapper(object, schema=None):
        if schema is None: 
            schema = object.schema
        return func(object, schema)
    return wrapper

def infer_schema(*objects):
    """infer the schema from the first object that has a schema attribute, or return None if no object has a schema attribute"""
    from .objects import Object
    import genson
    builder = genson.SchemaBuilder()
    for object in objects:
        builder.add_object(Object.builtin(object))
    return builder.to_schema()
    
def iter_values(object, path=None):
    from nbref import Schema
    if path is None:
        path = []
    if isinstance(object, dict):
        for key, value in object.items():
            yield value
            yield from iter_values(value, path + [key])
    elif isinstance(object, list):
        yield object
        yield from (iter_values(x, path + [i]) for i, x in enumerate(object))
    else:
        yield object

def get_length(object):
    """get the length of an object, returning 1 for non-iterables"""
    if isinstance(object, (list, tuple, dict)):
        return len(object)
    return None

def tracebacks(tb=None):
    """list tracebacks in an exception"""
    tb = getattr(tb, "__traceback__", tb)
    if tb is None:
        tb = sys.last_traceback
    return [x[0] for x in traceback.walk_tb(tb)]