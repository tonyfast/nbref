from abc import ABC
import collections
from curses import meta
from dataclasses import dataclass
from functools import partial, singledispatch, wraps
from operator import add, ge, getitem, methodcaller
import re


DICT_TYPES = dict, collections.ChainMap

@singledispatch
def dispatch(value):
    if value is Expanded:
        return value
    raise TypeError(f"Unsupported type: {type(value)}")


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



class Pointer(list):
    """a list of a pointer to an object in a json document."""
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

# in schema operation it is important to know where an
# object is in the type and name space.
class HasPath:
    def __init__(self, *args, **kwargs):
        # self.parent = getattr(self, "parent", None)
        # self.path = getattr(self, "path", Pointer("#"))
        # self.name = getattr(self, "name", getattr(self.parent, "name", None))
        # the schema probably isnt set yet so this does little good
        self.root = self
        self.path = getattr(self, "path", Pointer("#"))
        self.name = None
        if isinstance(self, (dict, collections.ChainMap, list)):
            super().__init__(*args, **kwargs)
        else:
            super().__init__()
        
        if args and isinstance(args[0], Object):
            args[0].reflect(self)
        
        
        # self.root = getattr(self, "root", self)
        
        
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
        # if object.root is object:
        object.set_root(self.root)
        object.set_parent(self)
        object.set_path(self.path + list(key))
        # if object.name is None:
        #     object.set_name(self.name)
        if key:
            if self.schema:
                property = Schema.property(self.schema, *key) 
                if property:
                    object.set_schema(property)

        if len(object.path) == 1:
            object.set_root(object)
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
    
    def force_schema(self, *schema, **kwargs):
        from .schemas import Schema
        self.schema = Schema(*schema, **kwargs)
        return self
    def set_schema(self, *schema, **kwargs):
        from .schemas import Schema
        if not self.schema:
            if not kwargs and len(schema) == 1 and isinstance(schema[0], Schema):
                self.schema = schema[0]
            else:
                self.schema = Schema(*schema, **kwargs)
        return self
    
    def modify_schema(self, *schema, **kwargs):
        from .schemas import Schema
        if self.schema:
            self.schema = Schema(*schema, *self.schema.maps, **kwargs)
        else:
            self.set_schema(*schema, **kwargs)
        return self
    
    modify = modify_schema
    
    def errors(self):
        if self.schema:
            from .schemas import Schema
            return Schema.errors(self.schema, self)
        return []
    
    def validate(self, raises=True):
        if self.schema:
            from .schemas import Schema
            Schema(self.schema).validate_object(self, raises=raises)
            return self
        return self
    
    def warn(self):
        try:
            self.validate(raises=True)
        except Exception as e:
            import warnings
            warnings.warn(str(e))
        return self
    
    def infer_schema(self):
        from .schemas import Schema
        self.schema = Schema.infer(self)
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
            if isinstance(self, (collections.ChainMap, dict, list)):
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
        
    # @classmethod
    # def dispatch(cls, value):
    #     from .schemas import Schema
    #     if isinstance(value, (Object, Schema)):
    #         return value
    #     if isinstance(value, (dict,)):
    #         object = Dict(value)
    #         if issubclass(cls, Schema):
    #             return cls(object)
    #         return object
    #     elif isinstance(value, (list, tuple)):
    #         return Array(value)
    #     elif isinstance(value, str):
    #         return String(value)
    #     elif isinstance(value, bool):
    #         return Boolean(value)
    #     elif value is None:
    #         return 
    #     elif isinstance(value, int):
    #         return Integer(value)
    #     elif isinstance(value, float):
    #         return Number(value)
    #     elif isinstance(value, Null):
    #         return value
    #     raise TypeError(f"Unsupported type: {type(value)}")
    dispatcher = dispatch
    
    @classmethod
    def dispatch(cls, value):
        if isinstance(value, cls):
            return value
        return cls.dispatcher(value)

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

class Expanded:
    pass

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
        if object is not None and object is not Expanded:
            # self.reflect(object, key)
            object.set_parent(self)
            if object.root is object:
                object.set_root(self.root)
            object.set_path(self.path + [key])
            if self.schema:
                from .schemas import Schema
                object.schema = Schema.property(self.schema, key)
                # object.schema = Schema.property(self.schema, key, value)
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
        object = dict.fromkeys(self)
        blocked = set()
        # print(object)
        for key in list(object):
            value = self[key]
            # print(key,value, value is Expanded)
            if value is Expanded:
                object.pop(key)
            else:
                object[key] = value.builtin() if hasattr(value, "builtin") else value
                pass
        return object

        return dict(
            (key, value.builtin() if hasattr(value, "builtin") else value) for key, value in self.items()
        )

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
    
