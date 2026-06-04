from .objects import Object, Dicts, Dict, Boolean, Uri, Ref, Null

import collections
class Core:
    def id(self, *ids):
        return str(self.path + list(ids))
    
    def anchor(self):
        return self.get("$anchor", None)

class Metadata:
    def default(self):
        object = Object.dispatch(Schema._default(self))
        if object is None:
            object = Null()
        object.set_schema(self)
        return object

    def _default(self):
        default = self.get("default")
        if default is not None:
            return default
        type = self.type()
        if "integer" in type:
            return 0
        elif "number" in type:
            return 0.0
        elif "boolean" in type:
            return False
        elif "string" in type:
            return ""
        elif "array" in type:
            return []
        elif "object" in type:
            return {}
        return None
    
    def _default_array(self):
        object = []
        
        return object
        
    def title(self):
        return self.get("title", object.path[-1])
    
    
    def comment(self):
        if isinstance(self, collections.ChainMap):
            return self.all_strings("$comment")
        comment = self.get("$comment")
        if comment:
            return [comment]
        return []
    
    def description(self):
        return self.get("description", "")
    
class Applicator:
    def properties(self):
        return self.all("properties", {})
    
    def additional(self):
        type = self.type()
        if "array" in type:
            return self.get("items", {})
        elif "object" in type:
            return self.get("additionalProperties", {})
        return {}
    
    def property(self, key):
        type = self.type()
        if "object" in type:
            subschema = Schema.property_object(self, key)
        elif "array" in type and isinstance(key, int):
            subschema = Schema.property_array(self, key)
        else:
            subschema = Schema(type=type).set_parent(self).set_root(self.root).set_path(self.path + [key])

        if isinstance(subschema, (bool, Boolean)):
            subschema = subschema.reflect(Schema())

        return subschema
    
    def property_object(self, key):
        properties = self.all("properties", {})
        if key in properties:
            value = properties.all(key, None)
            if value is None:
                value = Schema().set_parent(self).set_root(self.root).set_path(self.path + ["properties", key])
                    
            return Schema.expand(value)
        additional = self.all("additionalProperties", None)
        if additional is None:
            return Schema().set_parent(self).set_root(self.root).set_path(self.path + ["additionalProperties"])
        return additional
    
    def property_array(self, key):
        items = self.get("prefixItems", [])
        if key < len(items):
            return Schema.expand(items[key])
        additional = self.get("items", None)
        if additional is None:
            return Schema().set_parent(self).set_root(self.root).set_path(self.path + ["items"])
        return additional
    
class Validation:
            
    def type(self):
        type = self.get("type")
        if type is not None or isinstance(type, dict):
            return type
        types = set()
        for key in ("allOf", "anyOf", "oneOf"):
            if key in self:
                for subschema in self[key]:
                    types.update(Schema.types(subschema))
        for key in ("properties", "additionalProperties"):
            if key in self:
                types.add("object")

        for key in ("items", "additionalItems"):
            if key in self:
                types.add("array")
        
        return list(types)
    def types(self):
        type = self.type()
        if not isinstance(type, list):
            type = [type]
        return type
    def required(self):



        return self.get("required", [])
    
    
class Expand:
    def expand_subschemas(self, object=None):
        yield from Schema.expand_all_of(self)
        yield from Schema.expand_ref(self)
        if object is not None:
            pass
            # test the object for if then else schema
            # one of or anyof
        
    def expand(self, object=None):
        if isinstance(self, (bool, Boolean)):
            self = self.reflect(Schema())
        
        if isinstance(self, (dict, collections.ChainMap)):
            subschemas = list(Schema.expand_subschemas(self))
            if subschemas:
                if isinstance(self, Schema):
                    return self.extend(
                        x for x in subschemas if x is not self
                    )
                return Schema(*subschemas)
            
        return self

    def expand_all_of(self):
        all = self.get("allOf")
        if all and isinstance(all, (list, tuple)):
            yield self
            for i in range(len(all)):
                yield Schema.expand(all[i])
        return self
    
    def expand_ref(self, dynamic=False):
        for dynamic, key in enumerate(("$ref", "$dynamicRef")):
            ref = self.get(key)
            if ref is not None and isinstance(ref, str):
                # the dynamic and local references have different roots
                # the dynamic reference starts at the root level schema.
                # the local reference refers to the containing document.
                root = self.root if dynamic else ref.root
                object = Ref.resolve(ref, root)

                yield Schema.expand(object)

class Repr:
    def repr(self, type=None):
        if type is None:
            type = self.type()
        return f"{type}({self.id()})"

class Form:
    pass
    
# class Properties:
#     # when working with schema we know the expected behavior of the properties.
#     # this class provides accessors for the properties.

#     def default(self):
#         object = Object.dispatch(Schema._default(self))
#         if object is None:
#             object = Null()
#         object.set_schema(self)
#         return object

#     def title(self):
#         return self.get("title", object.path[-1])
    
    
#     def comment(self):
#         if isinstance(self, collections.ChainMap):
#             return self.all_strings("$comment")
#         comment = self.get("$comment")
#         if comment:
#             return [comment]
#         return []
    
#     def required(self):
#         return self.get("required", [])
    
#     def properties(self):
#         return self.all("properties", {})
    
#     def additional(self):
#         type = self.type()
#         if "array" in type:
#             return self.get("additionalItems", {})
#         elif "object" in type:
#             return self.get("additionalProperties", {})
#         return {}
    
#     def description(self):
#         return self.get("description", "")
    
#     def id(self, *ids):
#         return str(self.path + list(ids))
    
