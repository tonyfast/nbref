
import collections
from dataclasses import dataclass, field
from functools import partial
from turtle import title

from nbref import html, schema


from .schemas import Schema, EMPTY
from .utils import el, parse_html

def html_render(schema, object=EMPTY, options=None, **attrs):
    return html_bs4(schema, object=object, options=options, **attrs)

def html_bs4(schema, object=EMPTY, options=None, **attrs):
    if options is None:
        options = Options()
    if object is not EMPTY:
        schema = Schema.__call__(schema, object)
    html = list(html_root(schema, options, **attrs))
    if len(html) == 1:
        return html[0]
    return options.el("div", *html, **attrs)

def html_parent(schema, options=None, *children, **attrs):
    """render the parent of a schema and object"""
    position = str(schema.path)
    modifier = options.schema_patch.get(position)
    if modifier:
        modified = modifier(schema, options, **attrs)
        schema = schema if modified is None else modified
    core = html_core(schema, options, **attrs)
    parent = schema.get("parent")
    if parent and parent is not Schema.Expanded:
        yield from html_role(parent.reflect(Schema(parent, schema)), options, core, *children, **attrs)
    else:
        yield from core 

def html_tag(schema, options=None, *children, tag="div", **attrs):
    """render a schema and object as a tag"""
    yield options.el(tag, *children, **attrs)    

def html_landmark(schema, options=None, *children, tag="section", **attrs):
    """render a schema and object as a tag"""
    yield from html_tag(schema, options, *children, tag=tag, **attrs)

def html_core(schema, options, *children, **attrs):
    """the core html representation of a schema and object"""
    # if "role" in schema or "contentMediaType" in schema:
    #     # role and contentMediaType are explicit type declarations.
    #     # role refers to the input declaration.
    #     # contentMediaType refers to the output declaration a default of "text/plain"
    #     explicit = list(html_role(schema, options, *children, **attrs))
    #     if explicit:
    #         yield from explicit
    #         return
    # otherwise we infer the type declarations from the schema
    schema = Schema.expand(schema)
    # input is more complicated type system that output, and it is validated
    t = Schema.type(schema)
    read = schema.get("readOnly", False) or schema.get("readonly", False)
    write = schema.get("writeOnly", False) or schema.get("writeonly", False)
    input, output = options.input, options.output

    if not (read or write):
        read, write = output, input

    if input:
        options.output = read
    if output: 
        options.input = write    
    content = None

    if read:
        content = list(html_content(schema, options, **attrs))
        yield options.el("output.read", *content)

    if write or not content:
        yield from html_applicator(schema, options, **attrs)
        # yield options.el("div.write", *children, **attrs)

    options.input, options.output = input, output

html_root = html_parent

def html_applicator(schema, options=None, **attrs):
    """render keys in the applicator schema"""
    # the first intervention in the schema and object is use either the
    # schema of object patcher to modify the schema and object before rendering.
    # schema, options = html_patch(schema, options, **attrs)
    # the allof schema is doesn't need to be handled because the schema are aggregated.
    # nopes = list(html_not(schema, options, **attrs))
    # if nopes:
    #     yield from nopes
    # maybe if then doesnt have. visual represntation
    # an else representation means not then
    # yield from html_if_then(schema, options, **attrs)
    # every schema can be represented as a one of schema so we use
    # that applicator generally for diving deeper into a schema representation
    yield from html_one_of(schema, options, **attrs)

