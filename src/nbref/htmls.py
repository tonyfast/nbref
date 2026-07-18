
from cProfile import label
from contextlib import contextmanager
from dataclasses import dataclass, field
from functools import partial

from nbref.templates.sf import Dict, Null

from .schemas import Schema
from .utils import el, parse_html

# the renderers use iterators to yield the elements
# and the renderer function coalesces the elements into a single element.
def html_render(schema, object, options=None, *children, **attrs):
    """render an schema and object as html"""
    
    # initialize the options if they were not provided.
    if options is None:
        options = Options()
    # make the element concrete
    result = list(
        html_applicator(schema, object, options, **attrs)
    ) + list(children)
    if len(result) == 1:
        # return a single element if there is only one child
        return result[0]
    # coalesce all the elements
    return el("div", *result, **attrs)

def html_applicator(schema, object, options, **attrs):
    """render keys in the applicator schema"""
    # the first intervention in the schema and object is use either the
    # schema of object patcher to modify the schema and object before rendering.
    schema, object, options = html_patch(schema, object, options, **attrs)
    # the allof schema is doesn't need to be handled because the schema are aggregated.
    nopes = list(html_not(schema, object, options, **attrs))
    if nopes:
        yield from nopes
        return
    # every schema can be represented as a one of schema so we use
    # that applicator generally for diving deeper into a schema representation
    yield from html_one_of(schema, object, options, **attrs)

def html_patch(schema, object, options, **attrs):
    """allows for modifying schema, object, and options in a scope."""
    for mapping, relative in [(options.schema_patch, schema.path), (options.object_patch, object.path)]:
        patch = mapping.get(tuple(relative))
        if patch:
            patched = patch(schema, object, options, **attrs)
            if patched is not None:
                if len(patched) == 1:
                    schema = patched[0]
                elif len(patched) == 2:
                    schema, object = patched
                elif len(patched) == 3:
                    schema, object, options = patched
                object.schema = schema
    return schema, object, options

def html_repr(schema, object, options, **attrs):
    yield from ()

def html_format_role_content(schema, object, options, **attrs):
    """handle the representation of the role, format, or content schema."""
    # process the format, then the content media type, and then the role.
    # this order was chosen because the format is the most flexible as it describes the
    # the content media type is specific to the type space.
    # the role is slowest to change and is codified in the WAI specifications.
    # we want a generic function that can call entry points
    repr = list(html_repr(schema, object, options, **attrs))
    if repr:
        yield from repr
        return
    format = list(html_format(schema, object, options, **attrs))
    if format:
        yield from format
        return
    content = list(html_content(schema, object, options, **attrs))
    if content:
        yield from content
        return
    # note: this is not the inferred role, that is handled in another role.
    role = schema.get("role")
    if role:
        # the next line will naturally raise when the explicit role can't be processed.
        callable = options.role_mapping[role]
        yield from callable(schema, object, options, **attrs)
        return

def html_if_then(schema, object, options, **attrs):
    pass


