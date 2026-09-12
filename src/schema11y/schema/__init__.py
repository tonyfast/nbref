
from contextlib import contextmanager
from dataclasses import dataclass, field
from functools import partial, wraps
import typing 
from numpy import isin
from toolz import pipe, compose_left as compose

class ValidationError(ExceptionGroup):
    pass

def el_from_tag(tag, *children, **attrs):
    import bs4
    if isinstance(tag, str):
        tag = bs4.Tag(name=tag)
    for child in children:
        if isinstance(child, typing.Generator):
            child = list(child)
        if isinstance(child, list):
            for subchild in child:
                tag.append(subchild)
        else:
            tag.append(child)
    tag.attrs.update(attrs)
    return tag

def el_from_selector(selection, *children, first=True, **attrs):
    import cssselect, bs4
    if isinstance(selection, bs4.Tag):
        return el_from_tag(selection, *children, **attrs)
    if isinstance(selection, str):
        selection = cssselect.parse(selection)

    if isinstance(selection, list):
        elements = []
        for element in selection:
            element = el_from_selector(element, *children, **attrs)
            if first:
                return element
            elements.append(element)
        return elements
        

    elif isinstance(selection, cssselect.Selector):
        return el_from_selector(selection.parsed_tree, *children, **attrs)
    elif isinstance(selection, cssselect.parser.Element):
        return el_from_tag(selection.element, *children, **attrs)
    elif isinstance(selection, cssselect.parser.Hash):
        attrs.update(id=selection.id)
        return el_from_selector(selection.selector, *children, **attrs)
    elif isinstance(selection, cssselect.parser.Class):
        attrs.setdefault("class", []).append(selection.class_name)
        return el_from_selector(selection.selector, *children, **attrs)
    elif isinstance(selection, cssselect.parser.CombinedSelector):
        return el_from_selector(selection.selector, el_from_selector(selection.subselector), *children, **attrs)
    raise ValueError(f"Unsupported selection type: {selection}")
element = el_from_selector

class Pointer(list):
    """a json pointer that can be flexibility formatted."""
    sep = "/"
    def __init__(self, *args, **kwargs):
        if args == (None,):
            args = ()
        super().__init__(*args, **kwargs)
        if not self:
            self.extend(["#"])

    def resolve(self, object, default=None):
        """resolve a pointer in a document"""
        from jsonpointer import JsonPointer
        return JsonPointer.from_parts(self[1:]).resolve(object, default=default)

    def add(self, *parts):
        return Pointer(self + list(parts))

    def pointer(self):
        from jsonpointer import JsonPointer
        return JsonPointer.from_parts(self)

    def string(self, sep="/"):
        if sep == "/":
            return str(self.pointer())
        return str(self.pointer()).replace("/", sep)
    
    def __str__(self):
        return self.string()

class EMPTY:
    pass

class Subschema:
    def __new__(cls, root=EMPTY, path=None, parent=None, **kwargs):
        if isinstance(root, Subschema):
            path = path or root.path
            parent = parent or root.parent
            root = root.root
                        
        if isinstance(root, Schema):
            return root
        self = super().__new__(cls)
        self.__init__(root=root, path=path, parent=parent, **kwargs)
        return self


    def __init__(self, root=EMPTY, path=None, parent=None, **kwargs):
        if root is EMPTY:
            root = kwargs
        if root is None:
            root = object
            
        self.root = root
        self.path = Pointer(path)
        self.parent = parent

    def  object(self):
        return self.path.resolve(self.root)

    def expand(self):
        return Schema([self])

    def get(self, key, default=None):
        return self.path.add(key).resolve(self.root, default=default)
    
    def __repr__(self):
        return self.path.string() + "@" + repr(self.object())

    @classmethod
    def infer(cls, *objects):
        from genson import SchemaBuilder
        builder = SchemaBuilder()
        for obj in objects:
            builder.add_object(obj)
        schema = builder.to_schema()
        schema.pop("$schema", None)
        return cls(schema)

    def child(self, *path):
        return Subschema(root=self.root, path=self.path.add(*path), parent=self)