class Registry:
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

    @classmethod
    def register_schema(cls, schema, id=None):
        if id is None:
            id = schema.get("$id", None)
        import referencing
        if id in cls.REGISTRY:
            return cls
        cls.REGISTRY = cls.REGISTRY.combine(referencing.Registry({
            id: referencing.Resource.from_contents(schema, Ref.default_specification)
        }))
        return cls
    
    @classmethod
    def crawl(cls):
        cls.REGISTRY.crawl()
        return cls
        

    
class Ref(String, Registry):
    @dataclass
    class Reference:
        contents: dict

    def __enter__(self):
        self._refs = []
        return self
    
    def __exit__(self, exc_type, exc_value, traceback):
        del self._refs
        return False
    
    def resolver(self, root=None):
        import referencing
        from .schemas import Schema
        
        if root is None:
            # the root will usually be passed from an outer scope
            if self.root is not self:
                root = self.root
        if isinstance(root, str):
            # when the root is a string we have a uri referencing a schema and not root yet.
            return Ref.REGISTRY.resolver(self).lookup
        parts = Ref.parse(self)
        if parts.scheme == "file":
            from pathlib import Path
            from toolz import compose_left
            from toolz.curried import flip
            return compose_left(
                flip(str.removeprefix, "file://"), Path, Path.expanduser, Path.read_text, 
                Object.from_string, Ref.Reference)
        elif parts.scheme in ("http", "https"):
            return Ref.retrieve
        elif not parts.scheme and not parts.path and parts.fragment and parts.fragment.startswith("/"):
            resource = referencing.Resource.from_contents(root.builtin(), self.default_specification)
            return (
                referencing._core.Resolver("", referencing._core.Registry().with_resource("", resource).crawl()).lookup
            )
            # refer 
            return referencing._core.Resolver(resource.id(), Schema.Ref.REGISTRY.with_resource(
                resource.id() or "", resource
            ), referencing._core.List([
                # "https://json-schema.org/draft/2020-12/schema",
                "https://deathbeds.github.io/nbref/schema/meta.yaml"
            ])).lookup
        elif self == "#":
            return lambda x: Ref.Reference(self.root)
        
        if isinstance(root, str):
            # when the root is a string we have a uri referencing a schema and not root yet.
            return Ref.REGISTRY.resolver(self).lookup
        # the scoped root is used to deference $ref $dynamicRef in the current schema
        resolver = Ref.REGISTRY.resolver_with_root(referencing.Resource.from_contents(root, self.default_specification))
        resource = referencing.Resource.from_contents(root.builtin(), self.default_specification)
        return referencing._core.Resolver(resource.id(), Schema.Ref.REGISTRY.with_resource(
            resource.id() or "", resource
        ).crawl(), referencing._core.List([
            resource.contents.get("$schema", "https://deathbeds.github.io/nbref/schema/meta.yaml")
        ])).lookup

        return Ref.REGISTRY.resolver_with_root(referencing.Resource.from_contents(root, self.default_specification)).lookup
    
    def resolve(self, root=None):
        # the root is passed by an expansion function
        # it can only make a schema and then only schema can use the
        from .schemas import Schema
        dynamic = self.path[-1] == "$dynamicRef"
        visits = None
        # if not dynamic:
        #     visited = getattr(self.root, "visited_cache", None)
        #     if visited is None:
        #         visited = self.root.visited_cache = dict()
        #     visits = visited.get(str(self))
        if visits is None:
            object = Object.dispatch(Ref.resolver(self, root)(self).contents)
            if len(object.path) == 1:
                object.set_root(object)
            # if self.path[-1] == "$ref":
            #     visits
            # if len(visits.path) == 1 and self.path[-1] == "$ref":
            #     visits.set_root(self.root)
        return object
    def parse(self):
        import urllib.parse
        return urllib.parse.urlparse(str(self))

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

@dispatch.register(Object)
def dispatch_object(value):
    return value
@dispatch.register(dict)
def dispatch_dict(value):
    return Dict(value)

@dispatch.register(list)
@dispatch.register(tuple)
def dispatch_list(value):
    return Array(value)

@dispatch.register(str)
def dispatch_str(value):
    return String(value)

@dispatch.register(bool)
def dispatch_bool(value):
    return Boolean(value)

@dispatch.register(type(None))
def dispatch_none(value):
    return None

@dispatch.register(int)
def dispatch_int(value):
    return Integer(value)

@dispatch.register(float)
def dispatch_float(value):
    return Number(value)
