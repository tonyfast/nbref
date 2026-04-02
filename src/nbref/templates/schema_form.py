"""create html forms from schema and data."""

import copy
from dataclasses import dataclass, field
from os import path
import re
from bs4 import BeautifulSoup, Tag
import bs4
from toolz.curried import *
import cssselect


class WithPath:
    _path = None
    _root = None
    level = 0

    def __new__(cls, *args, **kwargs):
        if args and isinstance(args[0], WithPath):
            return args[0]
        return super().__new__(cls, *args, **kwargs)

    @property
    def root(self):
        if self._root is None:
            return self
        return self._root

    @property
    def path(self):
        if self._path is None:
            return ["#"]
        return self._path

    def set_root(self, root):
        self._root = root
        return self
    
    def set_level(self, level): 
        self.level = level
        return self

    def set_path(self, path):
        self._path = path
        return self

    def get(self, key, default=None):
        try:
            return self[key]
        except KeyError:
            return default

    def __getitem__(self, key):
        object = super().__getitem__(key)
        if isinstance(object, dict):
            return PathDict(object).set_root(self.root).set_path(self.path + [key]).set_level(self.level + 1)
        elif isinstance(object, list | tuple | set):
            return PathList(object).set_root(self.root).set_path(self.path + [key]).set_level(self.level + 1)
        elif isinstance(object, str):
            return PathStr(object).set_root(self.root).set_path(self.path + [key]).set_level(self.level + 1)
        elif isinstance(object, int):
            return PathInt(object).set_root(self.root).set_path(self.path + [key]).set_level(self.level + 1)
        elif isinstance(object, float):
            return PathFloat(object).set_root(self.root).set_path(self.path + [key]).set_level(self.level + 1)
        
        return object

    __truediv__ = set_path
    __matmul__ = set_root


class PathDict(WithPath, dict):
    """a dict that can be accessed with a list of keys, like {"properties": {"name": "value"}}["properties", "name"] -> "value" """


class PathList(WithPath, list):
    """a dict that can be accessed with a list of keys, like {"properties": {"name": "value"}}["properties", "name"] -> "value" """

class PathStr(WithPath, str):
    """a dict that can be accessed with a list of keys, like {"properties": {"name": "value"}}["properties", "name"] -> "value" """

class PathInt(WithPath, int):
    """a dict that can be accessed with a list of keys, like {"properties": {"name": "value"}}["properties", "name"] -> "value" """

class PathFloat(WithPath, float):
    """a dict that can be accessed with a list of keys, like {"properties": {"name": "value"}}["properties", "name"] -> "value" """

############################################################
# top level schema rendering functions, which generate form elements from a schema and data.
############################################################
def render_schema(schema, data, schema_path=None, data_path=None, level=0) -> Tag:
    """top level function for rendering a schema."""
    if schema_path is not None:
        schema = PathDict(schema).set_path(schema_path)
    else:   
        schema = PathDict(schema)
        
    if data_path is not None:
        data = PathDict(data).set_path(data_path)
    else:
        data = PathDict(data)
        
    if level:
        return render_schema_dispatch(schema, data, level)
    return render_schema_form(schema, data, level)


def render_schema_form(schema, data, level=0):
    return el(
        "form.schema",
        render_schema_dispatch(schema, data, level + 1),
        el("button.submit", "submit", type="submit"),
        name=path_name(data.path),
        id=path_name(data.path),
        on=dict(submit="event.preventDefault(); submitSchemaForm.call(this, event)"),
        aria=dict(
            labelledby=path_name(data.path + [":title"]),
            describedby=path_name(data.path + [":desc"]),
        ),
    )


def render_schema_dispatch(schema, data, level=0):
    """generate a form element for a given schema and data, dispatching to different render functions based on the type of the schema"""
    match get_type_from_schema(schema, data) or "string":
        case "object":
            return render_schema_object(schema, data, level)
        case "array":
            return render_schema_array(schema, data, level)
        case "anyof":
            return render_schema_anyof(schema, data, level)
        case "oneof":
            return render_schema_oneof(schema, data, level)
        case "allof":
            return render_schema_allof(schema, data, level)
        case "ifthen":
            return render_schema_ifthen(schema, data, level)
    return render_schema_value(schema, data, level)


############################################################
## schema container renderers, which generate form elements for schema objects, arrays, and combinators.
############################################################