def html_one_of(schema, options=None, **attrs):
    one_of = schema.get("oneOf", [schema])
    ol = options.el("ol.oneof")
    errors = dict()
    if one_of is Schema.Expanded:
        one_of = [schema]
    for i, subschema in enumerate(one_of):
        item = options.el("li")
        try:
            options.el(item, html_validation(subschema.reflect(Schema(subschema, schema)), options, **attrs))   
        except Schema.ValidationErrors as e:
            errors[i] = e, subschema
            options.el(item, html_validation(subschema.reflect(Schema(subschema, schema, default=Schema.Expanded)), options, **attrs))
        options.el(ol, item)

    if errors:
        if len(errors) == 1:
            for one_of_index, (error, subschema) in errors.items():
                item = options.el("li")
                default = Schema.default(subschema)
                nope = schema.reflect(~Schema(default=default, title="invalid"))
                options.el(item, html_not(nope, options))
                ol.insert(one_of_index, item)
            errors_schema = Schema(default=[
                dict(message=str(e.message), type=type(e).__name__) for e in error.exceptions
            ], parent=dict(role="group", title="errors"))
            yield from html_root(errors_schema, options)
    i = 0

    for i, child in enumerate(ol.children, 1):
        if i > 1:
            break

    if i == 1:
        yield from child.children
    else:
        yield ol

def html_not(schema, options=None, **attrs):
    nope = schema.get("not")
    if nope:
        yield from html_role(nope, options, **attrs)

def html_errors(schema, options=None, **attrs):
    try:
        Schema.validate(schema)
    except Schema.ValidationErrors as e:
        print(e)

def html_validation(schema, options=None, **attrs):
    t = Schema.type(schema)
    if ("object" not in t) and ("array" not in t):
        # print(33, t)
        Schema.validate(schema)
    yield from html_format(schema, options, **attrs)

def html_format(schema, options=None, **attrs):
    format = schema.get("format")
    if format:
        callable = options.format_mapping.get(format)
        if callable is not None:
            yield from callable(schema, options, **attrs)
        return
    yield from html_role(schema, options, **attrs)

def html_role(schema, options=None, *children, **attrs):
    # content is more specific than role
    # explicit = list(html_content(schema, options, **attrs))
    # if explicit:
    #     yield from explicit
    #     return
    role = Schema.role(schema)
    if role:
        callable = options.role_mapping.get(role)
        if callable is not None:
            yield from callable(schema, options, *children, **attrs)
        return


def html_content(schema, options=None, **attrs):
    subschema = schema.get("contentSchema", Schema())
    value = Schema.default(schema)
    subschema = schema.reflect(Schema(subschema, default=value, readonly=True), "contentSchema")
    
    type = Schema.type(subschema)
    is_container = type in {"object", "array"}
    default_type = None if is_container else "text/plain"
    content = schema.get("contentMediaType", default_type)

    callable = options.content_mapping.get(content)
    
    # this is a note about the contentSchema that cant be used to expand the content of the schema.
    # we should use that.
    
    if callable is not None:
        yield from callable(subschema, options, **attrs)
    # elif content is None and t in {"object", "array"}:
    #     yield from html_root(subschema, options, **attrs)
    

def html_link(schema, options=None, *children, **attrs):
    if not children:
        children = html_title(schema, options)
    yield options.el("a", *children, **attrs)

def html_object(schema, options=None, **attrs):
    ul = options.el("ul.items.object", klass=[schema.path[-1]])
    for key in Schema.property_order(schema):
        subschema = Schema.property(schema, key)
        # print(subschema.path, Schema(subschema, default=Schema.Expanded))
        id = ""
        default = subschema.get("default")
        if default is not None:
            id = subschema.get("default").id()
        item = options.el("li.item", klass=key)
        options.el(item, html_link(subschema, options, href="#" + id, id=id, klass="anchor"))
        options.el(item, html_root(subschema, options, **attrs))
        options.el(ul, item)
    # print(1, str(ul)[:1000])
    # assert False
    yield ul

def html_list(schema, options, **attrs):
    object = Schema.default(schema)
    ol = options.el("ol.items.array", klass=[schema.path[-1]])
    for i in range(len(object)):
        subschema = Schema.property(schema, i)
        item = options.el("li.item", aria=dict(posinset=i+1, setsize=len(object)))
        id = ""
        default = Schema.default(subschema)
        if default is not None:
            id = default.id()
        options.el(item, html_link(subschema, options, href="#" + id, id=id, klass="anchor"))
        options.el(item, html_root(subschema, options, **attrs))
        options.el(ol, item)
    yield ol

