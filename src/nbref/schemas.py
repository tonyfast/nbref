from .exceptions import ValidationError
from .objects import Expanded, HasPath, Object, Dict, Boolean, Uri, Ref, dispatch, Array, HasSchema, Expanded

import collections
# create separate classes for all the facets of the 2020-12 json meta schema.
# there are core, metadata, applicator, validation, content, format aspects.
class Core:
    ref = "https://json-schema.org/draft/2020-12/meta/core"
    def id(self, *ids):
        anchor = self.get("$anchor", None)
        return str(self.path + list(ids))
    
    def anchor(self):
        return self.get("$anchor", None)

class Metadata:
    ref = "https://json-schema.org/draft/2020-12/meta/meta-data"

    def examples(self, index=None):
        return self.get("examples", [])
        
    def example(self, index=None):
        if index is None:
            return self.default()
        index = index or 0
        return self.examples()[index]

    def default(self):
        object = Object.dispatch(Schema._default(self))
        if object is None:
            return object
        object.schema = self
        return object
    
    def required(self):
        return self.get("required", [])
    
    def prefix_items(self):
        return self.get("prefixItems", [])
    
    def _default(self):
        default = self.get("default")
        if default is None:
            for example in self.get("examples", []):
                default = example
                break
        if default is not None:
            default = default.builtin()
            
            return Object.dispatch(default).set_schema(self)
        type = Schema.type(self)
        if "integer" in type:
            return 0
        elif "number" in type:
            return 0.0
        elif "boolean" in type:
            return False
        elif "string" in type:
            return ""
        elif "array" in type:
            return [
                Schema.default(sub) for sub in self.prefix_items()
            ]
        elif "object" in type:
            object = dict.fromkeys(Schema.required(self), None)
            for property, subschema in Schema.properties(self).items():
                value = Schema.default(subschema)
                if value is not None:
                    object[property] = value
            return object
        return None
    
    def _default_array(self):
        object = []
        
        return object
        
    def title(self):
        return str(self.get("title", self.path[-1]))
    
    
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
    ref = "https://json-schema.org/draft/2020-12/meta/applicator"

    def properties(self):
        return self.get("properties") or {}
    
    def additional(self):
        type = self.type()
        if "array" in type:
            return self.get("items", {})
        elif "object" in type:
            return self.get("additionalProperties", {})
        return {}
    
    def columns(self, object):
        required = Schema.required(self)
        properties = Schema.properties(self)
        for key in required:
            subschema = Schema.property(self, key)
            value = None
            if isinstance(object, (dict, collections.ChainMap)):
                value = object.get(key)    
            if value is None:
                value = Schema.default(subschema)
                if value is not None:
                    value = object.reflect(value, key)
            if value is None:
                value = object.reflect(Schema.Null(), key)
            yield subschema.reflect(Schema(value.schema, tags=["required"])), value

        for key, subschema in properties.items():
            if key in required:
                continue
            if key not in object:
                continue
            value = None
            if isinstance(object, (dict, collections.ChainMap)):
                value = object.get(key)
            if value is None:
                value = Schema.default(subschema)
            if value is None:
                value = self.reflect(Schema.Null(), key)
            yield subschema.reflect(Schema(value.schema)), value
        
        if isinstance(object, (dict, collections.ChainMap)):
            for key in object:
                subschema = Schema.property(self, key)
                if key in required or key in properties:
                    continue
                value = object[key]
                if value is None:
                    value = self.reflect(Schema.Null(), key)
                yield subschema.reflect(Schema(value.schema or subschema, tags=["additional"])), value

    def property(self, key, expand=True):
        type = self.type()
        if "object" in type:
            subschema = Schema.property_object(self, key, expand)
        elif "array" in type and isinstance(key, int):
            subschema = Schema.property_array(self, key, expand)
        else:
            subschema = Schema(type=type).set_parent(self).set_root(self.root).set_path(self.path + [key])

        if isinstance(subschema, (bool, Boolean)):
            subschema = subschema.reflect(Schema())

        if self.schema:
            subschema.set_schema(self.schema.root)

        return subschema
    
    def property_object(self, key, expand=True):
        properties = self.all("properties", {})
        if key in properties:
            value = Dicts.all(properties, key, None, expand=expand)
            if value is None:
                value = Schema().set_parent(self).set_root(self.root).set_path(self.path + ["properties", key])
            if expand:
                return Schema.expand(value)
            return value
        additional = self.all("additionalProperties", None, expand=expand)
        if additional is None:
            return Schema().set_parent(self).set_root(self.root).set_path(self.path + ["additionalProperties"])
        return additional
    
    def property_array(self, key, expand=True):
        items = self.get("prefixItems", [])
        if key < len(items):
            if expand:
                return Schema.expand(items[key])
            return items[key]
        additional = self.get("items", None)
        if additional is None:
            return Schema().set_parent(self).set_root(self.root).set_path(self.path + ["items"])
        return additional
    
