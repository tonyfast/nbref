from asyncio import exceptions
from contextlib import contextmanager
from dataclasses import dataclass, field
from functools import partial, wraps
from logging import root
from pathlib import Path
import typing 
from toolz import pipe, compose_left as compose

class ValidationError(ExceptionGroup):
    pass

class Pointer(list):
    """a json pointer that can be flexibility formatted."""
    sep = "/"
    def __init__(self, *args, **kwargs):
        if args == (None,):
            args = ()
        if args:
            if isinstance(args[0], str):
                from jsonpointer import JsonPointer
                print(args[0])
                ptr = args[0]
                if not ptr.startswith("/"):
                    ptr = "/" + ptr
                args =  (JsonPointer(ptr).parts, ) + args[1:]
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

    def raw(self, sep=""):
        return sep.join(map(str, self))
    
    def __str__(self):
        return self.string()

class EMPTY:
    pass

class Subschema:
    from .referencing import default_registry
    REGISTRY = default_registry()
    del default_registry

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

    def object(self):
        return self.path.resolve(self.root)

    def expand(self):
        return Schema([self]).override(*self.expand_ref())

    def expand_ref(self):
        ref = self.get("$ref")

        if ref:
            root = self.root.get("@vocab", self.root.get("$id"))
            if root is None:
                from referencing import Resource, jsonschema
                resolver = self.REGISTRY.resolver_with_root(Resource(self.root, jsonschema.DRAFT202012))
            elif isinstance(ref, str) and ref.startswith("#"):
                return [Subschema(self.root, path=Pointer(ref), parent=self.parent)]
            else:
                resolver = self.REGISTRY.resolver(root)
            contents =resolver.lookup(ref).contents
            # relative pointers need the root reattached to their schema in fact this fucntion should export shcema
            return [contents] 
        return []

    def get(self, key, default=None):
        return self.path.add(key).resolve(self.root, default=default)
    
    def __repr__(self):
        return self.path.string() + "@" + repr(self.object())

    @classmethod
    def infer(cls, *objects):
        from .utils import infer_schema
        return cls(infer_schema(*objects))

    def child(self, *path):
        return Subschema(root=self.root, path=self.path.add(*path), parent=self)

    def __invert__(self):
        return Subschema({"not": self.root})

    @classmethod
    def resolve(cls, object):
        return cls.REGISTRY._retrieve(object).contents

    
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
        return cls(Subschema.REGISTRY._retrieve(filepath).contents)

    from_id = classmethod(from_file.__func__)
    def load(self, object, id=None, type=None, base=None):
        #  this will breka when object reutrns a list. need to hand this
        # damn base uri somehow
        schema = Subschema.REGISTRY._retrieve(object, key="@base").contents
        return self.linked(schema, id=id, type=type)
    
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

    def default(self, default=EMPTY):
        value = self.get("default", default)
        if value is EMPTY:
            return self._default()
        return value
    def _default(self, default=EMPTY):
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
        value = self.value(EMPTY)
        try:
            value = value[key]
        except (KeyError, TypeError):
            value = EMPTY
        schema = Schema().linked(
            value, self.aid().add(key), self.atype().add("properties", key),
            self.abase(),
            self.avocab(),
        )
        for subschema in self.expand_all().schemas:
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
        try:
            value = value[index]
        except (IndexError, TypeError):
            value = EMPTY
        schema = Schema().linked(value, self.aid().add(index), self.atype().add("items"), self.abase(), self.avocab())
        for subschema in self.expand_all().schemas:
            prefixItems = subschema.get("prefixItems", [])
            if index < len(prefixItems):
                schema.append(subschema.child("prefixItems", index))
            else:
                items = subschema.get("items", None)
                if items is not None:
                    schema.append(subschema.child("items").expand())
        return schema
    
    def linked(self, value=EMPTY, id=None, type=None, base=None, vocab=None):
        linked_data = dict()
        if value is not EMPTY and value is not None:
            linked_data["@value"] = value
        if id is not None:
            linked_data["@id"] = Pointer(id)
        if type is not None:
            linked_data["@type"] = Pointer(type)
        if base is not None:
            linked_data["@base"] = base
        if vocab is not None:
            linked_data["@vocab"] = vocab
        return self.override(**linked_data)
    
    def expand_all(self):
        schema = Schema()
        for i, subschema in enumerate(self.schemas):
            allOf = subschema.get("allOf", None)
            if allOf is not None:
                for j, subsubschema in enumerate(allOf):
                    schema.append(*subschema.child("allOf", j).expand().schemas)
                break
        return self.override(schema)
    
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

    def abase(self, *path):
        return self.get("@base")

    def avocab(self, *path):
        return self.get("@vocab")

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

    def value(self, default=EMPTY):
        value = self.get("@value", EMPTY)
        if value is EMPTY:
            value = self.default(default)
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