def render_schema_object(schema, data, level=0):
    if data is None:
        # force data to be a dict
        data = {}
    section = el(
        el("section.object", id=path_name(schema.path)),
        render_schema_heading(schema, data, level),
        el("ul.object", id=path_name(data.path)),
    )
    properties = schema.get("properties", {})
    required = schema.get("required", [])
    additional = schema.get("additionalProperties", False)
    if required:
        section.ul.append(item := el("li.required.properties > ul.required.properties"))
        for key in required:
            subschema = properties.get(key, {})
            value = data.get(key)
            property = render_schema_property(subschema, value, level)
            property = el("li.property", property, id=path_name(data.path + [key, ":item"]))
            el(item.ul, el(property, klass=["required", "property"]))

    if properties:
        el(section.ul, item := el("li.object.properties > ul.object.properties"))
        for key in properties:
            if key in required:
                continue
            subschema = properties.get(key, {})
            value = data.get(key)
            property = render_schema_property(subschema, value, level)
            el(item.ul, el("li.property.object", property, id=path_name(data.path + [key, ":item"])))

    if additional:
        el(
            section.ul,
            item := el("li.additional.properties > ul.additional.properties"),
            id=path_name(additional.path),
        )
        for key in data:
            if key in properties or key in required:
                continue
            subschema = additional if isinstance(additional, dict) else {}
            value = data.get(key)
            property = render_schema_property(subschema, value, level)
            el(item.ul, el("li.additional.property", property, id=path_name(data.path + [key, ":item"])))
        if additional is True:
            additional = dict(type="string")
        template_path = path_name(additional.path + ["template"])
        button = el(
            "button.additional",
            "add property",
            on=dict(click=f"addSchemaProperty.call(this, event)"),
            aria=dict(owns=template_path, controls=additional.path),
        )
        property = el("li.additional.property", render_schema_property(additional, None, level=level))
        el(
            item,
            button,
            el(
                f"template",
                el(property, klass="additional properties"),
                id=template_path,
            ),
        )

    return section


def render_schema_array(schema, data, level=0):
    prefixItems = schema.get("prefixItems", [])
    items = schema.get("items", {})
    max_items = schema.get("maxItems", None)
    min_items = schema.get("minItems", None)
    section = el(
        el("section.array", id=path_name(schema.path)),
        render_schema_heading(schema, data, level),
        el("ol.array", id=path_name(schema.path)),
    )
    
    for i, value in enumerate(data):
        print(2,len(prefixItems), prefixItems, i)
        is_prefix = i < len(prefixItems)
        subschema = prefixItems[i] if is_prefix else items
        section.ol.append(
            el(
                "li.array.item",
                render_schema_dispatch(
                    subschema,
                    value,
                    level + 1,
                ),
                aria=dict(posinset=str(i + 1), setsize=str(len(data))),
                id=path_name(data.path + [":item"]),
                klass="prefix" if is_prefix else "additional",
            )
        )
    if items not in [False, None]:
        el(
            section,
            el(
                "button.additional",
                "add item",
                on={"click": "addSchemaItem.call(this, event)"},
            ),
        )
    # a button to add an empty item and the template for the empty item
    return section


def render_schema_anyof(schema, data, level=0):
    return


def render_schema_oneof(schema, data, level=0):
    return


def render_schema_allof(schema, data, level=0):
    # works for now
    schema = schema_compact(schema)
    return render_schema_dispatch(schema, data, level=level)


def render_schema_ifthen(schema, data, level=0):
    return


############################################################
# schema property renderers, which generate form elements for schema properties, which are the key-value pairs in an object schema.
############################################################


def render_schema_property(schema, data, level=0):
    if is_container(schema):
        value = render_schema_dispatch(schema, data, level=level)
        buttons = render_schema_additional(schema, data, level=level)
        return el(
            "li", value, buttons, id=path_name(data.path + [":item"]), klass="property"
        )
    key, value = juxt(render_schema_label, render_schema_dispatch)(
        schema, data, level=level
    )
    desc = el("p", schema_description(schema), id=path_name(schema.path + [":desc"]))
    return key, value, desc


def render_schema_additional(schema, data, level=0):
    if schema.path[-1] == "additionalProperties":
        title = schema_title(schema, schema.path[-1])
        edit = el(
            "button.key",
            "edit",
            on=dict(click="editSchemaPropertyKey.call(this, event)"),
        )
        input = el("input.key.edit", value=title)
        remove = el(
            "button.key.remove",
            "remove",
            on=dict(click="removeSchemaProperty.call(this, event)"),
            aria=dict(controls=path_name(schema.path + [":item"])),
        )
        return edit, remove, input


def render_schema_label(schema, data, level=0):
    title = schema_title(schema, schema.path[-1])
    label = el("label", title, **{"for": path_name(schema.path)})
    return label, render_schema_additional(schema, data, level)

def render_schema_enum(schema, data, level=0):
    item = dict(prop=schema.path[-1])
    if item["prop"] == "unit":
        item.update(prop=path_name(schema.path[-2:]))
    select = el("select", name=path_name(schema.path[1:]), item=item)
    options = schema.get("enum", [])
    object = schema_default(schema, data)
    if isinstance(options, list):
        options = dict(zip(options, options))
    for option, value in options.items():
        opts = {}
        if option == object:
            opts["selected"] = ""
        select.append(el("option", str(option), value=str(value), **opts))
    return select


def render_schema_value(schema, data, level=0):
    if "enum" in schema:
        return render_schema_enum(schema, data, level)
    attrs = dict(id=path_name(schema.path), name=path_name(schema.path[1:]))
    schema = schema_compact(schema)
    input = el(
        "input",
        value=schema_default(schema, data),
        item=dict(prop=schema.path[-1]),
        **attrs,
    )
    if unit := GUNIT(schema):
        # deteremine default unit value``
        return el(
            "span",
            input,
            render_schema_enum(
                PathDict({"enum": unit, "type": "string"}) / schema.path + ["unit"],
                unit,
                level,
            ),
        )
    return input