class Validation:
    ref = "https://json-schema.org/draft/2020-12/meta/validation"
            
    def type(self):
        try:
            type = self.__getitem_native__("type")
        except KeyError:
            type = None
        if type is Expanded:
            type = None
        if type is not None or isinstance(type, dict):
            if isinstance(type, (list, tuple)):
                if len(type) == 1:
                    type = type[0]
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
        if "enum" in self:
            if not types:
                types.add("string")
        # get the types from an applicator
        types = list(types)
        if len(types) == 1:
            return types[0]
        return list(types)
    
    def types(self):
        type = Schema.type(self)
        if not isinstance(type, list):
            type = [type]
        return type
        
    def required(self):
        return self.get("required", [])
    
# expansion/compaction are subclasses of Applicator
class Expand:
    def expand_if_then_else(self, object=None):
        oneOf = []
        subschema  = Schema(**{
            "if": Expanded,
            "then": Expanded,
            "else": Expanded,
        })
        i, t, e = self.get("if"), self.get("then"), self.get("else")
        if all(x is not None and x is not Expanded for x in (i, t, e)):
            oneOf.append(Schema(i, t))
            oneOf.append(e)
            subschema.append(oneOf=oneOf)
        # if i is not None:
        #     if_then = Schema({"if": Expanded}, i)
        #     if t is not None:
        #         if_then.append({"then": Expanded})
        #         if_then.append(t)
        #     if e is not None:
        #         if_then.append({"else": Expanded})
        #         oneOf.append(e)
        # yield oneOf
            yield subschema
        yield from ()
    def expand_subschemas(self, object=None):
        yield from Schema.expand_all_of(self)
        yield from Schema.expand_if_then_else(self)
        yield from Schema.expand_ref(self)
        if object is not None:
            pass
            # test the object for if then else schema
            # one of or anyof
        
    def expand(self, object=None):
        prior = self
        is_root = self is self.root
        if getattr(self, "_schema_expanded", False):
            if object is None:
                return self
        else:
            if isinstance(self, (bool, Boolean)):
                self = prior.reflect(Schema())
            
            if isinstance(self, (dict, collections.ChainMap)):
                self = Schema.expand_type_array(self)
                # if is_root:
                #     self.root = self
                subschemas = list(Schema.expand_subschemas(self))
                if subschemas:
                    if isinstance(self, Schema):
                        self = Schema(*subschemas, *self.maps)
                        # return self
                        # return self.extend(
                        #     x for x in subschemas if x is not self
                        # )
                    else: 
                        self = Schema(*subschemas)
                if is_root:
                    self.root = self

            
                self._schema_expanded = True
                
        if object is not None:
            subschema = Schema.expand_one_of(self, object)
            return subschema

        return self

    def expand_all_of(self):
        all = self.get("allOf")
        if all and isinstance(all, (list, tuple)):
            yield self
            for i in range(len(all)):
                yield Schema.expand(all[i])
        return self
    
    def expand_one_of(self, object=None):
        oneOf = self.get("oneOf")
        if oneOf and isinstance(oneOf, (list, tuple)):
            if object is None:
                for subschema in oneOf:   
                    Schema.expand(subschema)
                return
            # for subschema in oneOf:
            #     try:
            #         Schema(subschema).validate_object(object)
            #         return Schema(subschema).expand().append(oneOf=Expanded).append(self)
            #     except ValidationError:
            #         continue
            # else:
            #     return self.append({"not": object.infer_schema().schema})
        # elif object is not None:
        #     try:
        #         Schema.validate_object(self, object)
        #     except ValidationError:
        #         return self.append({"not": object.infer_schema().schema})
        return self

    def expand_type_array(self):
        type = self.get("type")
        if type and isinstance(type, (list, tuple)):
            try:
                bool = type.index("boolean")
                type.pop(bool)
            except ValueError:
                pass
            if not isinstance(self, Schema):
                self = Schema(self)
            if len(type) > 1:
                # override type
                if not isinstance(self, Schema):
                    self = Schema(self)
                self.insert(0, type=Expanded, oneOf=[
                    dict(type=t) for t in type
                ])
                # return self.reflect(Schema(oneOf=[
                #     Schema(self, type=t) for t in type
                # ]))
            else:
                self.insert(0, type=type[0])
        return self
        
    
    def expand_ref(self, dynamic=False):
        for dynamic, key in enumerate(("$ref", "$dynamicRef")):
            ref = self.get(key)
            
            if isinstance(ref, str):
                # if "$ref" == key:
                #     visited = getattr(self.root, "visited_cache", None)
                #     if visited is None:
                #         visited = self.root.visited_cache = dict()
                #     if ref in visited:
                #         yield visited[ref]
                #         continue
                # the dynamic and local references have different roots
                # the dynamic reference starts at the root level schema.
                # the local reference refers to the containing document.
                root = self.root # if dynamic else ref.root
                yield Schema(**{key: Expanded})
                yield self
                subschema = Ref.resolve(ref, root)
                yield Schema.expand(subschema)