def html_one_of(schema, object, options, **attrs):
    """handle the one of and not schema representations"""

    # return the results for explicit role, format, or content schema.
    # this pass does not use the inferred role.
    explicit = list(html_format_role_content(schema, object, options, **attrs))
    if explicit:
        yield from html_parent(schema, object, options, *explicit)
        return

    one_of = schema.get("oneOf", [schema])

    # what role making the most sense for a oneOf schema?
    only_one = len(one_of) == 1
    ol = el("ol.oneof", klass=[object.type()], role="group")

    is_valid = []
    for subschema in one_of:
        # subschema = Schema.expand(subschema)
        t = Schema.type(subschema)
        # i make the mistake of not using this form a lot.
        # calling subschema.type() doesnt give the expected outcomes.
        # print(object.path, t)
        # print(t, subschema.path, object.path)
        value = object
        if t in ["string", "number", "integer", "boolean", "null"]:
            is_valid.append(Schema.is_valid(subschema, value))
            if not is_valid[-1]:
                value = Schema.default(subschema).set_path(object.path).set_root(object.root)
        else:
            valid = Schema.is_valid(Schema(type=t), object)

            is_valid.append(valid)
            # is_valid.append(True)
        classes = html_classes(subschema, value, options, **attrs)
        item = el("li.oneof", klass=classes)
        # wheres the radio label? 
        radio = el(
            "input.radio", type="radio", name=object.id("oneof"), value=str(subschema.path[-1]), 
            aria=html_aria_labelledby(subschema, value, options, **attrs)
            | dict(owns=object.id())
        )
        # print(is_valid[-1], subschema.path, object.path, value)
        if is_valid[-1]:
            radio.attrs["checked"] = ""
        el(item, radio)
        # subschema = subschema.reflect(Schema(subschema)).append(title=F"{subschema.type()}")
        iterator = only_one and html_validator or html_applicator
        children = list(iterator(subschema, value, options, **attrs))
        el(item, *children)
        el(ol, item)

    if only_one:
        # when a schema of one is valid return just the children
        if all(is_valid):
            # this drops the radio button
            children = (x for i, x in enumerate(ol.li.children) if i)
            yield from html_parent(schema, object, options, *children, **attrs)
            return
        
    if is_valid and not(any(is_valid)):
        # add the negative schema and value to the list of children
        invalid = el("li.invalid.not", klass=[object.type(), object.path[-1]])
        # generate a synthetic not schema
        negative_schema = ~Schema(Schema.infer(object), title=object.title(), tags=["not"])
        value = object.copy()
        value.schema = negative_schema
        radio = el(
            "input.radio", type="radio", name=object.id("oneof"), value=str(negative_schema.path[-1]), 
            checked="", aria=html_aria_labelledby(subschema, object, options, **attrs)
        )
        el(invalid, radio, html_not(negative_schema, value, options, **attrs))
        ol.insert(0, invalid)
    
    yield from html_parent(schema, object, options, ol, **attrs)

def html_not(schema, object, options, **attrs):
    """create a representation of the not schema"""
    nope = schema.get("not")
    if nope:
        nope = nope.reflect(Schema(nope, tags=["not"]))
        value = object.copy()
        value.schema = nope
        yield from html_validator(nope, value, options, **attrs)

def html_parent(schema, object, options, *children, **attrs):
    parent = schema.get("parent")
    if parent:
        role = Schema.role(parent)
        yield from options.role_mapping.get(role)(parent, object, options, *children)
        return
    yield from children

def html_validator(schema, object, options, **attrs):
    # create a representation based on the role the schema refers to.
    explicit = list(html_format_role_content(schema, object, options, **attrs))
    if explicit:
        yield from html_parent(schema, object, options, *explicit)
    else:
        yield from html_role(schema, object, options, **attrs)
    yield from html_dependent_schemas(schema, object, options, **attrs)

def html_dependent_schemas(schema, object, options, **attrs):
    # for units to work efficiently in dependent schemas we should
    # use aria-owns off the parent input. this way the parent input 
    # can concatenate all the values.

    # dependentRequired should be implemented near here possibly using something
    # similar to the Schema.column pattern because that doesnt create defaults.
    dependent_schemas = schema.get("dependentSchemas", {})
    # yield from ()
    for key, subschema in dependent_schemas.items():
        # the dependent schema values probably wont actually be in the object,
        # so we should recover them fromt he settings but for the meantime we'll use defaults.
        # since the valid isn't guarenteed we need to manually expand the schema.
        value = Schema.default(Schema.expand(subschema)).set_path(object.path + [key]).set_root(object.root)
        yield from html_applicator(subschema, value, options, **attrs)

def html_role(schema, object, options, **attrs):
    # infer the implicit or explicit role of the schema.
    role = Schema.role(schema, options, object)
    # print(role, schema.path, object.path)
    callable = options.role_mapping[role]
    # print(callable, list(callable(schema, object, options, **attrs)))
    yield from callable(schema, object, options, **attrs)

