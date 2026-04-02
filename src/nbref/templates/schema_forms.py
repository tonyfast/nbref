from functools import partial
from bs4 import Tag
import bs4
import cssselect
import jsonschema

VALIDATOR = jsonschema.Draft202012Validator


class Pointer(list):
    separator = ":"

    def __str__(self):
        return self.separator.join(map(str, self))

    def __getitem__(self, key):
        return Pointed.dispatch(super().__getitem__(key))


class Pointed:
    path: Pointer = None
    root: None = None
    _freeze: bool = False

    def freeze(self, freeze=True):
        self._freeze = freeze
        return self

    def set_root(self, root):
        self.root = root
        return self

    def set_path(self, path):
        self.path = Pointer(path)
        return self

    @classmethod
    def dispatch(cls, object):
        freeze = getattr(object, "_freeze", False)
        value = None
        if isinstance(object, dict):
            return Dict(object).freeze(freeze)
        elif isinstance(object, list | tuple | set):
            return List(object).freeze(freeze)
        elif isinstance(object, int | float | bool):
            return Number(object).freeze(freeze)
        elif isinstance(object, str):
            return Str(object).freeze(freeze)
        elif isinstance(object, type(None)):
            return None
        raise TypeError(f"unsupported type {type(object)} for object {object}")

    def ptr(self, root=None):
        parts = self.path
        if self.path[0] == "#":
            parts = Pointer([root or self.root.get("$id", "#")] + self.path[1:])
        return str(parts)


class Dict(Pointed, dict):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.path is None:
            self.path = Pointer(["#"])
        if self.root is None:
            self.root = self

    def __getitem__(self, key):
        object = super(type(self), self).__getitem__(key)
        if not self._freeze:
            if key == "$ref":
                return schema_ref(self, key, object)
        return (
            self.dispatch(object)
            .set_root(self.root)
            .set_path(self.path + [key])
            .freeze(self._freeze)
        )

    def get(self, key, default=None):
        if key in self:
            return self[key]
        else:
            return default


class List(Pointed, list):
    __getitem__ = Dict.__getitem__


class Str(Pointed, str):
    pass


class Number(Pointed, int):
    pass


import jsonschema_specifications, referencing


def schema_id(schema):
    return schema.ptr()


def schema_title(schema):
    if "title" in schema:
        return schema["title"]
    if schema.path:
        return schema.path[-1]
    if "$id" in schema:
        return schema["$id"]
    return ""


def schema_description(schema):
    return schema.get("description", "")


def schema_ref(schema, key, ref):
    if "$ref" == key:
        resolver = jsonschema_specifications.REGISTRY.resolver_with_root(
            referencing.Resource.from_contents(
                schema.root, referencing.jsonschema.DRAFT202012
            )
        )
        resolved = Pointed.dispatch(resolver.lookup(ref).contents)
        if ref.startswith("#"):
            resolved.set_path(ref.split("/")).set_root(schema.root)
        return resolved
    return None


def render_schema(schema, data, **attrs):
    match schema_type(schema, data):
        case "oneOf":
            return render_one_of(schema, data, **attrs)
        case "anyOf":
            return render_any_of(schema, data, **attrs)
        case "object":
            return render_object(schema, data, **attrs)
        case "array":
            return render_array(schema, data, **attrs)
        case "string":
            return render_string(schema, data, **attrs)
        case "number" | "integer":
            return render_number(schema, data, **attrs)
        case "boolean":
            return render_boolean(schema, data, **attrs)
        case "null":
            return render_null(schema, data, **attrs)
        case _:
            return el("data", value=data, **attrs)


def render_id(schema, data):
    return data.ptr()


def render_label(schema, data, **attrs):
    attrs.setdefault("for", data.ptr())
    attrs["id"] = data.ptr() + "::label"
    return el("label.schema", schema_title(schema), **attrs)