#     def _default(self):
#         default = self.get("default")
#         if default is not None:
#             return default
#         type = self.type()
#         if "integer" in type:
#             return 0
#         elif "number" in type:
#             return 0.0
#         elif "boolean" in type:
#             return False
#         elif "string" in type:
#             return ""
#         elif "array" in type:
#             return []
#         elif "object" in type:
#             return {}
#         return None
        
            
#     def type(self):
#         type = self.get("type")
#         if type is not None or isinstance(type, dict):
#             return type
#         types = set()
#         for key in ("allOf", "anyOf", "oneOf"):
#             if key in self:
#                 for subschema in self[key]:
#                     types.update(Schema.types(subschema))
#         for key in ("properties", "additionalProperties"):
#             if key in self:
#                 types.add("object")

#         for key in ("items", "additionalItems"):
#             if key in self:
#                 types.add("array")
        
#         return list(types)
    
#     def property(self, key):
#         type = self.type()
#         if "object" in type:
#             return Schema.property_object(self, key)
#         elif "array" in type and isinstance(key, int):
#             return Schema.property_array(self, key)
#         return Schema(type=type).set_parent(self).set_root(self.root).set_path(self.path + [key])
    
#     def property_object(self, key):
#         properties = self.all("properties", {})
#         if key in properties:
#             value = properties.all(key, None)
#             if value is None:
#                 value = Schema().set_parent(self).set_root(self.root).set_path(self.path + ["properties", key])
                    
#             return Schema.expand(value)
#         additional = self.all("additionalProperties", None)
#         if additional is None:
#             return Schema().set_parent(self).set_root(self.root).set_path(self.path + ["additionalProperties"])
#         return additional
    
#     def property_array(self, key):
#         items = self.get("prefixItems", [])
#         if key < len(items):
#             return Schema.expand(items[key])
#         additional = self.get("additionalItems", None)
#         if additional is None:
#             return Schema().set_parent(self).set_root(self.root).set_path(self.path + ["additionalItems"])
#         return additional

class Validate:

    def errors(self, object, raises=True):
        import jsonschema
        jsonschema._types.bool = jsonschema._keywords.bool = Boolean
        if isinstance(object, collections.ChainMap):
            return Schema.validator(object.maps[0])
        object = object.builtin() if isinstance(object, Object) else object
        try:
            return list(Schema.validator(self).iter_errors(object)            )
        finally:
            del jsonschema._types.bool, jsonschema._keywords.bool
    
    def validator(self):
        import jsonschema, referencing
        if isinstance(self, collections.ChainMap):
            return Schema.validator(self.maps[0])
        schema = self.builtin() if isinstance(self, Object) else self
        return jsonschema.Draft202012Validator(
            schema,
            resolver=jsonschema.validators.RefResolver.from_schema(self.root, referencing.jsonschema.DRAFT202012.id_of),
        )
        return jsonschema.Draft202012Validator(
            self.builtin() if isinstance(self, Object) else self,
            resolver=jsonschema.validators.RefResolver.from_schema(self.root, referencing.jsonschema.DRAFT202012.id_of),
            registry=Ref.REGISTRY,
            _resolver=Ref.REGISTRY.resolver_with_root(referencing.Resource.from_contents(self.root, referencing.jsonschema.DRAFT202012))
        )

    def validate(self, object, raises=True):
        import jsonschema
        jsonschema._types.bool = Boolean
        if isinstance(object, collections.ChainMap):
            return Schema.validator(self.builtin()).validate(object.maps[0])
        object = object.builtin() if isinstance(object, Object) else object
        try:
            Schema.validator(self).validate(object)
        except () if raises else jsonschema.ValidationError:
            pass
        finally:
            del jsonschema._types.bool
        return self
    
    def validate_schema(self,  raises=True):
        if self.schema:
            return self.schema.validate(self.schema)
        return self
    
    def is_valid(self, schema):
        try:
            Schema.validate(self, schema)
            return True
        except Exception:
            return False
    
class Schema(Core, Metadata, Applicator, Validation, Validate, Expand, Dicts):
    _cached_schemas = {}

    def __init__(self, *maps, **kwargs):
        if kwargs:
            maps += kwargs,
        objects = []
        id = None
        for i, object in enumerate(maps):
            object = self.__init_map(object)
            if isinstance(object, Schema):
                objects.extend(object.maps)
            else:
                objects.append(object)
        if not objects:
            objects.append(Dict())
        # print("super init", super())
        super().__init__(*objects)
        if isinstance(self, (dict, collections.ChainMap)):
            id = self.get("$id")
            if id and "://" in id:
                Schema._cached_schemas[id] = self
            # cant expand in init because the root isnt constructed yet
        if len(self.maps) == 1:
            self.set_parent(self.maps[0].parent).set_root(self.maps[0].root).set_path(self.maps[0].path)
        
    
    
    def __init_map(self, map):
        if map is None:
            return Dict()
        if isinstance(self, Schema) and isinstance(map, str):
            url = Uri.parse(map)
            if url.scheme in ("http", "https"):
                cached = Schema._cached_schemas.get(map)
                if cached is None:
                    return Schema.expand(Ref(map).resolve())
                return cached
        elif isinstance(map, (bool, Boolean)):
            return Dict()
        return self.dispatch(map)

    @classmethod
    def from_objects(cls, *objects):
        import operator
        from .utils import infer_schema

        return cls(Object.dispatch(infer_schema(
            *map(operator.methodcaller("builtin"), map(Object.dispatch, objects))
        )))