class Repr:
    def repr(self, type=None):
        if type is None:
            type = self.type()
        return f"{type}({self.id()})"

class Form:
    pass

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
        # if isinstance(self, collections.ChainMap):
        #     return Schema.validator(self.maps[0])
        schema = self.builtin() if isinstance(self, Object) else self
        # return jsonschema.Draft202012Validator(
        #     schema,
        #     resolver=jsonschema.validators.RefResolver.from_schema(self.root.builtin(), referencing.jsonschema.DRAFT202012.id_of),
        # )
        return jsonschema.Draft202012Validator(
            self.builtin() if isinstance(self, Object) else self,
            resolver=jsonschema.validators.RefResolver.from_schema(self.root.builtin(), referencing.jsonschema.DRAFT202012.id_of),
            registry=Ref.REGISTRY,
            _resolver=Ref.REGISTRY.resolver_with_root(referencing.Resource.from_contents(self.root, referencing.jsonschema.DRAFT202012))
        )
    
    def xfail(self, object):
        try:
            Schema.validate(self, object)
        except ValidationError:
            return self
        raise ValidationError("Expected validation to fail, but it passed", instance=object, schema=self)

    def validate_object(self, object, raises=True):
        import jsonschema
        jsonschema._types.bool = Boolean
        if isinstance(object, collections.ChainMap):
            return Schema.validator(self).validate(object.maps[0])
        object = object.builtin() if isinstance(object, Object) else object
        try:
            Schema.validator(self).validate(object)
        except () if raises else ValidationError:
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
            Schema.validate_object(self, schema)
            return True
        except Exception:
            return False
        
# testing is an extension of validation as expansion is an extension of applicator.
class Testing:
    def strategy(self):
        """generate a testing strategy for this schema using hypothesis_jsonschema"""
        strategy = getattr(self, "_strategy", None)
        if strategy is None:
            import hypothesis_jsonschema
            strategy = self._strategy = hypothesis_jsonschema.from_schema(self.builtin())
        return strategy
    
    def given_py(self):
        """a decorator for hypothesis given, using the strategy for this schema"""
        from hypothesis import given
        return given(self.strategy())
    
    def given(self):
        """a decorator for hypothesis given, using the strategy for this schema"""
        from hypothesis import given
        decorator = given(self.strategy().map(
            lambda x: Object.dispatch(x).set_schema(self)
        ))
        if "maxExamples" in self:
            from hypothesis import settings
            from toolz import compose_left
            return compose_left(decorator, settings(max_examples=self["maxExamples"]))
        return decorator
    
    def random(self):
        """generate a random example of this schema"""

        return dispatch(self.strategy().example()).set_schema(self)
    
    def object(self):
        """create an object from the first default or example of this schema
        
        use example to generate specific objects"""
        return self.example()
    
    def instance(self, object):
        """create an instance of this schema from the given object, validating it and filling in defaults"""
        return Object.dispatch(object).set_schema(self)
    
    
    
    
class Ops:
    def __invert__(self):
        # not is a reserved word and this sugar makes it easier to invert schema.
        return Schema({"not": self})
    
    def __add__(self, other):
        # this sugar makes it easier to combine schemas with allOf
        return self.append(other)
    
    # def __sub__(self, other):
    #     # excise things from a schema
    #     pass
    
    def __call__(self, object=None, **kwargs):
        """validate the given object against this schema, and return the object with defaults filled in"""
        if object is None:
            if kwargs:
                object = kwargs
            else:
                object = self.default()
        out = self.instance(object)
        if out is None:
            return out
        out.schema = self
        return out
    
