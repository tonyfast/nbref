
from abc import ABC
import builtins
import collections
from functools import partial, wraps
import itertools
import json
from operator import add, getitem, methodcaller
import re
from token import OP
from zipfile import Path
from bs4 import Tag
from typing import IO, Generator


DICT_TYPES = dict, collections.ChainMap

def schema_type_to_path_types(value):
    """convert a json schema into a python type from the standard library."""

    if "object" in value:
        return Dict
    elif "array" in value:
        return Array
    elif "string" in value:
        return String
    elif "null" in value:
        return Null
    
    elif "integer" in value:
        return Integer
    elif "number" in value:
        return Number
    elif "boolean" in value:
        return Boolean
    elif "enum" in value:
        return String
    return Null
    raise TypeError(f"Unsupported type: {value}")

def python_type_to_schema(value):
    if isinstance(value, DICT_TYPES):
        return "object"
    elif isinstance(value, (list, tuple)):
        return "array"
    elif isinstance(value, str):
        return "string"
    elif value is None:
        return "null"
    elif isinstance(value, int):
        return "integer"
    elif isinstance(value, float):
        return "number"
    elif isinstance(value, bool):
        return "boolean"
    return "null"
    raise TypeError(f"Unsupported type: {type(value)}")

class UNDEFINED:
    def __contains__(self, item):
        return False
    
UNDEFINED = None

def dispatch(value):
    from .schemas import Schema
    if isinstance(value, (Object, Schema)):
        return value
    if isinstance(value, (dict,)):
        return Dict(value)
    elif isinstance(value, (list, tuple)):
        return Array(value)
    elif isinstance(value, str):
        return String(value)
    elif isinstance(value, bool):
        return Boolean(value)
    elif value is None:
        return 
    elif isinstance(value, int):
        return Integer(value)
    elif isinstance(value, float):
        return Number(value)
    elif isinstance(value, Null):
        return value
    raise TypeError(f"Unsupported type: {type(value)}")

class Pointer(list):
    def __add__(self, value):
        return type(self)(super().__add__(value))
    
    def __radd__(self, value):
        return type(self)(super().__add__(value))
    
    def __str__(self):
        if self:
            if self[0] == "#":
                self = [getattr(self, "name", self[0])] + self[1:]
        return ':'.join(map(str, self))
    
    def set_name(self, name):
        self.name = name
        return self
    
    def pointer(self, *key):
        from jsonpointer import JsonPointer
        return str(JsonPointer.from_parts(self + list(key))).lstrip("/")

class HasPath:
    def __init__(self, *args, **kwargs):
        self.parent = getattr(self, "parent", None)
        self.root = getattr(self, "root", self)
        self.path = getattr(self, "path", Pointer("#"))
        self.name = getattr(self, "name", getattr(self.parent, "name", None))
        # the schema probably isnt set yet so this does little good
        if isinstance(self, (dict, collections.ChainMap, list)):
            super().__init__(*args, **kwargs)
        else:
            super().__init__()

    def set_name(self, name=None):
        if name is None:
            # set the naem from the schema
            if self.schema:
                from .schemas import Schema
                name = Schema.anchor(self.schema)
        if name is not None:
            self.name = name
            self.path.set_name(name)
        return self
    
    def set_parent(self, parent):
        self.parent = parent
        return self
    
    def set_root(self, root):
        self.root = root
        return self
    
    def _name_path(self):
        if self.schema:
            anchor = self.schema.root.get("$anchor")
            if anchor:
                self.path.set_name(anchor)
        return self
    
    def set_path(self, path):
        self.path = path
        self._name_path()
        return self
    
    def reflect(self, object, *key):
        from .schemas import Schema
        if object.root is object:
            object.set_root(self.root)
            object.set_parent(self)
        object.set_path(self.path + list(key))
        if object.name is None:
            object.set_name(self.name)
        if key:
            property = Schema.property(self.schema, *key) if self.schema is not None else None
            if property:
                object.set_schema(property)
        return object

    # need to iunfer namespace
    def infer_name(self):
        import gc
        names = collections.deque()
        for referrer in gc.get_referrers(self):
            if isinstance(referrer, dict):
                possible = referrer.get("__file__")
                if not possible:
                    possible = referrer.get("__name__")
                if possible:
                    spec = referrer.get("__spec__")
                    if spec:
                        pair = spec.name,
                    else:
                        pair = possible,
                    
                    pair +=  list(referrer)[list(referrer.values()).index(self)],
                    if pair[1].isalpha() or possible in ("__main__", "__init__"):
                        names.appendleft(pair)
                    else:
                        names.append(pair)
        return Dict(possible=names, probable=names[0])["probable"]


