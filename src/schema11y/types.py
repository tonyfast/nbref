from asyncio import exceptions
from contextlib import contextmanager
from dataclasses import dataclass, field
from functools import partial, wraps
import typing 
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

                        
        # if isinstance(root, Schema):
        #     return root
        self = super().__new__(cls)
        self.__init__(root=root, path=path, parent=parent, **kwargs)
        return self


    def __init__(self, root=EMPTY, path=None, parent=None, **kwargs):
        if root is EMPTY:
            root = kwargs

        while isinstance(root, Subschema):
            path = path or root.path
            parent = parent or root.parent
            root = root.root
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

    def __invert__(self):
        return Subschema({"not": self.root})
    
class Repr:
    def bs4(self, options: Options = None, **opts):
        from .html import html_bs4

        return list(html_bs4(self, options, **opts))
    
    def html(self, options: Options = None, **opts):
        from . html import html_render

        return html_render(self, options, **opts)

    def display(self, options: Options = None, **opts):
        from IPython.display import display
        display(self.html(options, **opts))

class Schema(Repr):
    @classmethod
    def from_string(cls, string):
        from yaml import safe_load
        return cls(safe_load(string))

    @classmethod
    def from_file(cls, filepath):
        with open(filepath, "r") as f:
            return cls.from_string(f.read())
        
    def __init__(self, schemas=None, **kwargs):
        self.schemas = []
        if schemas is None:
            schemas = []
        if not isinstance(schemas, list):
            schemas = [schemas]
        if kwargs:
            schemas.insert(0, kwargs)
        for i, schema in enumerate(schemas):
            if isinstance(schema, Schema):
                self.schemas.extend(schema.schemas)
                continue
            elif isinstance(schema, dict):
                schema = Subschema(schema)
            self.schemas.append(schema)

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
                schema.append(value)
        return schema

    def default(self):
        default = self.get("default", EMPTY)
        if default is EMPTY:
            return self._default()
        return default

    def _default(self):
        enum = self.get("enum")
        if enum:
            return enum[0]
        type = self.get("type", "null")
        if type == "string":
            return ""
        elif type == "number":
            return float()
        elif type == "integer":
            return int()
        elif type == "boolean":
            return bool()
        elif type == "array":
            return list()
        elif type == "object":
            return dict()
        elif type == "null":
            return None
        return EMPTY

    def property(self, key):
        value = self.value()
        schema = Schema().linked(value.get(key, EMPTY), self.aid().add(key), self.atype().add("properties", key))
        for subschema in self.schemas:
            properties = subschema.get("properties", {})
            if key in properties:
                schema.append(subschema.child("properties", key))
            else:
                additional = subschema.get("additionalProperties", EMPTY)
                if additional is not EMPTY:
                    schema.append(subschema.child("additionalProperties"))
        return schema

    def index(self, index):
        value = self.value()
        schema = Schema().linked(value[index], self.aid().add(index), self.atype().add("items", index))
        for subschema in self.schemas:
            prefixItems = subschema.get("prefixItems", [])
            if index < len(prefixItems):
                schema.append(subschema.child("prefixItems", index))
            else:
                items = subschema.get("items", None)
                if items is not None:
                    schema.append(subschema.child("items"))
        return schema
    
    def linked(self, value=EMPTY, id=None, type=None):
        linked_data = dict()
        if value is not EMPTY:
            linked_data["@value"] = value
        if id is not None:
            linked_data["@id"] = Pointer(id)
        if type is not None:
            linked_data["@type"] = Pointer(type)
        return self.override(**linked_data)
    
    def expand(self):
        return self

    def insert(self, index, *other):
        for schema in reversed(other):
            self.schemas.insert(index, Subschema(schema))
    
    def append(self, *other, **kwargs):
        if kwargs:
            other = (kwargs,) + other
        for schema in other:
            if isinstance(schema, Schema):
                self.schemas.extend(schema.schemas)
            else:
                self.schemas.append(Subschema(schema))
        return self

    def override(self, *schemas, **kwargs):
        if kwargs:
            schemas = (kwargs,)  + schemas
        schema = list()
        for s in schemas:

            if isinstance(s, Schema):
                schema.extend(s.schemas)
            elif isinstance(s, Subschema):
                schema.append(s)
            else:
                schema.append(Subschema(s))
        return Schema(schema + self.schemas)

    def add(self, *schemas, **kwargs):
        if kwargs:
            schemas = (kwargs,)  + schemas
        schema = list()
        for s in schemas:
            if isinstance(s, Schema):
                schema.extend(s.schemas)
            else:
                schema.append(s)
        return Schema(self.schemas + schema)
            
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

        if self.get("enum"):
            return "select"
        if self.get("format"):
            return "input"
        
        types = self.types() 
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

    def atype(self, *path):
        return Pointer(self.get("@type")).add(*path)

    def types(self):
        types = self.get("type")
        if isinstance(types, str):
            types = [types]
        if not types:
            # could add examples here
            t = Schema.infer(self.value()).get("type", EMPTY)
            if t is EMPTY or t == "null":
                return []
            return [t]
        return types

    def value(self):
        value = self.get("@value", EMPTY)
        if value is EMPTY:
            value = self.default()
        return value


    @classmethod
    def infer(cls, *objects):
        return Subschema.infer(*objects).expand()

    def __bool__(self):
        return bool(self.schemas)

    def errors(self, object=EMPTY):
        import jsonschema
        if object is EMPTY:
            object = self.value()
        # Implement validation logic here
        exceptions = []
        for schema in self.schemas:
            try:
                jsonschema.Draft202012Validator(schema.object()).validate(object)
            except jsonschema.ValidationError as e:
                exceptions.append(e)
        return exceptions

    def validate(self, object=EMPTY):
        exceptions = self.errors(object)
        if exceptions:
            raise ExceptionGroup("Validation errors", exceptions)
        return self