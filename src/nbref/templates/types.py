from abc import ABC
import collections
import json
from operator import getitem, methodcaller
import re
from zipfile import Path
from bs4 import Tag
from typing import Generator

from nbref.templates.sf import Schema

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
    elif isinstance(value, list):
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

def dispatch(cls, value):
    if isinstance(value, Object):
        return value
    if isinstance(value, (dict, Dicts)):
        if issubclass(cls, Schema):
            return Schema(value)
        return Dict(value)
    elif isinstance(value, (list, tuple)):
        return Array(value)
    elif isinstance(value, str):
        return String(value)
    elif isinstance(value, bool):
        return Boolean(value)
    elif value is None:
        return Null()
    elif isinstance(value, int):
        return Integer(value)
    elif isinstance(value, float):
        return Number(value)
    raise TypeError(f"Unsupported type: {type(value)}")

class Pointer(list):
    def __add__(self, value):
        return type(self)(super().__add__(value))
    
    def __radd__(self, value):
        return type(self)(super().__add__(value))
    def __str__(self):
        return ':'.join(map(str, self))
    
class HasPath:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.parent = None
        self.root = self
        self.path = Pointer("#")
    
    
    def set_path(self, path):
        self.path = path
        return self
    
    def set_parent(self, parent):
        self.parent = parent
        return self
    
    def set_root(self, root):
        self.root = root
        return self
    
    def set_path(self, path):
        self.path = path
        return self
    
    def set_schema(self, schema):
        if self.schema is None:
            self.schema = Schema()
        if not self.schema:
            self.schema = schema
        else:
            self.schema.add(schema)
        return self
    

class HasSchema:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not hasattr(self, "schema"):
            self.schema = None
    
    def errors(self):
        if self.schema:
            return self.schema.errors(self)
        return []
    

    def validate(self, schema=None):
        schema  = schema or self.schema
        if schema:
            return Schema.validate(schema, self)
        return self
    def validate_schema(self):
        if self.schema:
            if self.schema.schema:
                return self.schema.schema.validate(self.schema)
        return self
    
    def is_valid(self, schema=None):
        try:
            self.validate(schema)
            return True
        except Exception:
            return False
        
    
    def set_schema(self, schema):
        if self.schema is None:
            self.schema = Schema()
        if not self.schema:
            self.schema = schema
        else:
            self.schema.add(schema)
        return self
    
    def enum(self):
        enum = []
        if self.schema:
            enum = self.schema.get("enum", [])
        return dict(zip(enum, enum))

    def type(self):
        if isinstance(self.root, Schema):
            return Schema.schema_type(self)
        if self.schema:
            return self.schema.schema_type(self)
        return python_type_to_schema(self)
    
    def title(self):
        title = None
        if self.schema:
            title = self.schema.get("title")
        if not title:
            title = self.path[-1]
        return title
    
    def description(self):
        description = None
        if self.schema:
            description = self.schema.get("description", None)
        return description
    
    def examples(self):
        examples = []
        if self.schema:
            examples = self.schema.get("examples", [])
        return examples

    def comment(self):
        comment = None
        if self.schema:
            comment = self.schema.get("$comment")
        return comment
    
    def ids(self):
        rel = self.relative_to()
        if rel is self:
            if self._id:
                return Pointer([self._id])
            if isinstance(rel, Schema):
                if "$id" in rel:
                    return Pointer([rel["$id"]])
            
            return Pointer([str(id(self))])
        if len(self.path) == 1:
            return Pointer([self._id or self.schema and self.schema.get("$id", "#") or "#"])
        return self.relative_to().ids() + self.path[1:]
    
    def id(self, *ids):
        return str(self.ids() + list(ids))

