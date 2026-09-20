
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
    unevaluated: bool = False
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
    depth: int = 0
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
                attrs["id"] = schema.id()
            elif isinstance(id, str):
                attrs["id"] = schema.id(id)
            else:
                attrs["id"] = schema.id(*id)
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
    id = schema.id()[-1]
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
    patches = options.patch.get(str(id)[1:])
    if patches:
        patched = patches(schema, options)
        if patched:
            schema = patched
    return schema


def html_root(schema: Schema, options: Options, *children, **attrs):
    schema = html_patch(schema, options)
    core = html_core(schema, options, *children)
    unevaluated = html_unevaluated_properties(schema, options)
    yield from html_parent(schema, options, *core, *unevaluated)

def html_parent(schema: Schema, options: Options, *children):
    # if not options.unevaluated:
    #     children += tuple(html_unevaluated_properties(schema, options))
    for subschema in schema.schemas:
        parent = subschema.get("parent")
        if parent is not None:
            if not parent:
                yield from children
                return
            parent = subschema.child("parent").expand()
            with options.enter(output=False):
                yield from html_root(parent.linked(id=schema.id("parent")), options, *children)
            break
    else:
        yield from children

def html_core(schema: Schema, options: Options, *children):
    types = schema.types()
    readOnly = schema.get("readOnly", False)
    with options.enter(
        input=not readOnly,
    ) as options:
        if options.output:
            content = list(html_content(schema, options))
            yield options.el("output.read", *list(content), role="none", **html_class(schema, options))

        if options.input:
            yield from html_applicator(schema, options, *children)

def html_content(schema: Schema, options: Options, *children, **attrs):
    schema = schema.expand_all()
    content_schema = schema.subschema("contentSchema")
    if content_schema:
        with options.enter(validate=False):
            yield from html_root(content_schema.linked(
                schema.value(), id=schema.id(), type=schema.atype("contentSchema"),
            ), options, *children, **attrs)
        return
    
    content_type = schema.get("contentMediaType")

    if content_type is None:
        types = schema.types()
        if {"array", "object"}.intersection(types):
            return
    callable = options.content.get(content_type)
    if callable is None:
        attrs.setdefault("style", {}).update(display="block")
        yield from html_script(schema, options, *children, **attrs)
        return
    yield from callable(schema, options, *children, **attrs)


def html_applicator(schema: Schema, options: Options, *children):
    yield from html_all_of(schema, options, *children)

def html_all_of(schema: Schema, options: Options, *children):
    for subschema in schema.schemas:
        all_of = subschema.get("allOf", None)
          
        if all_of is not None:
            for i, _ in enumerate(all_of):
                yield from html_root(
                    schema.override(parent={}, allOf=[]).override(subschema.child("allOf", i).expand())
                    .linked(type=schema.atype("allOf",  i)), 
                    options, *children
                )
            break
    # else:
    yield from html_any_of(schema, options, *children)

def html_any_of(schema: Schema, options: Options, *children):
    for subschema in schema.schemas:
        any_of = subschema.get("anyOf", None)
        if any_of is not None:
            for i, _ in enumerate(any_of):
                yield from html_root(
                    schema.override(parent={}, anyOf=[]).override(subschema.child("anyOf", i).expand())
                    .linked(type=schema.atype("anyOf",  i)), 
                    options, *children
                )
            break
    yield from html_one_of(schema, options, *children)


def html_one_of(schema: Schema, options: Options, *children):
    types = schema.types()
    if "integer" in types:
        if "number" in types:
            types.remove("integer")

    for subschema in schema.schemas:
        one_of = subschema.get("oneOf")
        has_one_of = bool(one_of)
        if has_one_of:
            one_of = [
                schema.override(subschema.child("oneOf", i), oneOf=None) 
                for i, _ in enumerate(one_of)
            ]
            break
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
        if has_one_of:
            pass
        else:
            pass
        item = options.el("li.oneOf")
        options.el(ol, item)
        try:
            if options.validate:
                # this might be a suspect construction
                validating = Schema(subschema,).linked(value)
                t = validating.types()
                if "array" not in t and "object" not in t:
                    validating.validate()

            if has_one_of:
                subschema = schema.override(schema.child("oneOf", i)).linked(
                    type=schema.atype("oneOf", i),
                )
            options.el(item, html_validator(subschema, options, *children))
        except ExceptionGroup as exception:
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
            html_validator(not_schema.linked(schema.value(), schema.id()), options, *children)
        )