def render_string(schema, data, **attrs):
    if "format" in schema:
        attrs.setdefault("type", schema["format"])
    if "maxLength" in schema:
        attrs.setdefault("maxlength", schema["maxLength"])
    if "minLength" in schema:
        attrs.setdefault("minlength", schema["minLength"])
    if "pattern" in schema:
        attrs.setdefault("pattern", schema["pattern"])
    attrs.setdefault("item", {}).update(prop=str(data.path[-1]))
    return el(render_input(schema, data, **attrs), klass="string")


def render_number(schema, data, **attrs):
    # we could support `format`
    klass = "number"
    if "multipleOf" in schema:
        attrs.setdefault("step", schema["multipleOf"])
    if schema_type(schema, data) == "integer":
        attrs.setdefault("step", "1")
    if "maximum" in schema:
        attrs.setdefault("max", schema["maximum"])
    if "minimum" in schema:
        attrs.setdefault("min", schema["minimum"])
    if "exclusiveMaximum" in schema:
        attrs.setdefault("max", schema["exclusiveMaximum"])
    if "exclusiveMinimum" in schema:
        attrs.setdefault("min", schema["exclusiveMinimum"])
    print(schema, schema.get("readOnly"))
    if schema.get("readOnly"):
        return el("data", str(data), value=str(data), item=dict(
            prop=str(data.path[-1])
        ), **attrs)

    attrs.setdefault("item", {}).update(prop=str(data.path[-1]))
    attrs.setdefault("type", "number")
    attrs.setdefault("id", data.ptr())
    return el(render_input(schema, data, klass=klass, **attrs))


def render_input(schema, data, **attrs):
    if "format" in schema:
        attrs.setdefault("type", schema["format"])
    attrs.setdefault("aria", {}).update(labelledby=data.ptr() + "::label")
    return el("input.schema", value=data, **attrs)


def render_boolean(schema, data, **attrs):
    if data:
        attrs.setdefault("checked", "")
    return el(render_input(schema, data, **attrs), klass="schema.number")


def render_null(schema, data, **attrs):
    return el("data", value=None, **attrs)


def schema_validate(schema, data):
    try:
        VALIDATOR(schema).validate(data)
        return True
    except jsonschema.ValidationError:
        return False


def render_one_of(schema, data, klass="oneOf", **attrs):
    section = el(f"section.schema.{klass}>ol.schema.{klass}")
    for subschema in schema["oneOf"]:
        item = el(f"li.schema.{klass}")
        if schema_validate(subschema, data):
            item.append(el("input.schema.validation", type="checkbox", checked=""))
        else:
            item.append(el("input.schema.validation", type="checkbox"))
        item.append(render_schema(subschema, data))
        section.ol.append(item)
    return section


render_any_of = partial(render_one_of, klass="anyOf")


def render_if_then_else(schema, data, **attrs):
    section = el("section.schema.if.then.else>ol.if.then.else")
    then_valid = schema_validate(schema["if"], data)
    else_valid = not then_valid

    if "then" in schema:
        if then_valid:
            attrs = dict(checked="")
        item = el(
            "li.schema.then", el("input.else.validation", type="checkbox", **attrs)
        )
        item.append(render_schema(schema["then"], data))
        section.ol.append(item)
    if "else" in schema:
        if else_valid:
            attrs = dict(checked="")
        item = el(
            "li.schema.else", el("input.else.validation", type="checkbox", **attrs)
        )
        item.append(render_schema(schema["else"], data))
        section.ol.append(item)
    return section


def render_object_properties(schema, data, keys, klass="object", **attrs):
    items = el(f"li.schema.{klass}.properties>ol.schema.{klass}.properties")
    for key in keys:
        value = data[key]
        subschema = schema.get("properties", {}).get(key, {})
        item = el("li.property", render_label(subschema, value), render_schema(subschema, value), klass=klass)
        items.ol.append(item)
        if klass != "additional":
            # this could also be turned off with dict(aria=dict(describedby=False))
            # the additional description will go after the add button like the items
            # item.append(
            #     el("p", schema_description(subschema), id=schema.ptr() + "::desc")
            # )
            ...
    return items


