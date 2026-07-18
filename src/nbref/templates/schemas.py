from abc import ABC
import collections
from itertools import chain
import json
from operator import getitem, methodcaller
import re
from zipfile import Path
from bs4 import Tag
from typing import Generator
from nbref.templates.rsf import Schema
import referencing, jsonschema_specifications
from .objects import Object, Dict, Dicts, UNDEFINED


def retrieve(uri):
    import requests_cache, requests, referencing
    requests_cache.install_cache("nbref_cache")

    response = requests.get(uri)
    data = requests.get(uri).json()
    return referencing.Resource.from_contents(data)


Object.REGISTRY = REGISTRY = referencing.Registry(
    jsonschema_specifications.REGISTRY._resources,
    jsonschema_specifications.REGISTRY._anchors,
    jsonschema_specifications.REGISTRY._uncrawled,
    retrieve
)

Object.REGISTRY.crawl()
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
    return None
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

class SchemaValidation:

    def errors(self, data):
        return list(Schema.validator(self).iter_errors(data))
    
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
    
class SchemaOps:
    # @classmethod
    # def add_to_registry(cls, uri, contents=None):
    #     if contents is None:
    #         contents = Object.REGISTRY.get_or_retrieve(uri).value
    #     if not isinstance(contents, referencing.Resource):
    #         contents = referencing.Resource.from_contents(contents)

    #     Object.REGISTRY = Object.REGISTRY.with_resources([[uri, contents]]).crawl()
    #     return
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

    def expand_any_one_of(self, key="anyOf"):
        container = self.get(key, None)
        if isinstance(container, list):
            for i in range(len(container)):
                container[i] = Schema.expand(container[i])
            self[key] = container
        return self
    
    def expand_ref(self):
        ref = self.get("$ref")
        if ref:
            yield Schema.expand(Schema.lookup(self, ref))
    
    def expand_dynamicRef(self):
        ref = self.get("$dynamicRef")
        if ref:
            yield Schema.lookup(self, ref, True)

    def expand_allOf(self):
        allOf = self.get("allOf", [])
        if isinstance(allOf, list):
            if allOf:
                yield self
            for i in range(len(allOf)):
                yield Schema.expand(allOf[i])

    def expand(self):
        if isinstance(self, dict):
            schemas = list(chain(Schema.expand_allOf(self), Schema.expand_ref(self), Schema.expand_dynamicRef(self)))
            Schema.expand_any_one_of(self, "anyOf")
            Schema.expand_any_one_of(self, "oneOf")
            if schemas:
                schemas =  Schemas(*schemas).set_root(self.root).set_path(self.path)
                if len(schemas.maps) == 1:
                    return schemas.maps[0]
                return schemas
        return self

    def ref_resolver(self):
        import jsonschema
        return jsonschema.validators._RefResolver.from_schema(Dict.dict(self.top))
    
    def resolver(self):
        import jsonschema_specifications, referencing
        try:
            return Object.REGISTRY.resolver_with_root(
                referencing.Resource.from_contents(
                    Schema.dict(Object.relative_to(self)), referencing.jsonschema.DRAFT202012)
            )   
        except BaseException as e:
            print(Object.relative_to(self))
            raise e
        
    def dict(self):
        from .objects import Boolean, String, Null, Integer, Number
        if isinstance(self, (dict, collections.ChainMap)):
            return {
                k: Schema.dict(v) for k, v in self.items()
            }

        elif isinstance(self, list):
            return list(map(Schema.dict, self))
        elif isinstance(self, Boolean):
            return bool(self)
        elif isinstance(self, String):
            return str(self)
        elif isinstance(self, Null):    
            return None
        elif isinstance(self, Integer):
            return int(self)
        elif isinstance(self, Number):
            return float(self)
        return self
    
    def lookup(self, ref, dynamic=False):
        longref = ref
        if not dynamic and "://" not in ref:
            longref = "".join(self.relative_to().id().rpartition("/")[:2]) + ref
        cache = self.relative_to().__dict__.setdefault("_lookup_cache", dict())
        if ref in cache:
            contents =  Schema(cache[ref])
            return contents
        print("lookup", ref, longref)#, Schema.relative_to(self))
        # print("----", Schema.relative_to(self))
        contents = Schema.resolver(self).lookup(longref).contents
        if isinstance(contents, bool):
            contents = {}
        
        contents = Schema(contents).set_root(self.root)
        if not dynamic and "://" not in ref:
            contents = contents.set_path(ref.split("/"))
        cache[ref] = contents
        return contents
        
    
    def schema_type(self, data=None):
        from .objects import Boolean, String, Null, Integer, Number

        if isinstance(self, (bool, Boolean)):
            self = dict()
        if "enum" in self:
            return "enum"
        types = self.get("type", [])
        if isinstance(types, Null):
            types = []
        elif isinstance(types, str):
            types = [types]

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


