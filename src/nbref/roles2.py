


from dataclasses import dataclass, field

from nbref.schemas import Schema
from nbref.objects import Null
from nbref import html, schema

from .utils import el, parse_html
@dataclass
class Options:
    readonly: list = field(default_factory=list)
    labels: dict = field(default_factory=dict)
    is_valid: list = field(default_factory=list)

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
    if "role" in schema:
        attrs["role"] = schema["role"]
    if is_readonly(schema):
        attrs["readonly"] = ""

    attrs.setdefault("class", []).extend([str(object.path[-1]), object.type()])
    return attrs

def render_schema(schema, object, options=None, **attrs):
    if options is None:
        options = Options()
    html = list(html_schema(schema, object, options, **attrs))
    if len(html) == 1:
        return html[0]
    return el("div", html, **attrs)

def html_schema(schema, object, options, **attrs):
    """the primary function for yielding html encoding of a schema and object."""
    # ensure that there is a schema to track
    if not schema:
        schema = object.infer_schema().schema
    # begin entering the representation with "oneOf" and "not" expressions
    yield from html_one_of(schema, object, options, **attrs)

def html_roles(schema, object, options, *children, **attrs):
    role = schema.get("role")
    if not role:
        role = Schema.role_widget(schema) or Schema.role_section(schema)
    yield from role_mapping[role](schema, object, options)
    # if outer_role:
    #     html = role_mapping[outer_role](schema, object, options, html)

def html_null(schema, object, options, *children, **attrs):
    yield el("span.null", str(object), **attrs)
    


# def aria_landmark_role(schema):
#     """determine the aria role for schema with the landmark abstract role as a base class"""

#     t = Schema.type(schema)
#     if "object" in t:
#         return "dialog"
#     elif "array" in t:
#         return "dialog"

def aria_widget_role(schema):
    """determine the aria role for schema with the widget abstract role as a base class"""

    enum = schema.get("enum")
    if enum:
        return "listbox"
        
    t = Schema.type(schema)
    if "string" in t:
        return "textbox"
    elif "number" in t:
        return  "spinbutton"
    elif "integer" in t:
        return  "spinbutton"
    elif "boolean" in t:
        return "checkbox"

    format = schema.get("format")
    if format:
        return "input"
        

def aria_section_role(schema):
    """determine the aria role for schema with the section abstract role as a base class"""
    content = schema.get("contentMediaType")
    if content and content != "text/plain":
        return "code"
    t = schema.type()
    if "object" in t:
        return "list"
    elif "array" in t:
        return "list"
    
def html_aside(schema, object, options, *children, **attrs):
    yield el("aside", *children, **attrs)

def html_banner(schema, object, options, *children, **attrs):
    yield el("header", *children)


def html_button(schema, object, options, *children, **attrs):
    yield el("button", *children, **attrs)

def html_cell(schema, object, options, *children, **attrs):
    if is_index(schema):
        yield from role_mapping["rowheader"](schema, object, options, *children, **attrs)
    else:
        yield el("td", html_schema(schema, object, options, *children, **attrs), **attrs)


def html_checkbox(schema, object, options, *children, **attrs): 
    yield html_label(schema, object, options, *children, **attrs)
    attrs["id"] = object.id()
    attrs["checked"] = bool(object)
    yield el("input.checkbox", type="checkbox", **attrs)

def html_code(schema, object, options, *children, **attrs):
    content_type = schema.get("contentMediaType")
    yield from content_mapping[content_type](schema, object, options, *children, **attrs)
def html_columnheader(schema, object, options, *children, **attrs):
    attrs["scope"] = "col"
    yield el("th", object, **attrs)

def html_comments(schema, object, options, *children, **attrs): 
    comments = schema.get("comments")
    if comments:
        yield el("p.comments", comments, **attrs)


def html_contentinfo(schema, object, options, *children, **attrs):
    yield el("footer", *children)