class Object(HasSchema, HasPath, ABC):
    def __new__(cls, *args, **kwargs):
        self = super().__new__(cls, *args, **kwargs)
        self.__init__(*args, **kwargs)
        return self.with_default()

    def __init__(self, *args, **kwargs):
        if isinstance(self, (dict, list, collections.ChainMap)):
            super().__init__(*args, **kwargs)
        else:
            super().__init__()
        self._id = None

    def with_default(self):
        if not self:
            if self.schema:
                if "default" in self.schema:
                    return Object.dispatch(self.schema["default"]).set_schema(self.schema).set_parent(self.parent).set_root(self.root).set_path(self.path)
                t = Schema.schema_type(self.schema)
                if "object" in t:
                    object = Dict().set_schema(self.schema).set_parent(self.parent).set_root(self.root).set_path(self.path)
                    for key in self.schema.properties({}):
                        if key not in object:
                            object[key] = Object.from_schema(self.schema.property(key))().set_parent(object).set_root(self.root).set_path(self.path + [key])
                    return object   
                if "array" in t:
                    array = Array().set_schema(self.schema).set_parent(self.parent).set_root(self.root).set_path(self.path)
                    return array
        return self

    def __class_getitem__(cls, item):
        if not isinstance(item, tuple):
            item = item,
        return cls.from_schema(*item)
    
    @classmethod
    def from_schema(cls, *schema, **kwargs):
        schema = Schema(*schema, **kwargs)
        if issubclass(cls, Schema):
            return type(cls.__name__, (cls,), dict(schema=schema))
        target = schema_type_to_path_types(schema.schema_type())
        return type(target.__name__, (target,), dict(schema=schema))

    def set_id(self, id):
        self._id = id
        return self

    def relative_to(self):
        rel = self
        while rel is not None:
            if len(rel.path) == 1:
                return rel
            rel = rel.parent

        return rel
        
    dispatch = classmethod(dispatch)
    def pipe(self, func, *args, **kwargs):
        return func(self, *args, **kwargs)
    
    def pipes(self, *funcs):
        for func in funcs:
            self = func(self)
        return self
    
    def html(self):
        return schema_html(self.schema, self)

class Getter:
    def get(self, key, default=None):
        try:
            return self[key]
        except KeyError:
            if self.schema:
                default = self.schema.get("default", default)
            if default is None:
                return Null().set_parent(self).set_root(self.root).set_path(self.path + [key])
            return default
    def __getitem__(self, key):
        try:
            value = super().__getitem__(key)
            object = self.dispatch(value)
            object.set_parent(self).set_root(self.root).set_path(self.path + [key])
            if self.schema:
                Schema.property(self.schema, key).pipes(Schema.expand, object.set_schema)
        except KeyError as error:
            if self.schema:
                try:
                    subschema = self.schema.property(key)
                except KeyError:
                    raise error
                object = Object.from_schema(subschema)().set_parent(self).set_root(self.root).set_path(self.path + [key]).pipe(Schema.expand)
            else:
                raise error
        if isinstance(self, Dicts):
            if isinstance(object, Dicts):
                object._expanded = self._expanded
        return object

class Dict(Object, Getter, dict):
    def dict(self, all=False):
        if isinstance(self, dict | collections.ChainMap):
            new = dict.fromkeys(self)
            for key in new:
                value = self[key]
                if isinstance(value, (Dict, collections.ChainMap)):
                    value = Dict.dict(value)
                elif isinstance(value, list):
                    value = list(map(Dict.dict, value))
                new[key] = value
            return new
        if isinstance(self, list):
            return list(map(Dict.dict, self))
        return self
    

class Dicts(Object, collections.ChainMap):
    @property
    def top(self):
        return self.maps[0]
    def dict(self, all=False):
        return Dict.dict(self if all else self.top)
    def __init__(self, *maps, **kwargs):
        if kwargs:
            maps += Dict(kwargs),
        super().__init__(*maps)
        
    def add(self, schema):
        self.maps += schema,
        self.maps = list(filter(bool, self.maps)) or [Dict()]
        return self
    
    def extend(self, *schema):
        for s in schema:
            self.add(s)
        return self
    
    def get(self, key, default=UNDEFINED):
        try:
            return self[key]
        except KeyError:
            if default is UNDEFINED:
                return 
            return default
        
    def get_all(self, key):
        object = collections.ChainMap.__getitem__(self, key)
        if isinstance(object, (dict, collections.ChainMap)):
            target = Schema if isinstance(self.root, Schema) else Dicts
            # target = Dicts
            s = target().set_parent(self).set_root(self.root).set_path(self.path + [key])
            for map in self.maps:
                if key in map:
                    s.add(map[key])
            if self.schema:
                s.set_schema(self.schema.property(key).pipe(Schema.expand))
            return s
        elif isinstance(object, list):
            s = Array().set_parent(self).set_root(self.root).set_path(self.path + [key])
            for map in self.maps:
                if key in map:
                    for item in map[key]:
                        if item not in s:
                            s.append(item)
            if self.schema:
                s.set_schema(self.schema.property(key).pipe(Schema.expand))
            return s

        elif isinstance(self.root, Schema) and isinstance(object, str):
            if key in "type":
                s = Array()
                for map in self.maps:
                    if key in map:
                        s.append(map[key])    
                if len(s) == 1:
                    s = s[0]
                s.set_parent(self).set_root(self.root).set_path(self.path + [key])
                if self.schema:
                    s.set_schema(self.schema.property(key).pipe(Schema.expand))
                return s
        object = self.root.dispatch(object)
        if self.schema:
            object.set_schema(self.schema.property(key).pipe(Schema.expand))
        if len(object.path) == 1:
            object.set_parent(self).set_root(self.root).set_path(self.path + [key])
        try:
            return object.unstack()
        except AttributeError:
            return object
        
    __getitem__ = get_all