def html_select(schema, options, **attrs):
    attrs = html_attrs(schema, options, **attrs)
    enum = schema.get("enum", [])
    default = schema.get("default", enum[0] if enum else None)
    select = options.el("select", id=schema.id("default"), **attrs)
    for i, value in enumerate(enum):
        option = options.el("option", value, value=value, **attrs)
        if value == default:
            option.attrs["selected"] = ""
        options.el(select, option)
    yield from  html_label(schema, options, **attrs)
    yield select

def html_image(schema, options, **attrs):
    object = schema.get("default")
    if object is not None:
        if "://" in object:
            pass#TODO
        else:
            content = schema.get("contentMediaType")
            src = f"data:{content};base64,{object}"
            yield options.el("img", src=src, **attrs)


def html_title(schema, options, **attrs):
    object = Schema.default(schema)
    yield options.el("span.title", schema.get("title", ""), **attrs)
    if object is not None:
        key = object.path[-1]
        if isinstance(key, int):
            key = str(key + 1)
        yield options.el("span.key", key, **attrs)

def html_label(schema, options, **attrs):
    object = Schema.default(schema)
    attrs["for"] = object.id()
    yield options.el("label", html_title(schema, options), **attrs)

def html_attrs(schema, options, **attrs):
    if options.output and not options.input:
        role = Schema.role(schema)
        key = "readonly"

        if role in {"select"}:
            key = "disabled"
        attrs[key] = ""
    
    return attrs

def html_number(schema, options, **attrs):
    if options.disabled:
        yield from html_plain(schema, options, **attrs)
        return
    attrs = html_attrs(schema, options, **attrs)
    attrs["value"] = object = Schema.default(schema)
    attrs["id"] = object.id()
    input = options.el("input", type="number", **attrs)
    yield from  html_label(schema, options, **attrs)
    yield input

def html_textbox(schema, options, **attrs):
    if options.disabled:
        yield from html_plain(schema, options, **attrs)
        return
    if schema.get("aria", {}).get("multiline"):
        yield from html_textarea(schema, options, **attrs)
        return
    attrs = html_attrs(schema, options, **attrs)
    attrs["value"] = object = "".join(Schema.default(schema))
    attrs["id"] = schema.id("default")
    input = options.el("input", type="text", **attrs)
    yield from  html_label(schema, options)
    yield input

def unified_string(object):
    if  isinstance(object, (list, tuple)):
        object = list(map(unified_string, object))
    elif isinstance(object, (int, float, bool, type(None))):
        object = str(object)
    return Schema.String("".join(object))

def html_textarea(schema, options, **attrs):
    attrs = html_attrs(schema, options, **attrs)
    object = unified_string(Schema.default(schema))
    attrs["id"] = schema.id("default")
    attrs["rows"] = object.count("\n") + 1
    textarea = options.el("textarea", object, **attrs)
    yield from  html_label(schema, options)
    yield textarea

def html_checkbox(schema, options, **attrs):
    attrs = html_attrs(schema, options, **attrs)
    object = unified_string(Schema.default(schema))
    attrs["id"] = schema.id("default")
    if schema.get("default"):
        attrs["checked"] = ""
    input = options.el("input", type="checkbox", **attrs)
    yield input
    yield from  html_label(schema, options)

def html_raw(schema, options, **attrs):
    object = unified_string(Schema.default(schema))
    yield from parse_html(object)


def html_markdown(schema, options, **attrs):
    from markdown_it import MarkdownIt
    md = MarkdownIt()
    object = Schema.default(schema)
    yield from parse_html(md.render("".join(object)))
    # handle attachments
    # # cell = (outputs:= (data:= object.parent).parent.parent).parent
    # attachments = cell.get("attachments", {})
    # for document in parse_html(html):
    #     if hasattr(document, "select"):
    #         for a in document.select("img"):
    #             if a.attrs.get("src", "").startswith("attachment:"):
    #                 attachment = a.attrs["src"].partition("attachment:")[2]
    #                 if attachment in attachments:
    #                     for mimetype, data in attachments[attachment].items():
    #                         datauri = f"data:{mimetype};base64,{data}"
    #                         a.attrs["src"] = datauri
        # yield document

