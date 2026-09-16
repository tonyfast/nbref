
from asyncio import exceptions
from contextlib import contextmanager
from dataclasses import dataclass, field
from functools import partial, wraps
import typing 
from numpy import isin
from toolz import pipe, compose_left as compose
from .types import Schema, Subschema, EMPTY
from .utils import el_from_selector
class ValidationError(ExceptionGroup):
    pass

role_mapping = dict()
content_mapping = dict()
format_mapping = dict()
tag_mapping = dict()

@dataclass
class Options:
    evaluated: list = field(default_factory=role_mapping.copy)
    role: dict = field(default_factory=role_mapping.copy)
    content: dict = field(default_factory=content_mapping.copy)
    format: dict = field(default_factory=format_mapping.copy)
    patch: dict = field(default_factory=dict)
    # patch schema
    tag: dict = field(default_factory=tag_mapping.copy)
    el: callable = field(default_factory=lambda: el_from_selector)
    validate: bool = True
    input: bool = True
    output: bool = True
    heading: int = 1
    def enter(self, **kwargs):
        @contextmanager
        def wrapper():
            before = vars(self).copy()
            self.__dict__.update(**kwargs)
            yield self
            vars(self).update(before)
            
        return wrapper()


def attrs(callable=None, id="value", **default_attrs):
    if callable is None:
        return lambda f: attrs(f, id=id, **default_attrs)
    @wraps(callable)
    def wrapper(schema: Schema, options: Options, *children, **attrs):
        nonlocal callable
        for key, value in default_attrs.items():
            attrs.setdefault(key, value)
        if id:
            if id is True:
                attrs["id"] = schema.aid()
            elif isinstance(id, str):
                attrs["id"] = schema.aid(id)
            else:
                attrs["id"] = schema.aid(*id)
            attrs["id"] = str(attrs["id"])
        attrs.update(html_class(schema, options, **attrs))
        return callable(schema, options, *children, **attrs)
    return wrapper
    return main

def html_class(schema: Schema, options: Options, *children, **attrs):
    classes = attrs.get("class", [])
    if isinstance(classes, str):
        classes = [classes]
    else:
        classes = list(classes)
    tags = schema.get("tags")
    if tags:
        if isinstance(tags, list):
            classes.extend(tags)
        elif isinstance(tags, str):
            classes.append(tags)
    attrs = schema.subschema("attrs")
    for attrs in attrs.schemas:
        cls = attrs.get("class")
        if cls:
            if isinstance(cls, list):
                classes.extend(cls)
            elif isinstance(cls, str):
                classes.append(cls)
    classes.extend(schema.types())
    id = schema.aid()[-1]
    if isinstance(id, str):
        classes.append(id)
    if classes:
        return {"class": classes}
    return {}

def html_render(schema: Schema, options: Options = Options(), **opts):
    from IPython.display import display, HTML
    return HTML("".join(map(str, html_bs4(schema, options, **opts))))

def html_bs4(schema: Schema, options: Options, *children, **opts):
    if isinstance(options, dict):
        options = Options(**options)
    elif options is None:
        options = Options()
    options.__dict__.update(**opts)
    options.evaluated = []
    yield from html_root(schema, options)

def html_patch(schema: Schema, options: Options = Options):
    id = schema.atype()
    print(str(id), str(id) in options.patch)
    patches = options.patch.get(str(id)[1:])
    if patches:
        patched = patches(schema, options)
        if patched:
            schema = patched
    return schema


def html_root(schema: Schema, options: Options, *children, **attrs):
    schema = html_patch(schema, options)
    yield from html_parent(schema, options, *html_core(schema, options, *children))

def html_parent(schema: Schema, options: Options, *children):
    parent = schema.subschema("parent")
    if parent.schemas:
        with options.enter(output=False):
            yield from html_root(parent.linked(id=schema.aid("parent")), options, *children)
    else:
        yield from children

def html_core(schema: Schema, options: Options, *children):
    types = schema.types()
    if options.output:
        content = html_content(schema, options)
        yield options.el("output.read", *content, role="none", **html_class(schema, options))
    if options.input:
        yield from html_applicator(schema, options, *children)