class Schema:
    def __init__(self, schemas=None, **kwargs):
        self.schemas = schemas or []
        if not isinstance(self.schemas, list):
            self.schemas = [self.schemas]
        for i, schema in enumerate(self.schemas):
            if not isinstance(schema, Subschema):
                self.schemas[i] = Subschema(schema)

        if kwargs:
            self.schemas.insert(0, Subschema(kwargs))

    def __repr__(self):
        return repr(self.schemas)


    def __post_init__(self):
        if not isinstance(self.schemas, list):
            self.schemas = [self.schemas]

    def get(self, key, default=None):
        for schema in self.schemas:
            value = schema.get(key, EMPTY)
            if value is not EMPTY:
                return value
        return default

    def subschema(self, key, default=None):
        schema = Schema()
        for subschema in self.schemas:
            value = subschema.get(key, EMPTY)
            if value is not EMPTY:
                schema.schemas.append(value)
        return schema

    def default(self):
        return self.get("default")

    def property(self, key):
        value = self.value()
        schema = Schema().linked(value.get(key, EMPTY), self.aid().add(key))
        for subschema in self.schemas:
            properties = subschema.get("properties", {})
            if key in properties:
                schema.append(subschema.child("properties", key))
            else:
                print('additiona', subschema.get("additionalProperties", EMPTY))
                additional = subschema.get("additionalProperties", EMPTY)
                if additional is not EMPTY:
                    schema.append(subschema.child("additionalProperties"))
        return schema

    def index(self, index):
        value = self.value()
        schema = Schema().linked(value[index], self.aid().add(index))
        for subschema in self.schemas:
            prefixItems = subschema.get("prefixItems", [])
            if index < len(prefixItems):
                schema.append(Subschema(subschema.root, subschema.path.add("prefixItems", index), subschema.parent))
            else:
                items = subschema.get("items", None)
                if items is not None:
                    schema.append(Subschema(subschema.root, subschema.path.add("items"), subschema.parent))
        return schema
    
    def linked(self, value=EMPTY, id=None, type=None):
        linked_data = dict()
        if value is not EMPTY:
            linked_data["@value"] = value
        if id is not None:
            linked_data["@id"] = Pointer(id)
        if type is not None:
            linked_data["@type"] = Pointer(type)
        self.append(linked_data)
        return self
    
    def expand(self):
        return self

    def insert(self, index, *other):
        for schema in reversed(other):
            self.schemas.insert(index, Subschema(schema).expand().schemas)
    
    def append(self, *other):
        for schema in other:
            self.schemas.extend(Subschema(schema).expand().schemas)

    def add(self, *schemas, **kwargs):
        if kwargs:
            schemas = (kwargs,)  + schemas
        return Schema(list(map(Subschema, schemas)) + self.schemas)
            
    def __add__(self, other):
        return self.add(other)

    def __radd__(self, other):
        return Subschema(other).expand() + self

    def __iadd__(self, other):
        self.append(other)
        return self
    
    def role(self, input=True):
        role = self.get("role", EMPTY)
        if role is not EMPTY:
            return role
        if self.get("format"):
            return "input"
        
        types = self.types() 
        print(types)
        if "array" in types:
            return "list"
        if "object" in types:
            return "associationlist"

        if input:
            if "integer" in types: 
                return "spinbutton"
            if "enum" in types:
                return "select"
            if "number" in types:
                return "spinbutton"
            if "string" in types:
                return "textbox"
            if "boolean" in types:
                return "checkbox"
        

    def aid(self, *path):
        return Pointer(self.get("@id")).add(*path)

    def atype(self):
        return self.get("@type")

    def types(self):
        types = self.get("type")
        if isinstance(types, str):
            types = [types]
        if not types:
            # could add examples here
            return Schema.infer(self.value()).types()
        return types

    def value(self):
        value = self.get("@value", EMPTY)
        if value is EMPTY:
            value = self.default()
        return value

    def bs4(self, options: Options = None):
        return list(html_bs4(self, options))

    def html(self, options: Options = None):
        return html_render(self, options)

    def display(self, options: Options = None):
        from IPython.display import display
        display(self.html(options))

    @classmethod
    def infer(cls, *objects):
        return Subschema.infer(*objects).expand()

    def __bool__(self):
        return bool(self.schemas)


role_mapping = dict()
content_mapping = dict()
format_mapping = dict()

@dataclass
class Options:
    evaluated: list = field(default_factory=role_mapping.copy)
    role: dict = field(default_factory=role_mapping.copy)
    content: dict = field(default_factory=content_mapping.copy)
    format: dict = field(default_factory=format_mapping.copy)
    el: callable = field(default_factory=lambda: el_from_selector)

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
        return callable(schema, options, *children, **attrs)
    return wrapper
    return main


def html_render(schema: Schema, options: Options = Options()):
    from IPython.display import display, HTML
    return HTML("".join(map(str, html_bs4(schema, options))))

def html_bs4(schema: Schema, options: Options, *children, **attrs):
    if isinstance(options, dict):
        options = Options(**options)
    elif options is None:
        options = Options()
    options.evaluated = []
    yield from html_root(schema, options)