def html_object(schema, object, options, **attrs):
    klass = html_classes(schema, object, options, **attrs)
    ul = el("ul.object", klass=klass)
    columns = Schema.columns(schema, object)
    for subschema, value in columns:
        klass = html_classes(subschema, value, options, **attrs)
        item = el("li", klass=klass)
        anchor = el("a.anchor", value.title(), id=object.id("anchor"), href="#" + object.id("anchor"), klass=klass)
        el(item, anchor, *html_applicator(subschema, value, options))
        el(ul, item)
        
    yield ul


def html_array(schema, object, options, **attrs):
    klass=html_classes(schema, object, options, **attrs)
    ol = el("ol.array")
    for index in range(len(object)):
        value = object[index]
        # print(value.path, value)
        subschema = value.schema
        k = html_classes(subschema, value, options, **attrs)
        # add data attributes for the numeric values in the object
        for s, o in Schema.columns(subschema, value):
            t = s.get("@type", "")
            if "rdfs:label" in t:
                k.append(o)
            if Schema.type(s) in ["number", "integer", "boolean"]:
                attrs.setdefault("data", {}).update({s.path[-1]: o})
                attrs.setdefault("style", {}).update({f"--{s.path[-1]}": o})
        item = el("li", klass=k, aria=dict(posinset=index + 1, setsize=len(object)))
        anchor = el("a.anchor", str(index+1), id=object.id("anchor"), href="#" + object.id("anchor"), klass=k)
        el(item, anchor, *html_applicator(subschema, value, options, **attrs))
        # add role to item class
        el(ol, item)
    el(ol, klass=klass, **attrs)
    # the group role adds label, description, details for the list.
    if "parent" not in schema:
        yield from html_parent(dict(parent=dict(role="group")), object, options, ol)
    else:
        yield ol

def html_details(schema, object, options, *children, **attrs):
    classes = html_classes(schema, object, options, **attrs)    
    details = el("details", klass=classes, open="")
    attrs = html_attrs(schema, object, options, **attrs)
    attrs["id"] = object.id("title")
    yield el(
        details, el("summary.label", *html_title(schema, object, options, **attrs), klass=classes), 
        *html_description(schema, object, options),
        *children, *html_comments(schema, object, options),
        **attrs
    )

def html_fieldset(schema, object, options, *children, **attrs):
    fieldset = el("fieldset", klass=[object.type()])
    attrs = html_attrs(schema, object, options, **attrs)
    yield el(
        fieldset, el("legend", str(object.title())), 
        *html_description(schema, object, options),
        *children, *html_comments(schema, object, options),
        **attrs
    )

def html_label(schema, object, options, **attrs):
    attrs["for"] = object.id()
    attrs["id"] = object.id("label")
    label = el("label.label", **attrs)
    el(label, *html_title(schema, object, options, **attrs), **attrs)
    yield label

def html_title(schema, object, options, **attrs):
    title = object.title()
    tags = schema.get("tags", [])
    type = object.type()
    
    if "not" in tags:
        yield el("span.invalid", "invalid")
    yield el("span.title", title, id=object.id("title"), klass=[type])
    yield el("span.type", type, klass=[type])
    
def html_description(schema, object, options, **attrs):
    """a description from the schema of the object"""
    description = schema.get("description")
    if description:
        attrs["id"] = object.id("desc")
        yield from options.role_mapping["paragraph"](schema, description, options, **attrs)

def html_comments(schema, object, options, **attrs):
    """comments from the object"""
    comments = schema.get("comments", [])
    if comments:
        attrs["id"] = object.id("comments")
        yield from options.role_mapping["group"](schema, object, options, *[el("p", comment) for comment in comments], **attrs)