def html_applicator(schema: Schema, options: Options, *children):
    yield from html_all_of(schema, options, *children)

def html_all_of(schema: Schema, options: Options, *children):
    all_of = schema.get("allOf")
    if all_of:
        for i, subschema in enumerate(all_of):
            yield from html_one_of(
                schema.override(schema.child("allOf", i), allOf=[])
                .linked(type=schema.atype("allOf",  i)), 
                options, *children
            )
    else:
        yield from html_one_of(schema, options, *children)

def html_one_of(schema: Schema, options: Options, *children):
    types = schema.types()
    if "integer" in types:
        if "number" in types:
            types.remove("integer")
    one_of = schema.get("oneOf")
    has_one_of = bool(one_of)

    if has_one_of:
        one_of = [schema.override(schema.child("oneOf", i), oneOf=None) for i, subschema in enumerate(one_of)]
    else:
        role = schema.role()
        
        if not role and len(types) > 1:
            one_of = [schema.override(type=t) for t in types]
        else:
            one_of = [schema]
        
    exceptions = []
    ol = options.el("ol.oneOf")
    value = schema.value()
    for i, subschema in enumerate(one_of):
        item = options.el("li.oneOf")
        options.el(ol, item)
        try:
            if options.validate:
                validating = Schema(subschema).linked(value)
                t = validating.types()
                if "array" not in t and "object" not in t:
                    validating.validate()

            if has_one_of:

                subschema = schema.override(schema.child("oneOf", i)).linked(
                    type=schema.atype("oneOf", i),
                )
            options.el(item, html_validator(subschema, options, *children))
        except ExceptionGroup as exception:
            print(exception, exception.exceptions)
            exceptions.append(exception)
            subschema = schema.override(subschema).linked(
                subschema.default(), type=schema.atype("oneOf", i),
            )
            options.el(item, html_validator(subschema, options))
            options.el(item, html_exception(exception, options))

    if exceptions:
        if len(exceptions) == len(one_of):
            schema = schema.override((~Subschema.infer(schema.value())).expand())
        yield ol
    elif len(one_of) == 1:
        children = item.children
        yield from children
    else:
        yield ol
    yield from html_not(schema, options)

def html_dependent_schema(schema: Schema, options: Options, *children, **attrs):
    dependent_schema = schema.subschema("dependentSchemas")
    if dependent_schema:
        keys = set()
        for subschema in dependent_schema.schemas:
            for key in subschema.object():
                if key not in keys:
                    keys.add(key)
                    yield from html_validator(dependent_schema.subschema(key), options, *children)

def html_not(schema: Schema, options: Options, *children, **attrs):
    not_schema = schema.subschema("not")
    if not_schema:
        yield from html_details(
            Schema(title="not!", role="group"), options,
            html_validator(not_schema.linked(schema.value(), schema.aid()), options, *children)
        )

def html_exception(exception, options):
    ol = options.el("ol.exceptions")
    for exception in exception.exceptions:
        li = options.el("li.exception", str(exception))
        options.el(ol, li)
    yield ol

def html_content(schema: Schema, options: Options, *children, **attrs):
    content_schema = schema.subschema("contentSchema")
    if content_schema:
        with options.enter(input=True, output=False, validate=False):
            yield from html_root(content_schema.linked(
                schema.value(), id=schema.aid(), type=schema.atype("contentSchema"),
            ), options, *children, **attrs)
        return
    
    content_type = schema.get("contentMediaType")
    callable = options.content.get(content_type)
    if callable is None:
        attrs.setdefault("style", {}).update(display="block")
        yield from html_script(schema, options, *children, **attrs)
        return
    yield from callable(schema, options, *children, **attrs)

    
def html_validator(schema: Schema, options: Options, *children):
    yield from html_role(schema, options, *children)
    yield from html_dependent_schema(schema, options, *children)

def html_role(schema: Schema, options: Options, *children):
    tag = schema.get("tagName")
    if tag:
        print(tag)
        callable = options.tag.get(tag)
        if callable:
            yield from callable(schema, options, *children)
            return
    role = schema.role()
    callable = options.role.get(role)
    if callable is None:
        callable = options.role.get(None)
    yield from callable(schema, options, *children)