class Schema(SchemaOps, Dict):
    pass

class Schemas(SchemaOps, Dicts):
    
    def __new__(cls, *args, **kwargs):
        # if not kwargs:
        #     if len(args) == 1:
        #         # this is ineffcient
        #         if "$schema" in list(args[0]):
        #             id = args[0].get("$id", "")
        #             if id in Schema.REGISTRY:
        #                 print("reuse")
        #                 return Schema.REGISTRY[id]

        self = collections.ChainMap.__new__(cls)
        Object.__init__(self)
        Dicts.__init__(self, *args, **kwargs)
        # for i, map in enumerate(self.maps):
        #     if isinstance(map, bool):
        #         self.maps[i] = Dict()
        # if "$schema" in self:
        #     id = self.get("$id", "")
        #     if "://" in id:
        #         if id in Schema.REGISTRY:
        #             return Schema.REGISTRY[id]
        #         Schema.REGISTRY[id] = self
        return self
    
    def to_type(self):
        return Object.from_schema(self)
    
    def new(self, *args, **kwargs):
        return Schema.to_type(self)(*args, **kwargs)
    
    def unstack(self):
        if self.maps == 1:
            try:
                return self.top.unstack()
            except AttributeError:
                pass
        return self
    
    def required(self):
        return self.get("required", [])

    def flatten(self):
        target = dict()
        for k in self:
            target[k] = self[k]
        return target



    # def get_all(self, key):
    #     from .schemas import Schema, Schemas
    #     object = collections.ChainMap.__getitem__(self, key)
    #     if isinstance(object, (dict, collections.ChainMap)):
    #         target = Schema if isinstance(self.root, Schema) else Dicts
    #         # target = Dicts
    #         maps = []
    #         for map in getattr(self, "maps", [self]):
    #             if key in map:
    #                 maps.append(map[key])
    #         if len(maps) == 1:
    #             s = maps[0].set_parent(self).set_root(self.root).set_path(self.path + [key])
    #         else:
    #             s = Schemas(*maps).set_parent(self).set_root(self.root).set_path(self.path + [key])

    #         if self.schema:
    #             s.set_schema(self.schema.property(key).pipe(Schema.expand))
    #         return s
    #     elif isinstance(object, list):
    #         s = Array().set_parent(self).set_root(self.root).set_path(self.path + [key])
    #         for map in self.maps:
    #             if key in map:
    #                 for item in map[key]:
    #                     if item not in s:
    #                         s.append(item)
    #         if self.schema:
    #             s.set_schema(self.schema.property(key).pipe(Schema.expand))
    #         return s

    #     elif isinstance(self.root, Schema) and isinstance(object, str):
    #         if key in "type":
    #             s = Array()
    #             for map in self.maps:
    #                 if key in map:
    #                     s.append(map[key])    
    #             if len(s) == 1:
    #                 s = s[0]
    #             s.set_parent(self).set_root(self.root).set_path(self.path + [key])
    #             if self.schema:
    #                 s.set_schema(self.schema.property(key).pipe(Schema.expand))
    #             return s
    #     object = self.root.dispatch(object)
    #     if self.schema:
    #         object.set_schema(self.schema.property(key).pipe(Schema.expand))
    #     if len(object.path) == 1:
    #         object.set_parent(self).set_root(self.root).set_path(self.path + [key])
    #     try:
    #         return object.unstack()
    #     except AttributeError:
    #         return object