class HasSchema:
    def __init__(self, *args, **kwargs):
        if not hasattr(self, "schema"):
            self.schema = None
        super().__init__(*args, **kwargs)
    
    def set_schema(self, schema):
        from .schemas import Schema
        if self.schema is None:
            self.schema = Schema()
        if not self.schema:
            if not isinstance(schema, Schema):
                schema = Schema(schema)
            self.schema = schema
        return self
    
    def errors(self):
        if self.schema:
            from .schemas import Schema
            return Schema.errors(self.schema, self)
        return []
    
    def validate(self, raises=True):
        if self.schema:
            from .schemas import Schema
            Schema(self.schema).validate(self, raises=raises)
            return self
        return self
    
    def infer_schema(self):
        from .schemas import Schema
        self.set_schema(Schema.from_objects(self))
        return self
    
class HasRepr(HasSchema):
    def repr(self, type="text/plain"):
        # this function assumes that there is a schema with the repr project that defines the output mimetypes
        if self.schema:
            repr = self.schema.property("repr").property(type).get("default", None)
            if repr:
                import importlib.metadata
                return importlib.metadata.EntryPoint(None, repr, None).load()
        return self.__class__.dumps
    
    def repr_html(self, *schema, **kwargs):
        from .html import Html, Schema
        if schema or kwargs:
            schema = Schema(*schema, **kwargs)
            if self.schema:
                schema.append(self.schema)
        else:
            schema = None
        return Html.format_object(self, schema)
        # else:
        #     return Html.format_object(self)

    html = repr_html

    def display(self, *schema, **kwargs):
        from IPython.display import display, HTML
        display(HTML("".join(map(str, self.html(*schema, **kwargs)))))

        

    # def _repr_html_(self):
    #     return self.repr_html(display=True)
        
    def __str__(self):
        return self.repr("text/plain")(self.builtin())
    
    def builtin(self):
        return self.python_type(self) if getattr(self, "python_type", None) else self

class Object(HasRepr, HasPath):
    python_type = None
    import referencing.jsonschema
    default_specification =  referencing.jsonschema.DRAFT202012
    del referencing
    
    # def __new__(cls, *args, **kwargs):
    #     no_args = issubclass(cls, (dict, list, collections.ChainMap))
    #     if no_args:
    #         self = super().__new__(cls)
    #         self.__init__(*args, **kwargs)
    #     else:
    #         self = super().__new__(cls, *args, **kwargs)
    #         self.__init__(*args, **kwargs)

    #     return self

    # def __init__(self, *args, **kwargs):
    #     if isinstance(self, (dict, list, collections.ChainMap)):
    #         super().__init__(*args, **kwargs)
    #     else:
    #         super().__init__()
    #     self._id = None

    def __class_getitem__(cls, item):
        if not isinstance(item, tuple):
            item = item,
        from .schemas import Schema
        if not isinstance(item, Schema):
            item = Schema(*item)
        return type(cls.__name__, (cls,), dict(schema=item))
    
    def __repr__(self):
        if self.schema:
            return str(self.repr("text/plain")(self))
            # repr = self.schema.property("repr").property("text/plain").get("default", None)
            # if isinstance(self, Object):
            #     self = self.builtin()
            # if repr is not None:
            #     import importlib.metadata
            #     return importlib.metadata.EntryPoint(None, repr, None).load()(self)
        # if isinstance(self, Object):
        #     return str(self.builtin())
        return super(type(self), self).__str__()
          

    def dumps(self):
        import json
        json.dict = Dict
        json.list = Array
        json.str = String
        json.float = Number
        json.int = Integer
        json.bool = Boolean
        if isinstance(self, Object):
            if isinstance(self, collections.ChainMap):
                self = self.builtin()
        try:
            return json.dumps(self, indent=4).strip('"')
        finally:
            try:
                del json.dict, json.list, json.str, json.float, json.int, json.bool
            except AttributeError:
                pass

    # the string representation needs to exist to simply the creation of html elements.
    __str__ = dumps
    
    def print(self):
        print(str(self))

    def type(self):
        from .schemas import Schema
        if not isinstance(self, Object):
            self = Object.dispatch(self).infer_schema()
            
        if self.schema:
            types = Schema.types(self.schema)
            if types:
                if len(types) == 1:
                    return types[0]
                return types
        return python_type_to_schema(self)
    
    def schema_type(self):
        if self.schema:
            return self.schema.type()
        return python_type_to_schema(self)
    
    def types(self):
        type = self.type()
        if not isinstance(type, list):
            type = [type]
        return type
    
    def set_id(self, id):
        self._id = id
        return self
        
    @classmethod
    def dispatch(cls, value):
        from .schemas import Schema
        if isinstance(value, (Object, Schema)):
            return value
        if isinstance(value, (dict,)):
            object = Dict(value)
            if issubclass(cls, Schema):
                return cls(object)
            return object
        elif isinstance(value, (list, tuple)):
            return Array(value)
        elif isinstance(value, str):
            return String(value)
        elif isinstance(value, bool):
            return Boolean(value)
        elif value is None:
            return 
        elif isinstance(value, int):
            return Integer(value)
        elif isinstance(value, float):
            return Number(value)
        elif isinstance(value, Null):
            return value
        raise TypeError(f"Unsupported type: {type(value)}")

    def pipe(self, func, *args, **kwargs):
        return func(self, *args, **kwargs)
    
    def pipes(self, *funcs):
        for func in funcs:
            self = func(self)
        return self
    
    @classmethod
    def from_string(cls, object, format=None):
        from yaml import safe_load
        return cls.dispatch(safe_load(object))
    
    @classmethod
    def from_file(cls, file, format=None):
        from pathlib import Path
        file = Path(file)
        return cls.from_string(file.read_text(), format=format)
        
    
