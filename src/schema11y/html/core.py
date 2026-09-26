
from asyncio import exceptions
from contextlib import contextmanager
from dataclasses import dataclass, field
from functools import partial, wraps
from toolz import pipe, compose_left as compose

from schema11y import schema
from ..types import Schema, Subschema, EMPTY
from ..utils import el_from_selector
class ValidationError(ExceptionGroup):
    pass

role_mapping = dict()
content_mapping = dict()
format_mapping = dict()
tag_mapping = dict()

def debug(callable):
    """a decorator to enable debugging for HTML rendering"""
    def yield_html(schema: Schema, options: Options, *children, **attrs):
        result = callable(schema, options, *children, **attrs)
        if options.debug:
            yield options.el("span.debug.start", "start", str(callable), str(schema.aid()), str(schema.atype()))
        yield from result
        if options.debug:
            yield options.el("span.debug.end", "end", str(callable),str(schema.aid()), str(schema.atype()))

    return yield_html

@dataclass
class Options:
    """Options for HTML rendering and validation."""
    unevaluated: bool = False
    debug: bool = False
    metadata: bool = False
    input_before_output: bool = False
    evaluated: list = field(default_factory=list)
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
    """a decorator to add HTML attributes to the rendered element"""
    if callable is None:
        return lambda f: attrs(f, id=id, **default_attrs)
    @wraps(callable)
    def wrapper(schema: Schema, options: Options, *children, **attrs):
        nonlocal callable
        attrs = html_attrs(schema, options, *children, id="value", **attrs)
        return callable(schema, options, *children, **attrs)
    return wrapper

def html_attrs(schema: Schema, options: Options, *children, id="value", **attrs):
    """compute the HTML attributes for an element based on the schema and options"""
    if id:
        if id is True:
            attrs["id"] = schema.aid()
        elif isinstance(id, str):
            attrs["id"] = schema.aid(id)
        else:
            attrs["id"] = schema.aid(*id)
        attrs["id"] = str(attrs["id"])

    attrs.update(html_class(schema, options, **attrs))
    return attrs


def html_class(schema: Schema, options: Options, *children, **attrs):
    """compose the html classes for an element"""
    classes = attrs.get("class", [])
    if isinstance(classes, str):
        classes = [classes]
    else:
        classes = list(classes)
    for subschema in schema.schemas:
        tags = subschema.get("tags")
        if tags:
            if isinstance(tags, list):
                classes.extend(tags)
            elif isinstance(tags, str):
                classes.append(tags)
    attrs = schema.subschema("attrs")
    atype = schema.atype()[-1]
    if isinstance(atype, str):
        classes.append(atype)
    classes.append(schema.role(input=True))
    for attrs in attrs.schemas:
        cls = attrs.get("class")
        if cls:
            if isinstance(cls, list):
                classes.extend(cls)
            elif isinstance(cls, str):
                classes.append(cls)
    classes.extend(schema.types())
    # id = schema.id()
    # if isinstance(id, str):
    #     classes.append(id)
    if classes:
        return {"class": list(set(classes) - {None})}
    return {}

def html_render(schema: Schema, options: Options = Options(), **opts):
    """render a schema as HTML"""
    from IPython.display import display, HTML
    return HTML("".join(map(str, html_bs4(schema, options, **opts))))

def html_bs4(schema: Schema, options: Options, *children, **opts):
    """render a schema as HTML object using the BeautifulSoup backend"""
    # initialize the options for this specific run of the task.
    # use an explicit Option to object state after execution;
    # a new options class is needed for every run because evaluated must be reset
    if isinstance(options, dict):
        options = Options(**options)
    elif options is None:
        options = Options()
    options.__dict__.update(**opts)
    options.evaluated = []
    
    yield from html_root(schema, options)

@debug
def html_frame(schema: Schema, options: Options, *children, **attrs):
    """render the boundaries and extent of the object."""
    # html core lies inside the frame
    # parent establishes the width of the frame
    schema = html_patch(schema, options)
    core = html_core(schema, options, *children)
    unevaluated = html_unevaluated_properties(schema, options)
    yield from html_parent(schema, options, *core, *unevaluated)

html_root = html_frame

def html_patch(schema: Schema, options: Options = Options, **attrs):
    """apply patches to the schema."""
    id = schema.atype()
    patches = options.patch.get(str(id)[1:])
    if patches:
        patched = patches(schema, options)
        if patched:
            schema = patched
    return schema