class Array(Object, Getter, list):
    pass

class Number(Object, float):
    pass    
class Integer(Object, int):
    pass
class Boolean(Integer):
    def __str__(self):
        return "true" if self else "false"
    __repr__ = __str__

class String(Object, str):
    pass
class Null(Object):
    def __str__(self):
        return ""
    
    def __bool__(self):
        return False

class Bunch:
    pass
    # def __getattr__(self, name):
    #     if name.startswith("_"):
    #         name = "$" + name[1:]
    #     try:
    #         return self[name]
    #     except KeyError:
    #         super().__getattribute__(name)

    # def __dir__(self):
    #     return [*self.keys(), *super().__dir__()]

_REGISTRY = dict()

class SchemaValidation:
    def validate(self, data):
        return Schema.validate(self, data)
    
    def errors(self, data):
        return Schema.errors(self, data)

class SchemaOps:
    def lookup(self, ref):
        return self
    
    def expand_ref(self):
        return self
    
    def expand_dynamicRef(self):
        return self
    
    def expand_allof(self):
        return self
    
    def expand_if_then(self):
        return self
    
    def expand_oneof(self):
        return self

    def expand_anyof(self):
        return self
    
    def expand(self):
        self = self.expand_ref()
        self = self.expand_dynamicRef()
        self = self.expand_allof()
        self = self.expand_oneof()
        self = self.expand_anyof()
        self = self.expand_if_then()
        return self

class Schema(Dict):
    REGISTRY = _REGISTRY