def html_paragraph(schema, options, **attrs):
    object = Schema.default(schema)
    unified = unified_string(object)

    yield from options.el("p", unified, **attrs)

def html_dialog_expanded(schema, options, *children, tag="section", **attrs):
    children += options.el("button.expand", "expand"),
    # need ids to set what is expanded 
    yield from html_landmark(schema, options, *children, tag=tag, aria={"expanded": "true"}, **attrs)

def html_dialog(schema, options, *children, **attrs):
    if schema.get("aria", {}).get("expanded"):
        yield from html_dialog_expanded(schema, options, *children, **attrs)
    else:
        yield from html_landmark(schema, options, *children, tag="dialog", **attrs)
        yield options.el("button", html_title(schema, options))

def html_details(schema, options, *children, **attrs):
    summary = options.el("summary", html_title(schema, options))
    if schema.get('aria', {}).get("expanded", True):
        attrs["open"] = ""
    yield options.el("details", summary, *children, **attrs)

def html_description(schema, options, **attrs):
    yield from ()

def html_controls(schema, options, **attrs):
    yield from ()

def html_owns(schema, options, **attrs):
    yield from ()

def html_disabled(schema, options, **attrs):
    yield from ()

def html_errors(schema, options, **attrs):
    yield from ()

def html_plain(schema, options, **attrs):
    yield unified_string(Schema.default(schema))

widget_role_mappings = dict()
structure_role_mappings = dict()
window_role_mappings = dict()

role_mappings = collections.ChainMap(widget_role_mappings, structure_role_mappings, window_role_mappings)


role_mapping = dict(
    associationlist=html_object,
    banner=partial(html_landmark, tag="header"),
    button=html_plain,
    checkbox=html_plain,
    code=html_plain,
    complementary=partial(html_landmark, tag="aside"),
    contentinfo=partial(html_landmark, tag="footer"),
    dialog=html_dialog,
    form=html_plain,
    group=html_details,
    heading=html_plain,
    img=html_plain,
    input=html_plain,
    link=html_plain,
    list=html_list,
    main=partial(html_landmark, tag="main"),
    navigation=partial(html_landmark, tag="nav"),
    paragraph=html_paragraph,
    region=partial(html_landmark, tag="section"),
    select=html_select,
    spinbutton=html_number,
    table=html_plain,
    textbox=html_textbox,
) | {None: html_plain}

section_role_mapping = {}
structure_role_mapping = {}
widget_role_mapping = role_mapping
format_mapping = {
    "datetime": html_plain,
    "json-pointer": html_plain,
}

def html_nb(schema, options, **attrs):
    """render a notebook as html"""
    from .nb import html_nb
    yield from html_nb(schema, options, **attrs)

content_mapping = {
    "text/html": html_raw,
    "text/markdown": html_markdown,
    "image/png": html_image,
    "image/jpeg": html_image,
    "image/bmp": html_image,
    "image/svg+xml": html_plain,
    "text/plain": html_paragraph,
    "text/uri-list": html_plain,
    "application/x-ipynb+json": html_plain,
}

@dataclass
class Options:
    role_mapping: dict = field(default_factory=role_mapping.copy)
    format_mapping: dict = field(default_factory=format_mapping.copy)
    content_mapping: dict = field(default_factory=content_mapping.copy)
    schema_patch: dict = field(default_factory=dict)
    object_patch: dict = field(default_factory=dict)
    disabled: bool = False
    validate: bool = True
    input: bool = True
    output: bool = True
    from .utils import el
    el = staticmethod(el)

# handle units

Schema.Options = Options