def guess_mimetype(string):
    if re.match(r"^\s*{", string):
        return "application/json"
    elif re.match(r"^\s*<", string):
        return "text/html"
    else:
        return "text/plain"

class Dict(Object, dict):
    python_type = dict

    def get(self, key, default=None):
        try:
            return self[key]
        except KeyError:
            return default
        
    def items(self):
        # override the items method so we ensure that the path and schema are carried forward to the child objects.
        for key in self:
            yield key, self[key]

    def __setitem__(self, key, value):
        object = self.root
        for k in self.path[1:]:
            object = Dict.__getitem_native__(object, k)
        if isinstance(object, dict):
            dict.__setitem__(object, key, value)
        elif isinstance(object, list):
            list.__setitem__(object, key, value)
        else:
            raise AttributeError(f"Unsupported type: {type(object)}")

    def __getitem_native__(self, key):
        if isinstance(self, dict):
            return dict.__getitem__(self, key)
        elif isinstance(self, list):
            return list.__getitem__(self, key)
        elif isinstance(self, str) and isinstance(key, (int, slice)):
            return str.__getitem__(self, key)
        else:             
            # print(self, type(self), key)
            raise TypeError(f"Unsupported type: {type(self)}")

    def __getitem__(self, key):
        if isinstance(key, tuple):
            object = self
            for k in key:
                object = object[k]
            return object
            # return Getter.get_pointer(self, key)
        value = Dict.__getitem_native__(self, key)
        # is_schema = isinstance(self.root, Schema)

        object = Object.dispatch(value)
        if object is not None:
            self.reflect(object, key)
            # object.set_parent(self)
            # if object.root is object:
            #     object.set_root(self.root)
            # object.set_path(self.path + [key])

            # if self.schema:
            #     from .schemas import Schema
            #     object.set_schema(Schema.property(self.schema, key))
        return object
    
    # def properties(self):
    #     if self.schema:
    #         keys = list(self.schema.properties())
    #         yield from keys
    #         for key in self:
    #             if key not in keys:
    #                 yield key
    #     else:
    #         yield from self.keys()

    def builtin(self) -> dict:
        """return a builtin python dict with the same content as this object, but without the path and schema information."""
        return dict(
            (key, value.builtin() if hasattr(value, "builtin") else value) for key, value in self.items()
        )