def render_region(schema, data, *children, **attrs):
    attrs.setdefault("id", schema.ptr() + "::region")
    attrs.setdefault("aria", {}).update(
        labelledby=schema.ptr() + "::title",
        describedby=schema.ptr() + "::desc",
    )
    # class of the type
    section = el(
        "section.schema.region",
        render_hgroup(schema, data),
        *map(el, children),
        **attrs,
    )
    return section


def render_hgroup(schema, data, **attrs):
    return el(
        "hgroup",
        el("h2", schema_title(schema), id=schema.ptr() + "::title"),
        el("p", schema_description(schema), id=schema.ptr() + "::desc"),
        **attrs,
    )


def render_object(schema, data, **attrs):
    section = render_region(schema, data, **attrs)
    section.append(el("ol.schema.object", aria=dict(labelledby=schema.ptr() + "::title"), item=dict(
        type=schema.ptr(), prop=str(data.path[-1]), scope=""
    )))
    properties = list(schema.get("properties", {}).keys())
    required = set(schema.get("required", []))
    additional = schema.get("additionalProperties", False)
    if required:
        section.ol.append(
            render_object_properties(schema, data, required, klass="required")
        )
    if properties:
        keys = [x for x in properties if x not in required]
        section.ol.append(render_object_properties(schema, data, keys, klass="object"))
        
    if additional:
        # should be able to add and remove additional properties
        keys = [x for x in data if x not in required or x not in properties]
        section.ol.append(
            props := render_object_properties(schema, data, keys, klass="additional")
        )
        # a fieldset could work here
        props.li.append(el("button.schema.array.add", "add item"))
        props.li.append(el("button.schema.array.rm", "remove item"))
    return section


def render_array(schema, data, **attrs):
    readonly = attrs.get("readonly", schema.get("readOnly", False))
    if readonly:
        attrs["readonly"] = ""
    section = render_region(
        schema,
        data,
        **attrs
    )
    section.append(el("ol.schema.array", aria=dict(labelledby=schema.ptr() + "::title")))
    el(
        section.ol,
        id=data.ptr(),
        item=dict(type=schema.ptr(), prop=str(data.path[-1]), scope="", id=data.ptr()),
    )
    items = schema.get("items", {})
    prefix_items = schema.get("prefixItems", [])

    for i in range(len(data)):
        attrs = {}
        if i < len(prefix_items):
            subschema = prefix_items[i]
        else:
            subschema = items
        attrs["itemtype"] = subschema.ptr()
        item = data[i]  # we have to use this accessor to track the path for the item
        section.ol.append(el("li.schema.array.item", render_schema(subschema, item)))
    if items and not readonly:
        section.append(el("button.schema.array.add", "add item"))
        section.append(el("button.schema.array.rm", "remove item"))
    return section


def schema_id(schema):
    if "$id" in schema:
        return schema["$id"]
    return None


def schema_type(schema, data):
    if "type" in schema:
        t = schema["type"]
        if isinstance(t, list):
            return "anyOf"
        return t

    if "if" in schema:
        return "ifThenElse"

    if "oneOf" in schema:
        return "oneOf"
    if "anyOf" in schema:
        return "anyOf"

    if (
        "properties" in schema
        or "additionalProperties" in schema
        or "patternProperties" in schema
    ):
        return "object"
    if "items" in schema or "prefixItems" in schema:
        return "array"

    if isinstance(data, str):
        return "string"
    if isinstance(data, bool):
        return "boolean"
    if isinstance(data, float | int):
        return "number"
    if data is None:
        return "null"

    if isinstance(data, dict):
        return "object"
    if isinstance(data, list | tuple | set):
        return "array"
    raise "any"


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