def html_input(schema: Schema, options: Options, *children, **attrs):
    yield from html_format(schema, options)

def html_format(schema: Schema, options: Options, *children, **attrs):
    format = schema.get("format")
    callable = options.format.get(format)
    yield from callable(schema, options)

@attrs
def html_list(schema: Schema, options: Options, *children, **attrs):
    object = schema.value()
    ol = options.el("ol.array")
    for i, item in enumerate(object):
        subschema = schema.index(i)
        id = schema.aid()
        link = options.el("a", html_title(subschema, options), href=f"#{id}")
        item = options.el("li.array", link, html_root(subschema, options), id=str(id))
        options.evaluated.append(str(subschema.aid()))
        options.el(ol, item)
    yield ol

@attrs
def html_associationlist(schema: Schema, options: Options, *children, **attrs):
    object = schema.value()
    ul = options.el("ul")
    for key in object:
        subschema = schema.property(key)
        id = schema.aid()
        link = options.el("a", html_title(subschema, options), href=f"#{id}")
        item = options.el("li", link, html_root(subschema, options), id=str(id))
        options.evaluated.append(str(subschema.aid()))
        options.el(ul, item)
    yield ul

def html_plain(schema: Schema, options: Options, *children, **attrs):
    object = schema.value()
    yield str(object)
    yield from children

def html_script(schema: Schema, options: Options, *children, **attrs):
    content_type = schema.get("contentMediaType")
    value = schema.value()
    yield options.el("script", str(value), type=content_type, **attrs)

def unified_string(string):
    if string is None:
        return ""
    if isinstance(string, list):
        return "".join(unified_string(s) for s in string)
    return str(string)

def html_paragraph(schema: Schema, options: Options, *children, **attrs):
    yield options.el("p", unified_string(schema.value()))

@attrs
def html_textbox(schema: Schema, options: Options, *children, **attrs):
    expanded = schema.subschema("aria").get("multiline", False)
    if expanded:
        yield from html_textarea(schema, options, **attrs)
        return
    yield from html_label(schema, options, **attrs)
    attrs["value"] = unified_string(schema.value())
    yield options.el("input", type="text", **attrs)

def html_textarea(schema: Schema, options: Options, *children, **attrs):
    yield from html_label(schema, options, **attrs)
    yield options.el("textarea", unified_string(schema.value()), **attrs)

def html_label(schema: Schema, options: Options, *children, **attrs):
    label_attrs = {"for": attrs.get("id")}
    label_attrs["for"] or label_attrs.pop("for")

    yield options.el("label", html_title(schema, options), **label_attrs)

def html_title(schema: Schema, options: Options, *children, **attrs):
    yield options.el("span.path", str(schema.aid()))
    yield options.el("span.title", schema.get("title", ""))
    yield options.el("span.type", *schema.types())

def html_metadata(schema: Schema, options: Options, *children, **attrs):
    yield from html_description(schema, options)
    yield from html_examples(schema, options)

def html_description(schema: Schema, options: Options, *children, **attrs):
    yield options.el("p.description", unified_string(schema.value()))

def html_examples(schema: Schema, options: Options, *children, **attrs):
    for example in schema.get("examples", []):
        yield options.el("pre.example", unified_string(example))

@attrs
def html_number(schema: Schema, options: Options, *children, **attrs):
    yield from html_label(schema, options, **attrs)
    attrs.update(
        value=str(schema.value())
    )
    yield options.el("input", type="number", **attrs)


@attrs
def html_checkbox(schema: Schema, options: Options, *children, **attrs):
    yield from html_plain(schema, options)
    yield from html_label(schema, options, **attrs)

@attrs  
def html_landmark(schema: Schema, options: Options, *children, tag="section", **attrs):
    heading = html_heading(schema, options)
    metadata = html_metadata(schema, options) 
    yield options.el(tag, heading, metadata,     *children, **attrs)

def html_heading(schema: Schema, options: Options, *children, **attrs):
    yield options.el(f"h{options.heading}", html_title(schema, options), **attrs)
    
def html_link(schema: Schema, options: Options, *children, **attrs):
    yield options.el("a", *children, **attrs)