def html_input(schema, object, options, **attrs):
    format = list(html_format(schema, object, options, **attrs))
    if format:
        yield from format
        return
    
    type = object.type()

    if type == "string":
        yield from html_string(schema, object, options, **attrs)
    elif type == "boolean":
        yield from html_checkbox(schema, object, options, **attrs)
    elif type in ["number", "integer"]:
        yield from html_input_number(schema, object, options, **attrs)
    elif type == "null":
        yield from html_paragraph(schema, object, options, **attrs)

def html_input_number(schema, object, options, **attrs):
    attrs = html_attrs(schema, object, options, **attrs)
    attrs.update(html_aria_labelledby(schema, object, options, **attrs))
    if "parent" not in schema:
        yield from html_label(schema, object, options, **attrs)
    yield el("input.number", type="number", value=str(object), **attrs)
    # dependent_schemas = schema.get("dependentSchemas", {})
    # for key, subschema in dependent_schemas.items():
    #     yield from html_validator(subschema, object, options, **attrs)

def html_string(schema, object, options, **attrs):
    if schema.get("aria", {}).get("multiline"):
        # remove the multiline attribute
        yield from html_textarea(schema, object, options, **attrs)
        return
    attrs = html_attrs(schema, object, options, **attrs)
    attrs.update(html_aria_labelledby(schema, object, options, **attrs))
    if "parent" not in schema:
        yield from html_label(schema, object, options, **attrs)
    yield el("input.string", type="text", value=str(object), **attrs)

def html_textarea(schema, object, options, **attrs):
    attrs = html_attrs(schema, object, options, **attrs)
    attrs.update(html_aria_labelledby(schema, object, options, **attrs))
    body = "".join(object)
    attrs["rows"] = body.count("\n") + 1
    if "parent" not in schema:
        yield from html_label(schema, object, options, **attrs)
    yield el("textarea.string", body , **attrs)

def html_checkbox(schema, object, options, **attrs):
    attrs = html_attrs(schema, object, options, **attrs)
    attrs.update(html_aria_labelledby(schema, object, options, **attrs))
    attrs["type"] = "checkbox"
    if object:
        attrs["checked"] = ""
    yield el("input.boolean", **attrs)
    yield from html_label(schema, object, options, **attrs)

def html_paragraph(schema, object, options, *children, **attrs):
    yield el("p", str(object), *children, **attrs)


# html attributes
def html_aria_labelledby(schema, object, options, **attrs):
    """return the id of the label for the object"""
    aria = {
    }
    if not schema.get("aria", True):
        return aria
    aria["aria-labelledby"] = object.id("title")
    description = object.description()
    if description:
        aria["aria-describedby"] = object.id("desc")
    return aria


def html_classes(schema, object, options, **attrs):
    classes = []
    classes += attrs.get("class", [])
    classes += attrs.get("klass", [])
    classes += schema.get("attrs", {}).get("class", [])
    classes += schema.get("tags", [])
    if len(object.path) == 1:
        if object.name:
            classes += [object.name]
    else:
        classes += [object.path[-1]]
    classes += [object.type(), object.title()]
    if isinstance(object, dict):
        pass # look for key, values with tag references
    output = []
    for s, o in Schema.columns(schema, object):
        t = s.get("@type", "")
        if "rdfs:label" in t:
            classes.append(o)
        if "@id" in t:
            classes.append(o)
    for klass in classes:
        if isinstance(klass, str):
            klass = "".join(
                c if c.isalnum() or c in ["-", "_"] else "_" for c in klass
            )
            if klass not in output:
                output.append(klass)
    return output