class Dicts(Object, collections.ChainMap):
    python_type = dict

    def __init_map(self, map):
        return Object.dispatch(map)

    def builtin(self) -> dict:
        """an builtin python dict that merges the content as this object, but without the path and schema information."""
        object = dict()
        for map in self.maps:
            for key, value in map.items():
                if key in object:
                    if isinstance(object[key], (dict, collections.ChainMap)):
                        object[key].update(value.builtin() if hasattr(value, "builtin") else value)
                    else:
                        continue
                else:
                    object[key] = value.builtin() if hasattr(value, "builtin") else value
        return object
    
    # def dict(self):
    #     if isinstance(self, collections.ChainMap):
    #         object = dict.fromkeys(list(self))
    #         for map in self.maps:
    #             object.update(map)
    #         return object
    #     return self
    
    
    def all(self, key, default=BaseException):
        # in theory only schemas should be chainmaps.
        from .schemas import Schema

        if isinstance(self, collections.ChainMap):
            try:
                object = collections.ChainMap.__getitem__(self, key)
            except () if default is BaseException else KeyError:
                return default
            if isinstance(object, (dict, collections.ChainMap)):
                object = self.reflect(self.all_dicts(key), key)
                # object = self.all_dicts(key).set_root(self.root).set_parent(self).set_path(self.path + [key])
        else:
            try:
                object = self[key]
            except () if default is BaseException else KeyError:
                return default
            
            if not isinstance(object, Schema):
                # why is this here? i think schemas are the only thing that make sense to have a dictionary mapping.
                # this wont be consistent more generally.
                object = self.reflect(Schema(object), key)
                # object = Schema(object).set_root(self.root).set_parent(self).set_path(self.path + [key])

        # if self.schema:
        #     object.set_schema(Schema.property(self.schema, key))
        return object
    
    def all_strings(self, key):
        if isinstance(self, collections.ChainMap):
            lines = Array()
            if self.schema:
                lines.set_schema(self.set_schema(self.schema))
            for i in range(len(self.maps)):
                map = self.maps[i]
                if key in map:
                    lines.append(map[key])
        else:
            lines = [self[key]] if key in self else []
        return self.reflect(Array(lines), key)

    def all_dicts(self, key):
        from .schemas import Schema
        values = []
        for i in range(len(self.maps)):
            map = self.maps[i]
            if key in map:
                # agtain this assumes taht only schemas can be chained maps.
                values.append(self.reflect(Schema(map[key]), key).expand())
        return self.reflect(Schema(*values), key)
    
    __truediv__ = __getitem__ = all

    def append(self, schema):   
        self.maps += self.__init_map(schema),
        if not self.maps[-1].schema:
            self.maps[-1].set_schema(self.schema)
        return self
    
    def extend(self, schema):
        for s in schema:
            self.append(s)
        return self
    
    def get(self, key, default=None):
        try:
            return self[key]
        except KeyError:
            return default
        
    # def dumps(self):
    #     return Object.dumps(self.builtin())
    
class Array(Object, list):
    __getitem__ = Dict.__getitem__

    def __iter__(self):
        # a compatibility function to ensure the path is tracked
        for i in range(len(self)):
            yield self[i]

    def builtin(self):
        return [value.builtin() if hasattr(value, "builtin") else value for value in self]

class Number(Object, float):
    python_type = float

class Integer(Object, int):
    python_type = int

class Boolean(Integer, ABC):
    python_type = bool
    def __str__(self):
        return "true" if self else "false"
    __repr__ = __str__
Boolean.register(bool)

class String(Object, str):
    python_type = str
    __getitem__ = Dict.__getitem__

class Uri(String):
    def parse(self):
        import urllib.parse
        return urllib.parse.urlparse(self)
    
class Ref(String):
    import referencing, jsonschema_specifications
    _cached_schema = {}
    

    def retrieve(uri):
        import requests_cache, requests, referencing
        requests_cache.install_cache("nbref_cache")

        response = requests.get(uri)
        data = requests.get(uri).json()
        return referencing.Resource.from_contents(data, Ref.default_specification)

    REGISTRY = referencing.Registry(
        jsonschema_specifications.REGISTRY._resources,
        jsonschema_specifications.REGISTRY._anchors,
        jsonschema_specifications.REGISTRY._uncrawled,
        retrieve
    ).crawl()

    del referencing, jsonschema_specifications

    
    def resolver(self, root=None):
        import referencing
        if root is None:
            # the root will usually be passed from an outer scope
            root = self.root
        if isinstance(root, str):
            # when the root is a string we have a uri referencing a schema and not root yet.
            return Ref.REGISTRY.resolver(self)
        # the scoped root is used to deference $ref $dynamicRef in the current schema
        return Ref.REGISTRY.resolver_with_root(referencing.Resource.from_contents(root, self.default_specification))
    
    def resolve(self, root=None):
        # the root is passed by an expansion function
        from .schemas import Schema
        subschema = Schema.dispatch(Ref.resolver(self, root).lookup(str.__str__(self)).contents)

        return subschema

# class Core:
#     def id(self, *ids):
#         return str(self.path + list(ids))
    
class Null(Object):
    def __str__(self):
        return ""
    
    def __bool__(self):
        return False
    
    def builtin(self):
        return
    
    def __repr__(self):
        return "Null"

# it doesnt seem to make sense to put raw strings in an output in the web beacuse of a lack of context.
# the formatter can use @type, contentMediaType, and format to determine how to render a string.