def html_description(schema, object, options, *children, **attrs):
    description = schema.get("description")
    if description:
        attrs["id"] = object.id("desc", suffix=False)
        yield el("p.description", description, **attrs)

    options.labels[tuple(object.path)] = True

def html_details(schema, object, options, *children, **attrs): 
    summary = el("summary", object.title(), id=object.id("title", suffix=False))
    description = html_description(schema, object, options, *children, **attrs)
    comments = html_comments(schema, object, options, *children, **attrs)
    attrs["open"] = True
    options.labels[tuple(object.path)] = True
    yield el("details", summary, description, *children, comments, **attrs)


def html_dialog(schema, object, options, *children, **attrs):
    group = role_mapping["group"](schema, object, options, *children, **attrs)
    yield el("section.dialog", group, **attrs)

def html_figure(schema, object, options, *children, **attrs):
    yield el("figure", *children, **attrs)

def html_form(schema, object, options, *children, **attrs):
    yield el("form", *children, **attrs)

def html_heading(schema, object, options, *children, **attrs):
    level = schema.get("headingLevel", 1)
    if level < 1 or level > 6:
        level = 1
    yield el(f"h{level}", *children, **attrs)

def html_img(schema, object, options, *children, **attrs):
    src = schema.get("src")
    if src:
        yield el("img", *children, src=src, **attrs)
def html_input(schema, object, options, *children, **attrs): 
    format = schema.get("format")
    if format in ["date", "time", "datetime-local"]:
        yield from html_input_datetime(schema, object, options, *children, **attrs)    
def html_input_datetime(schema, object, options, *children, **attrs): pass

def html_list(schema, object, options, *children, **attrs):
    if isinstance(object, dict):
        yield from html_list_object(schema, object, options, *children, **attrs)
    elif isinstance(object, list):
        yield from html_list_array(schema, object, options, *children, **attrs)

def html_list_array(schema, object, options, *children, **attrs):
    ol = el("ol.list", *children, **attrs)
    for item in object:
        # add a link to the index
        li = role_mapping["listitem"](item.schema, item, options, **attrs)
        el(ol, li)
    yield ol

def html_listitem(schema, object, options, *children, **attrs):
    yield el("li", html_schema(schema, object, options, **attrs), **attrs)


def html_list_object(schema, object, options, *children, **attrs):
    ol = el("ul", *children, **attrs)
    for key, item in object.items():
        if item is None:
            item = Null()
        el(ol, role_mapping["listitem"](item.schema, item, options, **attrs))
    yield ol

def html_link(schema, object, options, *children, **attrs):
    href = schema.get("href")
    if href:
        yield el("a.link", *children, href=href, **attrs)
    else:
        yield el("span.link", *children, **attrs)

def html_label(schema, object, options, *children, **attrs):
    # if options.labels.get(tuple(object.path)):
    #     return
    title = object.title()
    attrs["for"] = object.id()
    yield el("label", title, id=object.id("title"), **attrs)

def html_listbox(schema, object, options, *children, **attrs): 
    enum = schema.get("enum")
    if enum:
        yield from html_label(schema, object, options, *children, **attrs)
        yield el(
            "select.enum", (
                el("option", str(e), value=str(e)) for e in enum
            ), id=object.id()
        )

def html_main(schema, object, options, *children, **attrs):
    yield el("main", *children, **attrs)

def html_radiogroup(schema, object, options, *children, **attrs):
    yield html_label(schema, object, options, *children, **attrs)
    yield el("div.radiogroup", role="radiogroup", **attrs)

def is_index(schema):
    if schema.get("@type") == "@index":
        return True
    return False

def html_row(schema, object, options, *children, **attrs):
    tr = el("tr")
    for i, subschema in enumerate(schema.get("prefixItems", [])):
        el(tr, role_mapping["cell"](subschema, Schema.Object.dispatch(object[i]).set_schema(subschema), options, *children, **attrs))
    yield tr