def html_details(schema: Schema, options: Options, *children, **attrs):
    if schema.subschema("aria").get("expanded", True):
        attrs["open"] = ""
    summary = options.el("summary", html_title(schema, options))
    yield options.el("details", summary, *children, **attrs)

def html_dialog(schema: Schema, options: Options, *children, **attrs):
    expanded = schema.subschema("aria").get("expanded", False)
    if expanded:
        yield from html_dialog_expanded(schema, options, *children, **attrs)
        return
    heading = html_heading(schema, options)
    metadata = html_metadata(schema, options)
    button = options.el("button", "Close", type="button")
    yield options.el("dialog", heading, metadata, button, *children, **attrs)
    open = options.el("button", "Open", html_title(schema, options), type="button") 
    yield open

def html_dialog_expanded(schema: Schema, options: Options, *children, **attrs):
    heading = html_heading(schema, options)
    metadata = html_metadata(schema, options)
    button = options.el("button", "Close", type="button")
    yield options.el("dialog", heading, metadata, button, *children, **attrs)

@attrs
def html_select(schema: Schema, options: Options, *children, **attrs):
    yield from html_label(schema, options, **attrs)
    enum = schema.get("enum", [])
    select = options.el("select", *children, **attrs)
    value = schema.value()
    
    for option in enum:
        attrs= {}
        if value == option:
            attrs["selected"] = ""
        options.el(select, options.el("option", str(option), value=str(option), **attrs))
    yield select

def html_figure(schema: Schema, options: Options, *children, **attrs):
    figcaption = options.el("figcaption", html_title(schema, options))
    figure = options.el("figure", figcaption, *children, **attrs)
    yield figure
    
def html_time(schema: Schema, options: Options, *children, **attrs):
    value = schema.value()
    if value is not None:
        attrs["datetime"] = str(value)
    yield options.el("time", value, *children, **attrs)
    
def html_code(schema: Schema, options: Options, *children, **attrs):
    value = schema.value()
    pre = options.el("pre>code")
    options.el(pre.code, unified_string(value), *children, **attrs)
    yield pre



def html_fieldset(schema: Schema, options: Options, *children, **attrs):
    legend = options.el("legend", html_title(schema, options))
    fieldset = options.el("fieldset", legend, *children, **attrs)
    yield fieldset

def html_form(schema: Schema, options: Options, *children, **attrs):
    heading = html_heading(schema, options)
    metadata = html_metadata(schema, options)
    yield options.el("form", heading, metadata, *children, **attrs)

def html_radiogroup(schema: Schema, options: Options, *children, **attrs):
    fieldset = next(html_fieldset(schema, options, *children, **attrs))
    enum = schema.get("enum", [])
    for option in enum:
        attrs = {}
        if schema.value() == option:
            attrs["checked"] = ""
        options.el(fieldset, options.el("input", type="radio", value=str(option), **attrs))
        options.el(fieldset, html_label(schema, options, **attrs))
    yield fieldset

role_mapping[None] = html_plain
role_mapping.update(
    associationlist=html_associationlist,
    banner=partial(html_landmark, tag="header"),
    checkbox=html_checkbox, 
    code=html_code,
    complementary=partial(html_landmark, tag="aside"),
    contentinfo=partial(html_landmark, tag="footer"),
    dialog=html_dialog,
    figure=html_figure,
    form=html_form,
    heading=html_heading,
    link=html_link,
    list=html_list,
    main=partial(html_landmark, tag="main"),
    group=html_details,
    radiogroup=html_radiogroup,
    region=html_landmark,
    select=html_select,
    spinbutton=html_number,
    text=html_plain,
    textbox=html_textbox,
    time=html_time,
)
content_mapping[None] = html_plain

tag_mapping.update(
    aside=role_mapping["complementary"],
    code=role_mapping["code"],
    footer=role_mapping["contentinfo"],
    details=role_mapping["group"],
    dialog=role_mapping["dialog"],  
    fieldset=html_fieldset,
    form=role_mapping["form"],
    header=role_mapping["banner"],
    h=role_mapping["heading"],
    main=role_mapping["main"],
    section=role_mapping["region"],
    time=role_mapping["time"],
)