class Dicts(Object, collections.ChainMap):
    python_type = dict

    def __init_map(self, map):
        return Object.dispatch(map)

    def builtin(self) -> dict:
        """an builtin python dict that merges the content as this object, but without the path and schema information."""
        object = dict()
        blocked = list()
        for map in self.maps:
            for key, value in map.items():
                if value is Expanded:
                    blocked.append(key)
                if key in blocked:
                    continue
                elif key in object:
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
    
    
    def all(self, key, default=BaseException, expand=True):
        # in theory only schemas should be chainmaps.
        from .schemas import Schema

        if isinstance(self, collections.ChainMap):
            try:
                object = collections.ChainMap.__getitem__(self, key)
            except () if default is BaseException else KeyError:
                return default
            if isinstance(object, (dict, collections.ChainMap)):
                # object = self.reflect(self.all_dicts(key), key)
                object = self.all_dicts(key, expand=expand).set_parent(self).set_path(self.path + [key])
        else:
            try:
                object = self[key]
            except () if default is BaseException else KeyError:
                return default
            
            # if not isinstance(object, Schema):
                # why is this here? i think schemas are the only thing that make sense to have a dictionary mapping.
                # this wont be consistent more generally.
            # self.reflect(object, key)
            object = Schema(object).set_root(self.root).set_parent(self).set_path(self.path + [key])

        if self.schema and object is not None:
            object.schema = Schema.property(self.schema, key)
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

    def all_dicts(self, key, expand=True):
        from .schemas import Schema
        values = []
        for i in range(len(self.maps)):
            map = self.maps[i]
            if key in map:
                # agtain this assumes taht only schemas can be chained maps.
                value = map[key]
                if isinstance(value, (dict, collections.ChainMap)):
                    if expand:
                        expanded = self.reflect(Schema(value), key).expand()
                        if len(expanded.maps) == 1:
                            values.append(value)
                        else:
                            values.extend(expanded.maps)
                    else:
                        values.append(value)
        # if len(values) == 1:
        #     return values[0]
        return self.reflect(Schema(*values), key)
    
    __truediv__ = all

    def __getitem__(self, key):
        if isinstance(key, tuple):
            object = self
            for k in key:
                object = object[k]
            return object
        return self.all(key)

    def insert(self, id, *schema, **kwargs):
        self.maps = Schema(*schema, **kwargs).set_parent(self).maps + self.maps
        return self

    def append(self, *schema, **kwargs):   
        self.maps += Schema(*schema, **kwargs).maps
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
        
    def __getitem_native__(self, key):
        for map in self.maps:
            try:
                return map.__getitem_native__(key)
            except KeyError:
                continue
        raise KeyError(key)
        
    # def dumps(self):
    #     return Object.dumps(self.builtin())
    
    
class Schema(Core, Metadata, Applicator, Validation, Validate, Expand, Testing, Ops, Dicts):
    """a schema is a collection of mappings describing a type space.
    
    the schema object can expand and compact the representations"""
    Dicts = Dicts
    _cached_schemas = {}

    def get(self, key, default=None):
        object = super().get(key, default)
        if key == "$ref" and isinstance(object, str) and isinstance(self.root, Schema):
            return object.reflect(Ref(object))
        return object

    def __init__(self, *maps, **kwargs):
        HasSchema.__init__(self)
        if maps:
            if isinstance(maps[0], Object):
                maps[0].reflect(self)
        if kwargs:
            # kwargs are hard overrides
            maps = (kwargs,) + maps
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
            id = collections.ChainMap.get(self, "$id")
            if id and "://" in id:
                Schema._cached_schemas[id] = self
            # cant expand in init because the root isnt constructed yet
        # if len(self.maps) == 1:
        #     # self.set_parent(self.maps[0].parent).set_root(self.maps[0].root).set_path(self.maps[0].path)
        #     self.maps[0].reflect(self)
        
        # if not isinstance(self.root, Schema):
        #     self.root = self
    
    def __init_map(self, map: object) -> Object:
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
        return dispatch(map)

    @classmethod
    def infer(cls, *objects: Object) -> "Schema":
        """infer the schema from a collection of given objects"""
        import operator
        from .utils import infer_schema

        return cls(Object.dispatch(infer_schema(
            *map(operator.methodcaller("builtin"), map(Object.dispatch, objects))
        )))
    
    @classmethod
    def from_file(cls, file, format=None):
        return Schema.expand(super().from_file(file, format=format))

    @classmethod
    def dispatch(cls, value):
        from .objects import dispatch
        return cls(
            dispatch(value)
        )
    
    from .objects import Object, Dict, Boolean, Uri, Ref, Array, Null, String

    # def role(self, widget=True, section=True):
    #     role = self.get("role")
    #     if role is None:
    #         if widget:
    #             role = Schema.role_widget(self)
    #         if role is None and section:
    #             role = Schema.role_section(self)
    #     return role

    # def role_widget(self):
    #     """return the aria role for this schema"""
    #     from .roles import aria_widget_role
    #     return aria_widget_role(self)
    
    # def role_section(self):
    #     """return the aria role for this schema"""
    #     from .roles import aria_section_role
    #     return aria_section_role(self)
    
    # def role_landmark(self):
    #     """return the aria role for this schema"""
    #     from .roles import aria_landmark_role
    #     return aria_landmark_role(self)
        
from .objects import dispatch, dispatch_object
Object.dispatcher.register(Schema)(dispatch_object)

class Meta(Schema):
    def __call__(self, *schema, **kwargs):
        return Schema(*schema, **kwargs).set_schema(self)
        return Schema[self](*schema, **kwargs)
        
Schema.Meta = Meta
Schema.Schema = Schema