def html_attrs(schema, object, options=None, itemscope=False, **attrs):
    """convert a schema into html attributes for the object"""
    if itemscope:
        attrs.setdefault("item", {}).update(
            prop=object.path[-1]
        )
        if object.type() in ["object", "array"]:
            attrs["item"]["scope"] = ""
    if "attrs" in schema:
        attrs.update(schema["attrs"])
    if "on" in schema:
        for event, handler in schema["on"].items():
            attrs[f"on{event}"] = handler
    if "aria" in schema:
        aria = schema["aria"]
        if aria:
            for attribute, value in schema["aria"].items():
                if attribute not in {"expanded"}:
                    attrs[f"aria-{attribute}"] = value
    if "data" in schema:
        for attribute, value in schema["data"].items():
            attrs[f"data-{attribute}"] = value
    if "item" in schema:
        for attribute, value in schema["item"].items():
            attrs[f"item{attribute}"] = value
    if "style" in schema:
        attrs["style"] = "; ".join(f"{k}: {v}" for k, v in schema["style"].items())
    # if "role" in schema:
    #     attrs["role"] = schema["role"]
    # if is_readonly(schema):
    #     attrs["readonly"] = ""

    classes = html_classes(schema, object, options, **attrs)
    if classes:
        attrs["class"] = classes
    return attrs
    
landmark_tags = dict(
    main="main",
    form="form",
    region="section",
    complementary="aside",
    banner="header",
    contentinfo="footer",
)

def html_region(schema, object, options, *children, tag=None, **attrs):
    role = schema.get("role", "region")
    tag = tag or "section"
    attrs = html_attrs(schema, object, options, **attrs)
    if tag in {"section"}:
        attrs["role"] = role
    attrs.update(html_aria_labelledby(schema, object, options, **attrs))
    yield el(tag, *children, **attrs)

def html_form(schema, object, options, *children, **attrs):
    attrs = html_attrs(schema, object, options, **attrs)
    yield el("form", *children, **attrs)

def html_dialog(schema, object, options, *children, **attrs):
    if schema.get("aria", {}).get("expanded"):
        yield from html_dialog_block(schema, object, options, *children, **attrs)
        return
    attrs = html_attrs(schema, object, options, **attrs)
    yield from options.role_mapping["button"](schema, object, options, **attrs)
    yield el("dialog", *children, **attrs)

def html_dialog_block(schema, object, options, *children, **attrs):
    """a section that can be opened as a dialog to trim that accessibility tree."""
    attrs = html_attrs(schema, object, options, **attrs)
    section = el("section.dialog", *children, **attrs)
    button = options.role_mapping["button"](schema, object, options, **attrs)
    el(section, button)
    yield section


def html_script(schema, object, options, **attrs):
    attrs = html_attrs(schema, object, options, **attrs)
    attrs.setdefault("style", "display: block;")
    attrs["type"] = schema.get("contentMediaType", "text/plain")
    yield from html_details(
        schema, object, options, el("script", str(object), **attrs), **attrs
    )

def html_raw(schema, object, options, **attrs):
    yield from options.role_mapping["group"](schema, object, options, *parse_html("".join(object)), **attrs)

def html_markdown(schema, object, options, **attrs):
    from markdown_it import MarkdownIt
    md = MarkdownIt()
    html = md.render("".join(object))
    # handle attachments
    cell = (outputs:= (data:= object.parent).parent.parent).parent
    attachments = cell.get("attachments", {})
    for document in parse_html(html):
        if hasattr(document, "select"):
            for a in document.select("img"):
                if a.attrs.get("src", "").startswith("attachment:"):
                    attachment = a.attrs["src"].partition("attachment:")[2]
                    if attachment in attachments:
                        for mimetype, data in attachments[attachment].items():
                            datauri = f"data:{mimetype};base64,{data}"
                            a.attrs["src"] = datauri
        yield document

def html_button(schema, object, options, **attrs):
    attrs = html_attrs(schema, object, options, **attrs)
    if isinstance(object, (dict, list)):
        text = object.title()
    else:
        text = object

    yield el("button", str(text), **attrs)

def html_link(schema, object, options, *children, **attrs):
    attrs = html_attrs(schema, object, options, **attrs)
    yield el("a", str(object), *children, **attrs)