class Schemas(Dicts):
    REGISTRY = _REGISTRY
    def __new__(cls, *args, **kwargs):
        if not kwargs:
            if len(args) == 1:
                # this is ineffcient
                if "$schema" in list(args[0]):
                    id = args[0].get("$id", "")
                    if id in Schema.REGISTRY:
                        print("reuse")
                        return Schema.REGISTRY[id]

        self = collections.ChainMap.__new__(cls)
        Object.__init__(self)
        Dicts.__init__(self, *args, **kwargs)
        for i, map in enumerate(self.maps):
            if isinstance(map, bool):
                self.maps[i] = Dict()
        if "$schema" in self:
            id = self.get("$id", "")
            if "://" in id:
                if id in Schema.REGISTRY:
                    return Schema.REGISTRY[id]
                Schema.REGISTRY[id] = self
        return self

    def errors(self, data):
        return list(Schema.validator(self).iter_errors(data))
    
    def to_type(self):
        return Object.from_schema(self)
    
    def new(self, *args, **kwargs):
        return Schema.to_type(self)(*args, **kwargs)
    
    def validator(self):
        import jsonschema
        return jsonschema.Draft202012Validator(self, resolver=Schema.ref_resolver(self.root))
    
    def validate(self, data):
        import jsonschema
        schema = self
        if hasattr(schema, "maps"):
            schema = schema.maps[0]
        Schema.validator(self).validate(Dict.dict(data))
        return data
    
    def unstack(self):
        if self.maps == 1:
            try:
                return self.top.unstack()
            except AttributeError:
                pass
        return self
    
    def required(self):
        return self.get("required", [])
    
    def properties(self, data=None):
        """list the keys based on the object and schema"""
        required = self.required()
        yield from required

        properties = self.get("properties", "")
        for property in properties:
            if property not in required:
                yield property
        if data is not None:
            for key in data:
                if key not in required and key not in properties:
                    yield key

        
    def html(self, data=None):
        if data is None:
            data = self.new()
        return schema_html(self, data)
    def property(self, key):
        t = Schema.schema_type(self)
        if isinstance(key, int) and "array" in t:
            prefixItems = self.get("prefixItems", "")
            if len(prefixItems) > key:
                return prefixItems[key]
            items = self.get("items")
            return items
        properties = self.get("properties", "")
        if key in properties:
            return properties[key]
        patternProperties = self.get("patternProperties", "")
        for pattern in patternProperties:
            if re.match(pattern, key):
                return patternProperties[pattern]
        additionalProperties = self.get("additionalProperties")
        if additionalProperties:
            return additionalProperties
        return Schema()
        raise KeyError(f"Property {key} not found in schema")
    
    def schema_type(self, data=None):
        if "enum" in self:
            return "enum"
        types = self.get("type", [])
        # explicit types
        if not types:
            # implicit types
            keys = list(self)
            for property in ["properties", "additionalProperties"]:
                if property in keys:
                    types.append("object")
                    break
            for property in ["items", "additionalItems"]:
                if property in keys:
                    types.append("array")
                    break
        if not types and data is not None:
            types.append(python_type_to_schema(data))
        if len(types) == 1:
            return types[0]
        return types
            
    def flatten(self):
        target = dict()
        for k in self:
            target[k] = self[k]
        return target
    
    def expand(self):
        # if getattr(self, "_expanded", False):
        #     return self
        if isinstance(self, (dict, collections.ChainMap)):
            self = Schema.expand_ref(self)
            if "allOf" in self:
                self = Schema.expand_allof(self)
            # Schema.expand_objects(self)
        self._expanded = True
        # if self is not self.root:
        #     if len(self.maps) == 1:
        #         return Object.dispatch(*self.maps).set_parent(self.parent).set_root(self.root).set_path(self.path)
        return self

    object_keys = {"properties", "patternProperties"}
    
    def expand_objects(self):
        for key in Schema.object_keys.intersection(self):
            if key in self:
                object = self[key]
                for property in object:
                    Schema.expand(object)

    
    def expand_ref(self):
        keys = set(self)
        if not keys.intersection({"$ref", "$dynamicRef"}):
            return self

        refs = Schema(Dict(self)).set_parent(self).set_root(self.root).set_path(self.path)
        for i, map in enumerate(getattr(self, "maps", [self])):
            if "$ref" in map or '$dynamicRef' in map:
                input = Dict(**map).set_parent(self).set_root(self.root)
                ref = schema_ref(input)
                if isinstance(ref, (dict, collections.ChainMap)):
                    ref.set_root(self.root).set_parent(self).pipes(Schema.expand, refs.add)
                    ref.maps[0].pop("$ref", None)
                    # self.add(subschema.set_parent(self).pipe(Schema.expand))
        if len(refs.maps) > 1:
            refs.maps[0].pop("$ref", None)
            return refs
        return self
    
    def expand_allof(self):
        all_of = self.get("allOf")
        if all_of:
            # all = Dicts().set_parent(self).set_root(self.root).set_path(self.path + ["allOf"])
            all = Schema().set_parent(all_of).set_root(self.root).set_path(self.path + ["allOf"])
            for i in range(len(all_of)):
                all.add(
                    Schema(all_of[i]).set_root(self.root).set_parent(all_of).set_path(self.path + ["allOf", i]).pipe(Schema.expand)
                )
            return all
            self.extend(*all.maps)
        return self
    
    def ref_resolver(self):
        import jsonschema
        return jsonschema.validators._RefResolver.from_schema(Dict.dict(self.top))
    
    def resolver(self):
        import jsonschema_specifications, referencing
        return jsonschema_specifications.REGISTRY.resolver_with_root(
            referencing.Resource.from_contents(self.relative_to(), referencing.jsonschema.DRAFT202012)
        )
    
    def lookup(self, ref, dynamic=False):
        dynamic = "$dynamicRef" in self
        # if not dynamic and "://" not in ref:
        #     ref = "".join(self.relative_to().id().rpartition("/")[:2]) + ref
        cache = self.relative_to().__dict__.setdefault("_lookup_cache", dict())
        if ref in cache:
            contents =  Schema(cache[ref])
            return contents
        else:
            contents = self.resolver().lookup(ref).contents
            if isinstance(contents, bool):
                contents = {}
            contents = Schema(contents).set_parent(self).set_root(self.root).set_schema(self.root)
        cache[ref] = contents
        return contents
    

def schema_ref(schema, data=UNDEFINED):
    import jsonpointer, jsonschema_specifications, referencing

    ref = schema.get("$ref")
    dynamicRef = schema.get("$dynamicRef")

    if isinstance(ref, (dict, collections.ChainMap, type(None))):
        return schema
    if isinstance(ref, list):
        ref = str(jsonpointer.JsonPointer.from_parts(ref))[1:]
    print(ref, dynamicRef)
    resolved = schema.root.lookup(ref or dynamicRef, dynamicRef is not None)
    if dynamicRef:
        return resolved
    if "$id" in resolved:
        del resolved["$id"]
    if "$ref" in resolved:
        del resolved["$ref"]
    if ref.startswith("#/"):
        resolved.set_path(ref.split("/"))
        resolved.set_root(schema.root)
    resolved.set_parent(schema)
    return resolved