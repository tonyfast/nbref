from dataclasses import dataclass, field

from nbref.templates.sf import html_heading

from .schemas import Schema
from .objects import Null, String

from .utils import el, get_length, parse_html


@dataclass
class Options(dict):
    renderer: "Html" = None

@dataclass
class Renderer:
    options: Options = field(default_factory=Options)
    def __post_init__(self):
        if self.options.renderer is None:
            self.options.renderer = self


def is_readonly(schema):
    # if schema.get("readOnly") or schema.get("readonly"):
    #         return True
    return False

def html_item_attrs(object, index, item):

    attrs = dict(
        data=dict(setsize=get_length(item)),
        aria=dict(
            setsize=len(object), posinset=index + 1
        )
    )
    attrs["class"] = [str(item.path[-1]), item.type()]

    if attrs["data"]["setsize"] is None:
        del attrs["data"]

    return attrs

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

def html_group(schema, object, options=None, *children, **attrs):
    section = el("section", **attrs)
    el(section, html_heading(schema, object, options))
    # el(section, options.renderer.render_inner(object, options))
    yield el(section, *children)
    # yield section

def html_details(schema, object, options=None, *children, **attrs):
    if schema.get("attrs", {}).get("open", True):
        attrs["open"] = ""
    section = el("section", **attrs)
    attrs.pop("item", None)
    attrs.pop("data", None)
    details = el("details", el("summary", html_key_value_title(schema, object, options)), **attrs)
    title = schema.title()
    el(details, el("p.description", object.description(), id=object.id("desc")))
    yield el(section, el(details, *children))

def html_key_value_title(schema, object, options=None, **attrs):
    attrs = html_attrs(schema, object, options, itemscope=True, **attrs)
    title = schema.title()
    yield el("span.key.schema", schema.title())
    if object.title() != title:
        yield el("span.title", object.title(), klass=["object"])
    elif isinstance(object, dict) and "@index" in object:
        yield el("span.title", object['@index'], klass=["object"])

def html_form(schema, object, options=None, *children, **attrs):
    attrs.setdefault("name", object.name)
    attrs = html_attrs(schema, object, options, itemscope=not options["depth"], **attrs)
    form = el(F"form.{object.type()}", **attrs)
    el(form, html_heading(schema, object, options))
    yield el(form, *children)

def html_heading(schema, object, options=None, **attrs):
    # print(dict(options))
    level = options.get("first_heading", 1) + options.get("depth", 0)
    description = el("p.description", object.description(), id=object.id("desc")) 
    heading = el(F"h{level}.title", object.title(), id=object.id("title"))
    return el("hgroup", heading, description)

def html_object(schema, object, options=None, **attrs):
    is_child = bool(options["depth"])
    attrs = html_attrs(schema, object, options, itemscope=is_child, **attrs)
    ul = el("ul.object", **attrs)
    options["depth"] += 1
    required = schema.get("required", [])
    for index, key in enumerate(required):
        item = object.get(key)
        if item is None:
            item = object.reflect(Null(), key)
        ats = html_item_attrs(object, index, item)
        el(ul, el("li", *options.renderer.render_outer(item, options), **ats))
        # el(ul, el("li", *options.renderer.render_outer(item, options), aria=dict(
        #     setsize=len(object), posinset=index + 1
        # )))

    # handle some pattern properties
    for index, key in enumerate(object):
        if key not in required:
            item = object.get(key)
            if item is None:
                item = object.reflect(Null(), key)
            ats = html_item_attrs(object, index, item)
            el(ul, el("li", *options.renderer.render_outer(item, options), **ats))
    options["depth"] -= 1
    yield html_details(schema, object, options, ul, **attrs)

def html_list(schema, object, options=None, **attrs):
    is_child = bool(options["depth"] == 0)
    attrs = html_attrs(schema, object, options, itemscope=is_child, **attrs)
    ol = el("ol.array", **attrs)
    options["depth"] += 1
    
    # make the starting index and option
    for index, item in enumerate(object, 1):
        ats = html_item_attrs(object, index, item)
        if isinstance(item, dict):

            # make the name an option
            item.setdefault("@index", index)
        el(ol, el("li", *options.renderer.render_outer(item, options, schema.property(index)), **ats))
    options["depth"] -= 1        
    yield html_details(schema, object, options, ol, **attrs)