def html_table(schema, object, options, **attrs):
    table = el("table", el("thead"), el("tbody"), **attrs)
    # create a prefixItems schema that is more practical
    
def html_datetime(schema, object, options, **attrs):
    attrs = html_attrs(schema, object, options, **attrs)
    attrs.update(html_aria_labelledby(schema, object, options, **attrs))    
    attrs["type"] = "datetime-local"
    yield el("input.datetime", value=str(object), **attrs)

def html_content(schema, object, options, **attrs):
    content = schema.get("contentMediaType")
    if content in options.content_mapping:
        yield from options.content_mapping[content](schema, object, options, **attrs)

def html_format(schema, object, options, **attrs):
    format = schema.get("format")
    if format in options.format_mapping:
        yield from options.format_mapping[format](schema, object, options, **attrs)

def html_image(schema, object, options, **attrs):
    attrs = html_attrs(schema, object, options, **attrs)
    if object:
    # we dont have to deal with attachments here.
        datauri = "data:"
        mimetype = schema.get("contentMediaType", "image/png")
        datauri += mimetype + ";"
        datauri += ["base64,", "utf-8,"]["svg"  in mimetype]
        datauri += str(object)
        attrs["src"] = datauri
    yield el("img", **attrs)

def html_select(schema, object, options, **attrs):
    attrs = html_attrs(schema, object, options, **attrs)
    attrs.update(html_aria_labelledby(schema, object, options, **attrs))
    if "parent" not in schema:
        yield from html_label(schema, object, options, **attrs)
    select = el("select", **attrs)
    for option in schema.get("enum", []):
        option_attrs = html_attrs(schema, object, options, **attrs)
        option_attrs["value"] = str(option)
        if object == option:
            option_attrs["selected"] = ""
        el(select, el("option", str(option), **option_attrs))
    yield select


def html_load(schema, object, options, **attrs):
    ol = el("ol.load", klass=[object.type()])
    for uri in filter(str.strip, object.splitlines()):
        # there is a loader with ref that we can use already
        attrs = dict(itemid=uri)
        # should guess the mimetye from the file extension
        # and supply that as contentMediaType
        if uri.startswith("file://"):
            uri = uri.partition("file://")[2]
            object = Schema.Object.from_file(uri)
            if uri.endswith(".ipynb"):
                object.schema = Schema(contentMediaType="application/x-ipynb+json")
        else:
            continue
        item = el("li.load", **attrs)
        el(ol, el(item, *html_applicator(object.schema, object, options, **attrs)))
    yield ol

role_mapping = dict(
    associationlist=html_object,
    banner=partial(html_region, tag="header"),
    button=html_button,
    checkbox=html_checkbox,
    code=html_content,
    complementary=partial(html_region, tag="aside"),
    contentinfo=partial(html_region, tag="footer"),
    dialog=html_dialog,
    form=html_form,
    group=html_details,
    img=html_image,
    input=html_input,
    link=html_link,
    list=html_array,
    main=partial(html_region, tag="main"),
    navigation=partial(html_region, tag="nav"),
    paragraph=html_paragraph,
    region=html_region,
    select=html_select,
    spinbutton=html_input_number,
    table=html_table,
    textbox=html_string,
) | {None: html_paragraph}

format_mapping = {
    "datetime": html_datetime,
}
content_mapping = {
    "text/html": html_raw,
    "text/markdown": html_markdown,
    "image/png": html_image,
    "image/jpeg": html_image,
    "image/bmp": html_image,
    "image/svg+xml": html_image,
    "text/uri-list": html_load,
}

@dataclass
class Options:
    role_mapping: dict = field(default_factory=role_mapping.copy)
    format_mapping: dict = field(default_factory=format_mapping.copy)
    content_mapping: dict = field(default_factory=content_mapping.copy)
    schema_patch: dict = field(default_factory=dict)
    object_patch: dict = field(default_factory=dict)

# handle units

Schema.Options = Options