def html_exception(exception, options):
    ol = options.el("ol.exceptions")
    for exception in exception.exceptions:
        li = options.el("li.exception", str(exception))
        options.el(ol, li)
    yield ol
    
def html_validator(schema: Schema, options: Options, *children):
    yield from html_role(schema, options, *children)
    yield from html_dependent_schema(schema, options, *children)

def html_role(schema: Schema, options: Options, *children):
    tag = schema.get("tagName")
    if tag:
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
    if callable is None:
        yield from html_input_default(schema, options)
        return
    yield from callable(schema, options)

def html_input_default(schema: Schema, options: Options, *children, **attrs):
    
    options.el("input", value=schema.value())

@attrs
def html_list(schema: Schema, options: Options, *children, **attrs):
    object = schema.value()
    ol = options.el("ol.array")
    for i, item in enumerate(object):
        subschema = schema.index(i)
        id = schema.id()
        link = options.el("a", html_path(subschema, options), href=f"#{id}")
        item = options.el("li.array", link, html_root(subschema, options), id=str(id))
        options.evaluated.append(str(subschema.id()))
        options.el(ol, item)
    yield ol

@attrs
def html_associationlist(schema: Schema, options: Options, *children, **attrs):
    object = schema.value()
    
    schema = schema.linked(object)
    ul = options.el("ul")

    if options.unevaluated:
        keys = object
    else:
        properties = schema.get("properties", None)
        if properties is not None:
            keys = list(filter(bool, properties))
        else:
            keys = list(object)
    

    # keys = list(object)
    for key in keys:
        if str(schema.id(key)) in options.evaluated:
                continue

        subschema = schema.property(key)
        if not options.unevaluated:
            if key not in object:
                default = subschema.default()
                if default is None or default is EMPTY:
                    continue
                subschema = subschema.linked(default)
        id = schema.id(key)
        link = options.el("a", html_path(subschema, options), href=f"#{id}")
        item = options.el("li", link, html_root(subschema, options), id=str(id))
        options.evaluated.append(str(subschema.id()))
        options.el(ul, item)
    yield ul

def html_unevaluated_properties(schema: Schema, options: Options, *children, **attrs):
    unevaluated = schema.get("unevaluatedProperties", False)
    if unevaluated:
        if isinstance(schema.value(), dict):
            with options.enter(unevaluated=True) as options:
                yield from html_parent(schema, options, *html_applicator(schema, options, *children, **attrs))

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
    yield from html_path(schema, options)
    yield options.el("span.title", schema.get("title", ""))
    yield options.el("span.type", *schema.types())
    
def html_path(schema: Schema, options: Options, *children, **attrs):
    yield options.el("span.path", str(schema.id()))

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

def html_input_time(schema: Schema, options: Options, *children, **attrs):
    value = schema.value()
    
    yield options.el("input", type="time", value=value, *children, **attrs)
    
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

def html_html(schema: Schema, options: Options, *children, **attrs):
    value = unified_string(schema.value())
    yield from options.el(value, *children, raw=True, **attrs)

def html_markdown(schema: Schema, options: Options, *children, **attrs):
    from midgy.tangle import get_markdown_it
    value = unified_string(schema.value())
    value = get_markdown_it().render(value)
    yield from options.el(value, *children, raw=True, **attrs)

def html_image(schema: Schema, options: Options, *children, **attrs):
    value = unified_string(schema.value())
    mimetype = schema.get("contentMediaType")
    data = F"data:{mimetype};base64,{value}"
    yield options.el("img", *children, src=data, **attrs)

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
    input=html_input,
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
content_mapping.update({
    "text/plain": html_plain,
    "text/html": html_html,
    "text/markdown": html_markdown,
    "application/json": html_script,
    "image/png": html_image,
    "image/jpeg": html_image,
    "image/gif": html_image,
    "image/svg+xml": html_html,
})

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

format_mapping.update({
    "date-time": html_input_time,
})