def html_string(schema, object, options=None, **attrs):
    attrs = html_attrs(schema, object, options, itemscope=True, **attrs)
    yield html_label(schema, object, options, **attrs)
    yield el("input", type="text", value="".join(object), **attrs)

def html_number(schema, object, options=None, **attrs):
    attrs = html_attrs(schema, object, options, itemscope=True, **attrs)
    if object.type() == "integer":
        attrs.setdefault("step", "1")

    yield html_label(schema, object, options, **attrs)
    yield el("input", type="number", value=str(object), **attrs)

def html_boolean(schema, object, options=None, **attrs):
    attrs = html_attrs(schema, object, options, itemscope=True, **attrs)
    yield html_label(schema, object, options, **attrs)
    yield el("input", type="checkbox", checked=bool(object), **attrs)

def html_null(schema, object, options=None, **attrs):
    attrs = html_attrs(schema, object, options, itemscope=True, **attrs)
    yield el("span.null", el("span.key", schema.title()), "null")


def html_button(schema, object, options=None, **attrs):
    attrs = html_attrs(schema, object, options, itemscope=True, **attrs)
    yield el("button.button", str(object), **attrs)

def html_textarea(schema, object, options=None, **attrs):
    attrs = html_attrs(schema, object, options, itemscope=True, **attrs)
    body = "".join(object)
    attrs["rows"] = body.count("\n") + 1
    yield html_details(schema, object, options, el("textarea.textarea", *body, **attrs))

def html_link(schema, object, options=None, **attrs):
    attrs = html_attrs(schema, object, options, itemscope=True, **attrs)
    key = el("span.key", object.title(), id=object.id("title"), item=dict(type="dcterms:title"))
    value = str(object)
    yield el("a.link", key, value, href=str(object))

def html_label(schema, object, options=None, **attrs):
    attrs = html_attrs(schema, object, options, itemscope=True, **attrs)
    attrs["id"] = object.id("title")
    yield el("label.label", object.title(), **attrs)

def html_script(schema, object, options=None, **attrs):
    attrs = html_attrs(schema, object, options, itemscope=True, **attrs)

    attrs["type"] = schema.get("contentMediaType", "text/plain")
    yield el("script.script", *object, **attrs)

def html_select(schema, object, options=None, **attrs):
    attrs = html_attrs(schema, object, options, itemscope=True, **attrs)
    yield html_label(schema, object, options, **attrs)
    select = el("select.select", **attrs)
    for index, item in enumerate(object):
        ats = html_item_attrs(object, index, item)
        el(select, el("option", *options.renderer.render_outer(item, options), **ats))
    yield select


def html_markdown(schema, object, options=None, **attrs):
    import midgy
    print("md")

    object = object.reflect(String(midgy.tangle.get_markdown_it().render("".join(object))))
    yield from html_raw(schema, object, options, **attrs)

def html_raw(schema, object, options=None, **attrs):
    attrs = html_attrs(schema, object, options, itemscope=True, **attrs)
    yield parse_html("".join(object))

def html_plain(schema, object, options=None, **attrs):
    attrs = html_attrs(schema, object, options, itemscope=True, **attrs)
    yield el("pre.plain", *object, **attrs)

# def html_markdown(schema, object, options=None, **attrs):
#     attrs = html_attrs(schema, object, options, itemscope=True, **attrs)
#     yield el("div.markdown", *object, **attrs)

def html_dialog(schema, object, options=None, *children, **attrs):
    attrs = html_attrs(schema, object, options, itemscope=True, **attrs)
    open = attrs.pop("open", None)
    print("dialog!", open)
    if not open:
        dialog = el("dialog.dialog", **attrs)
    else:
        dialog = el("section.dialog", **attrs)
    yield el(dialog, *children)