def render_schema_heading(schema, data, level=0):
    return el(
        "hgroup",
        el(
            f"h{level + 1}",
            schema_title(schema, schema.path[-1]),
            id=path_name(schema.path + [":title"]),
        ),
        el("p", schema_description(schema), id=path_name(schema.path + [":desc"])),
    )


############################################################
# html and css utilities for creating and updating elements.
############################################################


def element_from_selector(selector, attrs=None, level=0) -> Tag:
    """create a Tag from a css selector, supporting a subset of css selectors, and some custom syntax for forms"""

    if attrs is None:
        attrs = dict()
    if isinstance(selector, str):
        selector = cssselect.parse(selector)

    tag = css_parsed(selector, attrs)
    if tag is None:
        tag = bs4.Tag(name=attrs.pop("tag"), attrs=attrs)
    return el(tag, **attrs)


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
            return el(bs4.Tag(name=parsed.element), **attrs)
        case Attrib():
            attrs.update({parsed.attrib: parsed.value.value})
            return css_parsed(parsed.selector, attrs, level=level + 1)
        case Hash():
            attrs.update(id=parsed.id)
            return css_parsed(parsed.selector, attrs, level=level + 1)
        case list():
            for tree in parsed:
                return css_parsed(tree, attrs, level=level + 1)


def el(
    tag: Tag | str,
    *content: str | Tag,
    klass: list | None = None,
    data: list | None = None,
    aria: list | None = None,
    on: list | None = None,
    item: list | None = None,
    **attrs,
) -> Tag:
    """create or update tag(s) given tag as a selector, content, and attributes

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
                klasses.append(k)
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

    content = [c for c in content if c is not None]
    for object in content:
        if not object:
            continue
        if isinstance(object, (list, tuple)):
            el(tag, *object)
        else:
            tag.append(object)
    return tag


############################################################
# schema utilities
############################################################


def get_type_from_schema(schema: dict, data=None) -> str | None:
    """determine the type of a schema"""
    if "type" in schema:
        return schema["type"]

    if (
        "properties" in schema
        or "additionalProperties" in schema
        or "patternProperties" in schema
        or "required" in schema
    ):
        return "object"
    if "items" in schema or "prefixItems" in schema or "additionalItems" in schema:
        return "array"
    match data:
        case dict():
            return "object"
        case list():
            return "array"
        case str():
            return "string"
        case int() | float():
            return "number"
        case bool():
            return "boolean"

    if "allOf" in schema:
        for sub in schema["allOf"]:
            t = get_type_from_schema(sub, data)
            if t is not None:
                return t
    if "anyOf" in schema:
        # should be treated like oneof in UI
        return "anyof"
    if "oneOf" in schema:
        # will need to make template elements
        return "oneof"
    if "if" in schema and ("then" in schema or "else" in schema):
        return "ifthen"
    return None


def is_container(schema):
    """return true if the schema is a container type, which is a type that can contain other types, like object and array"""
    return get_type_from_schema(schema) in [
        "object",
        "array",
        "anyof",
        "oneof",
        "allof",
        "ifthen",
    ]


def schema_default(schema, default=None):
    if default is not None:
        return default
    return schema.get("default", default)


def schema_compact(schema):
    if isinstance(schema, bool):
        return {}
    if "allOf" not in schema:
        return schema
    schema = copy.deepcopy(schema)
    for sub in schema.pop("allOf", []):
        schema.update(sub)
    return schema


def schema_id(schema, default=None):
    if "$id" in schema:
        return schema["$id"]
    return default


def schema_title(schema, default=None):
    if "title" in schema:
        return schema["title"]
    return default


def schema_description(schema, default=None):
    if "description" in schema:
        return schema["description"]
    return default


def schema_unit(schema):
    return schema.get("unit")


GUNIT = schema_unit


def path_name(object, sep=":"):
    """create a urn from a list of path segments, like ["properties", "name"] -> "properties:name" """
    return sep.join(map(str, object))


#############################################################
# tests for the generated html, which can be used to validate the generated html and ensure it meets accessibility standards.


def test_unique_ids(html: Tag):
    ids = [el.attrs["id"] for el in html.select("[id]")]
    print(ids)
    assert len(ids) == len(set(ids)), (
        f"duplicate ids found: {set([id for id in ids if ids.count(id) > 1])}"
    )
    return True


def test_aria_ids(html):
    idrefs = "for aria-labelledby aria-describedby aria-controls aria-owns".split()
    ids = set()
    for idref in idrefs:
        for el in html.select(f"[{idref}]"):
            for id in el.attrs[f"{idref}"].split():
                ids.add(id)
    misses = []
    for id in ids:
        if not html.select(f"[id='{id}']"):
            misses.append(id)

    assert not misses, (
        f"{len(misses)} aria references to non-existent ids found: {misses[:10]}{'...' if len(misses) > 10 else ''}"
    )
    html.select("[aria-labelledby]")
    return True


def test_all(html: Tag):
    return test_unique_ids(html) and test_aria_ids(html)