def html_root(schema: Schema, options: Options, *children, **attrs):
    yield from html_parent(schema, options, *html_core(schema, options))

def html_parent(schema: Schema, options: Options, *children):
    parent = schema.subschema("parent")
    if parent.schemas:
        yield from html_role(parent.linked(id=schema.aid("parent")), options, *children)
    else:
        yield from children

def html_core(schema: Schema, options: Options, *children):
    types = schema.types()
    if "array" not in types and "object" not in types:
        content = html_content(schema, options)
        yield options.el("output.read", content, role="none")
    yield from html_applicator(schema, options, *children)

def html_applicator(schema: Schema, options: Options, *children):
    yield from html_all_of(schema, options, *children)

def html_all_of(schema: Schema, options: Options, *children):
    all_of = schema.get("allOf", [schema])
    if all_of:
        for subschema in all_of:
            yield from html_one_of(subschema, options, *children)

def html_one_of(schema: Schema, options: Options, *children):
    one_of = schema.get("oneOf", [schema])
    exceptions = []
    for subschema in one_of:
        yield from html_validator(subschema, options, *children)

def html_content(schema: Schema, options: Options, *children, **attrs):
    content_schema = schema.subschema("contentSchema")
    if content_schema.schemas:
        return html_core(content_schema, options) 
    
    content_type = schema.get("contentMediaType")
    callable = options.content.get(content_type)

    yield from callable(schema, options)

def html_validator(schema: Schema, options: Options, *children):
    yield from html_role(schema, options, *children)

def html_role(schema: Schema, options: Options, *children):
    role = schema.role()
    callable = options.role.get(role)
    print(schema, callable, role)
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
        item = options.el("li.array", html_root(subschema, options))
        options.evaluated.append(str(subschema.aid()))
        options.el(ol, item)
    yield ol
@attrs
def html_associationlist(schema: Schema, options: Options, *children, **attrs):
    object = schema.value()
    ul = options.el("ul")
    for key in object:
        subschema = schema.property(key)
        item = options.el("li", html_root(subschema, options))
        options.evaluated.append(str(subschema.aid()))
        options.el(ul, item)
    yield ul

def html_plain(schema: Schema, options: Options, *children, **attrs):
    object = schema.value()
    yield str(object)
    yield from children


def html_script(schema: Schema, options: Options, *children, **attrs):
    content_type = schema.get("contentMediaType")
    yield options

def unified_string(string):
    if isinstance(string, list):
        return "".join(unified_string(s) for s in string)
    return str(string)

def html_paragraph(schema: Schema, options: Options, *children, **attrs):
    yield options.el("p", unified_string(schema.value()))

@attrs
def html_textbox(schema: Schema, options: Options, *children, **attrs):
    expanded = schema.subschema("aria").get("expanded", False)
    if expanded:
        yield from html_textarea(schema, options)
        return
    yield from html_label(schema, options)
    yield from html_plain(schema, options)

def html_textarea(schema: Schema, options: Options, *children, **attrs):
    yield from html_label(schema, options)
    yield options.el("textarea", unified_string(schema.value()))

def html_label(schema: Schema, options: Options, *children, **attrs):
    label_attrs = {"for": attrs.get("id")}
    label_attrs["for"] or label_attrs.pop("for")

    yield options.el("label", html_title(schema, options), **label_attrs)

def html_title(schema: Schema, options: Options, *children, **attrs):
    yield options.el("span.path", str(schema.aid()))
    yield options.el("span.title", schema.get("tittle", ""))

def html_metadata(schema: Schema, options: Options, *children, **attrs):
    yield from html_description(schema, options)

def html_description(schema: Schema, options: Options, *children, **attrs):
    yield options.el("p.description", unified_string(schema.value()))

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
    yield from html_label(schema, options)

@attrs  
def html_landmark(schema: Schema, options: Options, *children, tag="section", **attrs):
    yield options.el(tag, *children, **attrs)

def html_link(schema: Schema, options: Options, *children, **attrs):
    yield options.el("a", *children, **attrs)

role_mapping[None] = html_plain
role_mapping.update(
    list=html_list,
    associationlist=html_associationlist,
    text=html_plain,
    spinbutton=html_number,
    checkbox=html_checkbox, 
    group=html_landmark,
    main=partial(html_landmark, tag="main"),
    banner=partial(html_landmark, tag="header"),
    contentinfo=partial(html_landmark, tag="footer"),
    complementary=partial(html_landmark, tag="aside"),
    link=html_link,
)
content_mapping[None] = html_plain