def html_parent(schema: Schema, options: Options, *children):
    """render the parent container around the core"""
    for subschema in schema.schemas:
        parent = subschema.get("parent")
        
        if parent is not None:
            
            if not parent:
                if parent is False:
                    break
                continue
            parent = schema.subschema("parent").override(
                tags=html_class(schema, options)["class"]
            ).expand_all()
            children = children
            insert, append = parent.get("insert", []), parent.get("append", [])
            inserts, appends = [], []
            for i, insert in enumerate(insert):
                inserts.extend(list(html_root(Subschema(insert).expand(), options)))
            for append in append:
                appends.extend(list(html_root(Subschema(append).expand(), options)))
            with options.enter(output=False, input=True) as options:
                yield from html_root(parent.linked(id=schema.id("parent")), options, *inserts, *children, *appends)
            return
    yield from children
    

@debug
def html_core(schema: Schema, options: Options, *children):
    """render the core content of the object beginning by splitting it into input and output sections."""
    # fetch-execute is the only constant in computing, so be benefit from this separation.
    # the output area provides a definitive region for the value of an object.
    # this is important because of the jsonschema applicators offer multiple inputs for a single output.
    # this separation lets us handle the form vs output accessibility independently.
    types = schema.types()
    readOnly = schema.get("readOnly", False)
    new_options = {}
    if readOnly:
        new_options.update(output=True, input=False)
        
    with options.enter(
        **new_options
    ) as new_options:
        input = new_options.input
        applicator = html_applicator(schema, new_options, *children)
        if new_options.input_before_output:
            if input:
                yield from applicator
        if new_options.output or not input:
            content = html_content(schema, new_options)
            yield new_options.el("output.read", *content, role="none", **html_class(schema, new_options))
        if not new_options.input_before_output:
            if input:
                yield from applicator
    
    

def html_content(schema: Schema, options: Options, *children, **attrs):
    """render the content schema that decides influences the output representation"""
    # a schema can contain either a contentMediaType or a contentSchema.
    # the contentMediaTypes are extensible through the options parameters.
    # meanwhiile contentSchema can be used for a fully custom representation.
    schema = schema.expand_all()
    content_schema = schema.subschema("contentSchema")
    if content_schema:
        with options.enter(validate=False) as options:
            
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

@debug
def html_applicator(schema: Schema, options: Options, *children, **attrs):
    """begin rendering the applicator schema keys"""
    # the applicator schema keys provide ways to combine multiple schema.
    yield from html_all_of(schema, options, *children)

@debug
def html_all_of(schema: Schema, options: Options, *children, **attrs):
    for subschema in schema.schemas:
        all_of = subschema.get("allOf", None)
          
        if all_of is not None:
            for i, _ in enumerate(all_of):
                tmp = schema.override(parent={}, allOf=[]).override(subschema.child("allOf", i).expand()).linked(type=schema.atype("allOf",  i))
                children = html_applicator(tmp, options)
                yield from html_parent(tmp, options, *children)
            break
    # else:
    yield from html_any_of(schema, options, *children)

@debug
def html_any_of(schema: Schema, options: Options, *children, **attrs):
    for subschema in schema.schemas:
        any_of = subschema.get("anyOf", None)
        if any_of is not None:
            for i, _ in enumerate(any_of):
                children = html_applicator(
                    schema.override(parent={}, anyOf=[]).override(subschema.child("anyOf", i).expand())
                    .linked(type=schema.atype("anyOf",  i)), 
                    options, *children
                )
                yield from html_parent(
                    schema.override(parent={}, anyOf=[]).override(subschema.child("anyOf", i).expand())
                    .linked(type=schema.atype("anyOf",  i)), options, *children
                )
            break
    yield from html_one_of(schema, options, *children)

@debug
def html_one_of(schema: Schema, options: Options, *children, **attrs):
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
            options.el(item, (html_applicator if has_one_of else html_validator)(subschema, options, *children))
            
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
    yield from html_metadata(schema, options, *children)

@debug
def html_role(schema: Schema, options: Options, *children):
    tag = schema.get("tagName")
    if tag:
        yield from html_tag(schema, options, *children)
        return
    
    role = schema.role()
    
    callable = options.role.get(role)
    if callable is None:
        callable = options.role.get(None)
    yield from callable(schema, options, *children)

def html_tag(schema: Schema, options: Options, *children, **attrs):
    tag = schema.get("tagName")
    attrs = html_attrs(schema, options, *children, id=False, **attrs)
    if tag:
        callable = options.tag.get(tag)
        if callable:
            yield from callable(schema, options, *children, **attrs)
        else:
            yield options.el(tag, *children, **attrs)

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
    yield options.el("input", value=schema.value())