def html_rowgroup(schema, df, options, *children, **attrs):
    tbody = el("tbody")
    subschema = schema.get("items", {})
    for i, row in df.iterrows():
        el(tbody, role_mapping["row"](subschema, list(row), options, *children, **attrs))
    yield tbody
    

def html_rowgroup_object(schema, object, options, *children, **attrs):
    for item in object.values():
        yield from role_mapping["row"](schema, item, options, *children, **attrs)

def html_rowgroup_array(schema, object, options, *children, **attrs):
    for item in object:
        yield from role_mapping["row"](schema, item, options, *children, **attrs)


def html_row_object(schema, object, options, *children, **attrs):
    for key, value in object.items():
        is_index = False
        f = role_mapping[is_index and "rowheader" or "cell"]
        if value is None:
            value = Null()
        yield from f(value.schema, value, options, *children, **attrs)

def html_row_array(schema, object, options, *children, **attrs):
    for value in object:
        is_index = False
        f = role_mapping[is_index and "rowheader" or "cell"]
        if value is None:
            value = Null()
        yield from f(value.schema, value, options, *children, **attrs)

def html_rowheader(schema, object, options, *children, **attrs):
    attrs["scope"] = "row"
    yield el("th", schema.title(), **attrs)

def html_script_text(schema, object, options, *children, **attrs):
    attrs["type"] = schema.get("contentMediaType", "text/plain")
    attrs.setdefault("style", {}).update({"display": "block"})
    if isinstance(object, list):
        if all(x for x in object if isinstance(x, str)):
            object = "\n".join(object)
        
    if not isinstance(object, str):
        object = object.dump() if hasattr(object, "dump") else str(object)
    yield el("script", object, **attrs)

def html_spinbutton(schema, object, options, *children, **attrs): 
    yield html_label(schema, object, options, *children)
    attrs = html_attrs(schema, object, options, **attrs)
    type = schema.type()
    attrs["id"] = object.id()
    if "integer" in type:
        attrs["step"] = "1"
    attrs["value"] = str(object)
    attrs.setdefault("class", []).append("type")
    attrs.setdefault("aria", {}).setdefault("labelledby", object.id("title", suffix=False))
    attrs["aria"].setdefault("describedby", object.id("desc", suffix=False))


    if options.is_valid and not options.is_valid[-1]:
        attrs.setdefault("aria", {}).update(
            invalid="true"
        )
    yield el("input", type="number", **attrs)

def html_table(schema, object, options, *children, **attrs): 
    table = el("table")
    import pandas
    df = pandas.DataFrame(object)
    subschema = schema.get("items")
    required = subschema.required()
    df.index.name = "@index"
    df = df.reset_index()
    df = df[required + [x for x in df.columns if x not in required]]
    table_schema = Schema(items=Schema(prefixItems=[
        subschema.property(column).append(title=column) for column in df.columns
    ]))
    el(table, html_thead(table_schema, df, options, *children, **attrs))
    el(table, role_mapping["rowgroup"](table_schema, df, options, *children, **attrs))
    yield table


def html_textbox(schema, object, options, *children, **attrs): 
    if schema.get("aria", {}).get("multiline"):
        yield from html_textarea(schema, object, options, *children, **attrs)
    else:
        yield html_label(schema, object, options, *children, **attrs)
        yield el("input.textbox", type="text", value=str(object), id=object.id())

def html_textarea(schema, object, options, *children, **attrs):
    yield html_label(schema, object, options, *children)
    attrs = html_attrs(schema, object, options, **attrs)
    lines = "".join(object)
    yield el("textarea.textarea", lines, id=object.id(), rows=lines.count("\n") + 1, **attrs)


def html_thead(schema, object, options, *children, **attrs):
    # object is a pandas dataframe
    thead = el("thead", **attrs)
    subschemas = schema.get("items", {}).get("prefixItems", [])
    for i, subschema in enumerate(subschemas):
        el(thead, role_mapping["columnheader"](subschema, Schema.title(subschema), options, *children, **attrs))
    yield thead