default_outer_role_mapping = dict(
    dialog=html_dialog,
    form=html_form,
    banner=html_group,
    main=html_group,
    contentinfo=html_group,
    complementary=html_group,
    navigation=html_list,
)
default_inner_role_mapping = dict(
    link=html_link,
    textarea=html_textarea,
    button=html_button,
    listbox=html_select,
    select=html_select,
    list=html_list,
)
default_content_mapping = {
    "text/markdown": html_markdown,
    "text/html": html_raw,
    "text/plain": html_plain,
}
default_format_mapping = dict()
default_type_mapping = dict(
    array=html_list,
    object=html_object,
    string=html_string,
    number=html_number,
    integer=html_number,
    boolean=html_boolean,
    null=html_null
)

# 1. render the outer sectioning content roles
# 2. render the inner content
#  2.1 render the content roles for palpable, embedded, interactive content
#  

@dataclass
class Html(Renderer):
    outer_role_mapping: dict = field(default_factory=default_outer_role_mapping.copy)
    inner_role_mapping: dict = field(default_factory=default_inner_role_mapping.copy)
    format_mapping: dict = field(default_factory=default_format_mapping.copy)
    type_mapping: dict = field(default_factory=default_type_mapping.copy)
    content_mapping: dict = field(default_factory=default_content_mapping.copy)
    
    def render(self, object, options=None, schema=None):
        if options is None:
            options = self.options
        else:
            options = Options(options)
        options.renderer = self
        
        options.setdefault("depth", 0)
        options.setdefault("first_heading", 1)
        repr = list(self.render_outer(object, options, schema))
        if len(repr) == 1:
            return repr[0]
        
        if options["depth"] == 0:
            return el("form", *repr)
        return el("section", *repr)
    
    def render_wrapper(self, callables, object, options=None, schema=None):
        for callable in callables:
            i = -1
            for i, item in enumerate(callable(object, options, schema)):
                yield item
            if i > -1:             
                break


    def f(self, object, options=None, schema=None):
        options = options or self.options
        schema = schema or object.schema or Schema(type=object.type())
        yield from self.render_wrapper(
            [
                self.render_outer,
                self.render_inner_role,
                self.render_content,
                self.render_format,
                self.render_type,
                self.render_default,
            ],
            object,
            options,
            schema,
        )
        

    # outer sectioning content is a container for groups of information
    # these semantics replace traditional visual gestalt typesettting
    # with the appropriate types
    def render_outer(self, object, options=None, schema=None):
        """render the region around palpable, embedded, interactive, content."""
        # when no region is required then we yield from either the format or content mapping.
        # def render_role(self, object, options=None):
        options = options or self.options
        schema = schema or object.schema or Schema(type=object.type())
        role = schema.get("role")
        # print(dict(options),11)
        options.setdefault("depth", 0)
        # if options["depth"] == 0:
        #     role = "form"
        
        # render any sectioning or grouping content
        index = -1
        for index, item in enumerate(self.render_outer_role(object, options, schema)):
            yield item
        if index == -1:
            yield from self.render_inner(object, options, schema)

    def render_outer_role(self, object, options=None, schema=None):
        role = schema.get("role")
        options.setdefault("depth", 0)
        if options["depth"] == 0:
            role = "form"
        
        parent = schema.get("parent", {})
        children = []
        if role in self.outer_role_mapping:
            yield from self.outer_role_mapping[role](
                schema, object, options, *self.render_inner(object, options, schema)
            )

    def render_inner(self, object, options=None, schema=None):
        options = options or self.options
        schema = schema or object.schema
        yield from self.render_inner_role(object, options, schema)

    def render_inner_role(self, object, options=None, schema=None):
        role = schema.get("role")
        if role in self.inner_role_mapping:
            yield from self.inner_role_mapping[role](schema, object, options)
        else:
            yield from self.render_content(object, options, schema)

    def render_format(self, object, options=None, schema=None):
        format = schema.get("format")
        if format in self.format_mapping:
            yield from self.format_mapping[format](schema, object, options)
        else:
            yield from self.render_type(object, options, schema)

    def render_content(self, object, options=None, schema=None):
        content = schema.get("contentMediaType")
        if content in self.content_mapping:
            print(11, content)

            yield from self.content_mapping[content](schema, object, options)
        else:
            yield from self.render_format(object, options, schema)
        
    def render_enum(self, object, options=None, schema=None):
        enum = schema.get("enum")
        if enum is not None:
            yield from self.render_enum(object, options, schema)
        else:
            yield from self.render_type(object, options, schema)

    def render_type(self, object, options=None, schema=None):
        type = object.type()
        if type in self.type_mapping:
            yield from self.type_mapping[type](schema, object, options)
        else:
            yield from self.render_default(object, options)

    def render_default(self, object, options=None):
        attrs = dict()
        attrs.setdefault("item", {}).update(
            prop=object.path[-1]
        )
        yield el("pre", str(object), **attrs)


    def render_one_of(self, object, options=None, schema=None):
        one_of = schema.get("oneOf")
        if one_of is not None:
            if len(one_of) == 1:
                yield from self.render_inner(object, options, one_of[0])
            for subschema in one_of:
                yield from self.render_type(object, options, subschema)


        if one_of is not None:
            for subschema in one_of:
                yield from self.render_type(object, options, subschema)
        else:
            yield from self.render_type(object, options, schema)


    # outer sectioning content is a container for groups of information
    # these semantics replace traditional visual gestalt typesettting
    # with the appropriate types
    def render_outer(self, object, options=None, schema=None):
        """render the region around palpable, embedded, interactive, content."""
        # when no region is required then we yield from either the format or content mapping.
        # def render_role(self, object, options=None):
        options = options or self.options
        schema = schema or object.schema or Schema(type=object.type())
        role = schema.get("role")
        # print(dict(options),11)
        options.setdefault("depth", 0)
        # if options["depth"] == 0:
        #     role = "form"
        
        # render any sectioning or grouping content
        index = -1
        yield from self.render_wrapper(
            [
                self.render_outer_role,
                self.render_not,
                self.render_one_of,
                self.render_inner_role,
                self.render_content,
                self.render_format,
                self.render_type,
                self.render_default,
            ],
            object,
            options,
            schema,
        )

    def render_outer_role(self, object, options=None, schema=None):
        role = schema.get("role")
        options.setdefault("depth", 0)
        if options["depth"] == 0:
            role = "form"
        
        parent = schema.get("parent", {})
        children = []
        if role in self.outer_role_mapping:
            yield from self.outer_role_mapping[role](
                schema, object, options, *self.render_inner(object, options, schema)
            )


    def render_inner_role(self, object, options=None, schema=None):
        role = schema.get("role")
        if role in self.inner_role_mapping:
            yield from self.inner_role_mapping[role](schema, object, options)
        
    def render_format(self, object, options=None, schema=None):
        format = schema.get("format")
        if format in self.format_mapping:
            yield from self.format_mapping[format](schema, object, options)
        
    def render_content(self, object, options=None, schema=None):
        content = schema.get("contentMediaType")
        if content in self.content_mapping:
            yield from self.content_mapping[content](schema, object, options)
        
    def render_enum(self, object, options=None, schema=None):
        enum = schema.get("enum")
        if enum is not None:
            yield from html_select(schema, object, options)

    def render_type(self, object, options=None, schema=None):
        type = object.type()
        if type in self.type_mapping:
            yield from self.type_mapping[type](schema, object, options)


    def render_default(self, object, options=None):
        attrs = dict()
        attrs.setdefault("item", {}).update(
            prop=object.path[-1]
        )
        yield el("pre", str(object), **attrs)


    def render_one_of(self, object, options=None, schema=None):
        one_of = schema.get("oneOf")
        if one_of is not None:
            if len(one_of) == 1:
                yield from self.render_inner(object, options, one_of[0])
            else:
                ul = el("ul.oneOf")
                for index, subschema in enumerate(one_of):
                    li = el("li.one_of", *self.render_inner(object, options, subschema))
                    el(ul, li, aria=dict(posinset=index + 1, setsize=len(one_of)))
                yield ul