@attrs
def html_list(schema: Schema, options: Options, *children, **attrs):
    object = schema.value()
    role = schema.role()
    if role != "list":
        attrs["role"] = role
    ol = options.el("ol", **attrs)

    for i, item in enumerate(object):
        subschema = schema.index(i)
        patched = html_patch(subschema, options, **attrs)
        attrs = html_attrs(patched, options, *children, id=True)
        id = attrs["id"]
        link = options.el("a.path", html_path(subschema, options), href=f"#{id}")
        item = options.el("li.array", link, html_root(subschema, options), **attrs)
        attrs.setdefault("aria", {}).update(dict(posinset=i+1, setsize=len(object)))
        options.evaluated.append(str(id))
        options.el(ol, item)
    yield ol

@attrs
def html_associationlist(schema: Schema, options: Options, *children, **attrs):
    object = schema.value()
    role = schema.role()
    if role != "associationlist":
        attrs["role"] = role
    schema = schema.linked(object)
    ul = options.el("ul", **attrs)

    object = schema.default({}) | object
    if options.unevaluated:
        keys = object
    else:
        keys = schema.get("required", [])
        properties = schema.get("properties", None)
        if properties is not None:
            for prop in properties:
                if prop not in keys:
                    if prop in object:
                        keys.append(prop)
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
        link = options.el("a.path", html_path(subschema, options), href=f"#{id}")
        patched = html_patch(subschema, options, **attrs)
        attrs = html_attrs(patched, options, *children, id=True)
        item = options.el("li", link, html_root(subschema, options), **attrs)
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
    # yield from children

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
    yield options.el("span.path", *(options.el("span", str(x)) if isinstance(x, str) else options.el("data", str(x+1), value=x) for x in schema.aid()))

def html_metadata(schema: Schema, options: Options, *children, **attrs):
    # this really isnt about on an off but about verbosity labels, descriptions, details¬
    if options.metadata:
        yield from html_description(schema, options)
        yield from html_examples(schema, options)

def html_description(schema: Schema, options: Options, *children, **attrs):
    description = schema.get("description", "")
    if description:
        yield options.el("p.description", unified_string(description), id=schema.id("description"))

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
    if schema.value:
        attrs["checked"] = ""
    yield options.el("input", type="checkbox", **attrs)
    yield from html_label(schema, options, **attrs)

@attrs  
def html_landmark(schema: Schema, options: Options, *children, tag="section", **attrs):
    heading = html_heading(schema, options)
    metadata = html_metadata(schema, options) 
    yield options.el(tag, heading, metadata, *children, **attrs)

def html_heading(schema: Schema, options: Options, *children, **attrs):
    yield options.el(f"h{options.heading}", html_title(schema, options), **attrs)
    
def html_link(schema: Schema, options: Options, *children, **attrs):
    yield options.el("a", *children, **attrs)

@attrs
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
    # this needs links to lines of code
    # render each line separately
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

@attrs
def html_navigation(schema: Schema, options: Options, *children, **attrs):
    yield options.el("nav", *children, **attrs)

def html_toolbar(schema: Schema, options: Options, *children, **attrs):
    object = schema.value()
    if isinstance(object, list):
        yield from html_list(schema, options, *children, **attrs)
    elif isinstance(object, dict):
        yield from html_associationlist(schema, options, *children, **attrs)

def html_iframe(schema: Schema, options: Options, *children, **attrs):
    if "src" not in attrs:
        attrs["srcdoc"] = "".join(map(str, children))
    attrs["width"] = "100%"
    attrs["height"] = "600"
    yield options.el("iframe", **attrs)

# the role mapping definition contains commented entries for roles that are not yet implemented
role_mapping[None] = html_plain
role_mapping.update(
    associationlist=html_associationlist,
    banner=partial(html_landmark, tag="header"),
    # button=html_button,
    checkbox=html_checkbox, 
    code=html_code,
    complementary=partial(html_landmark, tag="aside"),
    contentinfo=partial(html_landmark, tag="footer"),
    # definition=html_definition,
    dialog=html_dialog,
    # feed=html_feed,
    figure=html_figure,
    form=html_form,
    group=html_details,
    heading=html_heading,
    # img=html_img,
    input=html_input,
    link=html_link,
    list=html_list,
    main=partial(html_landmark, tag="main"),
    # menu=html_menu,
    # meter=html_meter,
    navigation=html_navigation,
    # note=html_note,
    radiogroup=html_radiogroup,
    region=html_landmark,
    # search=html_search,
    select=html_select,
    spinbutton=html_number,
    # switch=html_switch,
    # tab=html_tab,
    text=html_plain,
    textbox=html_textbox,
    time=html_time,
    # timer=html_timer,
    toolbar=html_toolbar,
    # tooltip=html_tooltip,
    # tree=html_tree,
)

content_mapping[None] = html_plain
content_mapping.update({
    "text/plain": html_plain,
    "application/json": html_script,
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
    iframe=html_iframe,
)

format_mapping.update({
    "date-time": html_input_time,
})