def html_time(schema, object, options, *children, **attrs): pass

def html_one_of(schema, object, options, *children, **attrs):
    """render an object based off the one of expression"""
    # when there is no oneOf wrap return the schema as the only option.
    role = schema.get("role")
    if role:
        yield from html_roles(schema, object, options, *children, **attrs)
        return

    one_of = schema.get("oneOf", [schema])

    # represent the oneOf as a list.
    ul = el("ul.oneof", **attrs)
    valid = False
    options.labels[tuple(object.path)] = True
    for i, subschema in enumerate(one_of):
        value = object
        radio_attrs = {}
        item_attrs = {}
        # valid the object against the schema
        type_schema = subschema
        t = Schema.type(subschema)
        if t in ["array", "object"]:
            type_schema = Schema(type=t)
        # print(t, type(object), Schema.is_valid(type_schema, object))
        if Schema.is_valid(type_schema, object.builtin()):
            radio_attrs.update({"checked": ""})
            if not valid:
                valid = True
            item_attrs.setdefault("aria", {}).update({"current": "true"})
        else:
            value = object.reflect(Schema.default(subschema))
        
        if len(one_of) > 1:
            value.set_suffix(i)
            
        radio = el("input.oneof", type="radio", name=object.id(), value=Schema.title(subschema), **radio_attrs)
        el(ul, el("li.oneof", radio, html_roles(subschema, value, options)), **item_attrs)
    
    if not valid:
        subschema = object.infer_schema().schema
        radio_attrs = {"checked": ""}
        radio = el("input", type="radio", name=object.id(), value=Schema.title(subschema), **radio_attrs)
        prior = object.schema
        options.is_valid.append(False)
        object.schema = subschema = Schema(subschema, title="invalid" + object.title())
        ul.insert(0, el("li.not.oneof", radio, html_roles(subschema, object.set_suffix("not"), options, **attrs), aria=dict(current="true")))
        options.is_valid.pop()
        object.schema = prior
    details = html_details(schema, object, options, ul, **attrs)

    children = list(ul.children)
    if len(children) == 1:
        yield from list(children[0].children)[1:]
    else:
        yield from details

def html_math(schema, object, options, *children, **attrs): pass
def html_navigation(schema, object, options, *children, **attrs): pass
def html_note(schema, object, options, *children, **attrs): pass

role_mapping = default_role_mapping = dict(
    banner=html_banner, 
    button=html_button,
    code=html_code,
    complementary=html_aside,
    contentinfo=html_contentinfo,
    cell=html_cell,
    checkbox=html_checkbox, 
    columnheader=html_columnheader,
    datetime=html_input_datetime, 
    dialog=html_dialog,
    figure=html_figure,
    form=html_form,
    # label=html_label,  # this is not a role
    group=html_details,
    heading=html_heading,
    img=html_img,
    input=html_input,   
    link=html_link,
    list=html_list, 
    listitem=html_listitem,
    listbox=html_listbox,
    math=html_math,
    main=html_main,
    navigation=html_navigation,
    note=html_note,
    radiogroup=html_radiogroup,
    radio=html_radiogroup, # makes sense to alias radiogroup with radio
    rowgroup=html_rowgroup,
    row=html_row, 
    rowheader=html_rowheader,
    spinbutton=html_spinbutton, 
    table=html_table,
    textbox=html_textbox,   
    textarea=html_textarea, 
    time=html_time
) | {None: html_null}


def html_markdown(schema, object, options, *children, **attrs):
    """render a markdown object as html"""
    import markdown_it
    if isinstance(object, list):
        object = "\n".join(object)
    html = markdown_it.MarkdownIt().render(object)
    yield parse_html(html, **attrs)

content_mapping = {
    "text/markdown": html_markdown,
} | {None: html_script_text}

def is_readonly(schema):
    return bool(schema.get("readonly"))
