from nbref.templates.schema_forms import Schema
from nbref.utils import infer_schema

from .exceptions import ValidationError
from .objects import Expanded, HasPath, Object, Dict, Boolean, Uri, Ref, dispatch, Array, HasSchema, Expanded
import collections
# create separate classes for all the facets of the 2020-12 json meta schema.
# there are core, metadata, applicator, validation, content, format aspects.
EMPTY = object()
class Core:
    ref = "https://json-schema.org/draft/2020-12/meta/core"
    def id(self, *ids):
        
        path = self.path
        # print(1,path)
        if path and path[0] == "#":
            path[0] = self.root.get("@id") or getattr(self.root, "name", None) or path[0]
        return str(self.path + list(ids))
    
    def anchor(self):
        return self.get("$anchor", None)

class Metadata:
    ref = "https://json-schema.org/draft/2020-12/meta/meta-data"

    def examples(self):
        """return the examples for this schema"""
        return self.get("examples", [])
        
    def example(self, index=None):
        if index is None:
            return Schema.default(self)
        index = index or 0
        return Schema.examples(self)[index]

    def required(self):
        """return the required properties for this schema"""
        return self.get("required", [])
    
    def prefix_items(self):
        """return the prefix items for this schema"""
        return self.get("prefixItems", [])
    
    def default(self):
        """return a default for this schema from default or examples"""
        # object = Schema._default(self)
        object = Object.dispatch(Schema._default(self))
        # if object is None:
        #     return object
        # object.schema = self
        return object
    
    def _default(self):
        default = self.get("default")
        if default is Schema.Expanded:
            default = None
        
        if default is None:
            for example in self.get("examples", []):
                default = example
                break
        if default is not None:
            return default
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
                Schema.default(sub) for sub in Schema.prefix_items(self)
            ]
        elif "object" in type:
            object = dict.fromkeys(Schema.required(self), None)
            for property, subschema in Schema.properties(self).items():
                value = Schema.default(subschema)
                if value is not None:
                    object[property] = value
            return object
        return None
        
    def title(self, default=""):
        """return the title for this schema"""
        if hasattr(self, "path"):
            default = self.path[-1]
        return str(self.get("title", default))
    
    
    def comment(self):
        """return the comment for this schema"""
        if isinstance(self, collections.ChainMap):
            return self.all_strings("$comment")
        comment = self.get("$comment")
        if comment:
            return [comment]
        return []
    
    def description(self):
        """return the description for this schema"""
        return self.get("description", "")
    
class Applicator:
    ref = "https://json-schema.org/draft/2020-12/meta/applicator"

    def properties(self):
        """return the properties for this schema"""
        return self.get("properties", {})
    
    def additional(self):
        """return the additionalProperties for this schema"""
        type = self.type()
        if "array" in type:
            return self.get("items", {})
        elif "object" in type:
            return self.get("additionalProperties", {})
        return {}

    def property_order(self):
        required = Schema.required(self)
        # properties = Schema.properties(self)
        yield from required

        # for key in properties:
        #     if key not in required:
        #         yield key

        default = self.get("default", {})
        if isinstance(default, (dict, collections.ChainMap)):
            for key in default:
                if key not in required:# and key not in properties:
                    yield key

    def columns(self, object):
        """return the columns ordered for this schema."""
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
        """return the subschema for the given property key"""
        type = Schema.type(self)
        if "object" in type:
            subschema = Schema.property_object(self, key, expand)
        elif "array" in type and isinstance(key, int):
            subschema = Schema.property_array(self, key, expand)
        elif type:
            subschema = self.reflect(Schema(type=type), key)
        else:
            subschema = self.reflect(Schema(), key)

        if isinstance(subschema, (bool, Boolean)):
            subschema = subschema.reflect(Schema())

        # parent = Schema.default(self)
        # if parent is not None:
        #     if isinstance(parent, (dict, collections.ChainMap)):
        #         if key in parent:
        #             default = parent.get(key)
        #             subschema = subschema.reflect(Schema(subschema, default=default))
        #     elif isinstance(parent, (list, tuple, str)) and isinstance(key, (int, slice)):
        #         default = parent[key]
        #         if default is not None:
        #             subschema = subschema.reflect(Schema(subschema, default=default))

        if self.schema:
            subschema.set_schema(self.schema.root)

        return subschema
    
    def property_object(self, key, expand=True):
        """return the subschema for the given property key of an object"""
        getter = self.all if isinstance(self, collections.ChainMap) else self.get
        properties = getter("properties", {})
        value = Schema.default(self)
        if key in properties:
            subschema = Dicts.all(properties, key, None, expand=expand)
            if subschema is None:
                subschema = self.reflect(Schema(), "properties", key)
            # if expand:
            #     return Schema.expand(subschema, value.get(key))
            #     return Schema.expand(subschema, value.get(key))
            # return subschema
        else:
            subschema = getter("additionalProperties", None)
            if subschema is None:
                subschema = self.reflect(Schema(), "additionalProperties")
        id = Schema.id(value, key)
        if expand:
            subschema = Schema.expand(subschema, value.get(key))
        # return subschema
        return subschema.reflect(Schema(subschema).append(Schema.property_ld(self, subschema, key, value)))
    
    def property_array(self, key, expand=True):
        """return the subschema for the given property key of an array"""
        # print(22, self.path)
        value = Schema.default(self)    
        items = self.get("prefixItems", [])
        if key < len(items):
            subschema = items[key]
        else:
            subschema = self.get("items", None)
            if subschema is None:
                subschema = Schema().set_path(self.path + ["items", key])
        if expand:
            subschema = Schema.expand(subschema, value[key])

        return subschema.reflect(Schema(subschema).append(Schema.property_ld(self, subschema, key, value)))
            
        # print(self)
        additional = self.get("items", None)
        if additional is None:
            additional = Schema().set_parent(self).set_root(self.root).set_path(self.path + ["items"])
        return Schema.expand(additional, parent[key])

    def property_ld(self, subschema, key, value):
        id = Schema.id(value, key)
        t = Schema.id(subschema)
        if t.startswith(("#:",)):
            root = Schema.id(self.root).partition(":")[0]
            # t = t[1:]
        return {"@id": id, "@type": t}
    
class Validation:
    ref = "https://json-schema.org/draft/2020-12/meta/validation"
            
    def type(self):
        """determine the type of this schema, or the types if it is a union"""
        try:
            if isinstance(self, Object):
                type = self.__getitem_native__("type")
            else:
                type = self["type"]
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

        for key in ("items", "prefixItems"):
            if key in self:
                types.add("array")
        if "enum" in self:
            if not types:
                types.add("string")
        # get the types from an applicator
        types = list(types)
        if not types:
            if "default" in self:
                types.append(Schema.infer(Schema.default(self))["type"])
        if len(types) == 1:
            return types[0]
        return list(types)
    
    def types(self):
        """return the types of this schema as a list"""
        type = Schema.type(self)
        if not isinstance(type, list):
            type = [type]
        return type
        
    def required(self):
        """return the required properties for this schema"""
        return self.get("required", [])
    
# expansion/compaction are subclasses of Applicator
# the bread and butter of this library are the schema
# expansions that make it possible to disambiguate schema, and make it
# easier to generate forms and validate objects. 
# the expansion applies the applicator meta-schema and type from the validation meta-schema.

# $ref equivalency
# type equivalency
# oneOf equivalency
# allOf equivalency
# if then equivalency
# default equivalency
from exceptiongroup import ExceptionGroup
class ValidationErrors(ExceptionGroup):
    pass
class Expand:
    def expand_subschemas(self, object=EMPTY, no_default=False):
        """expand the independent and dependent schema"""
        if not no_default:
            yield from Schema.expand_default(self, object)

        if not getattr(self, "_schema_expanded", False):
            # expand object independent schema
            yield from Schema.expand_all_of(self)
            # ref is equivalent to allOf in how it merges with schema
            yield from Schema.expand_ref(self)
            # yield from Schema.expand_role(self)
            
        if object is not EMPTY:
            # expand object dependent schema
            yield from Schema.expand_if_then_else(self, object)
            yield from Schema.expand_one_of(self, object)
            # this is a good place to expand linked data.
            yield self

        # if not getattr(self, "_schema_expanded", False):
        #             yield from Schema.expand_role(self)
        
    def expand(self, object=EMPTY, no_default=False):
        prior = self
        is_root = self is self.root
        if getattr(self, "_schema_expanded", False) and object is EMPTY:
            return self
        if isinstance(self, (bool, Boolean)):
            self = prior.reflect(Schema())
            if not self:
                self = ~self
        
        if isinstance(self, (dict, collections.ChainMap)):
            self = Schema.expand_type_array(self)
            # if is_root:
            #     self.root = self
            subschemas = list(Schema.expand_subschemas(self, object, no_default=no_default))
            if subschemas:
                # if isinstance(self, Schema):
                if len(subschemas) == 1:
                    self = subschemas[0]
                else:
                    # if is_root and object is None:
                    if is_root and object is EMPTY:
                        self = self.reflect(Schema(*subschemas, *getattr(self, "maps", [self])))
                        # self = self.reflect(Schema(*subschemas, self))
                        # self = Schema(*subschemas)
                        # return self
                        # return self.extend(
                        #     x for x in subschemas if x is not self
                        # )
                    else:
                        self = self.reflect(Schema(*subschemas, self))
            if is_root:
                self.root = self

        
            self._schema_expanded = True
                
        # if object is not None:
        #     subschema = Schema.expand_one_of(self, object)
        #     return subschema
        if isinstance(self, collections.ChainMap):
            if len(self.maps) == 1:
                self.maps[0]._schema_expanded = True
                return self.maps[0]

        return self

    def expand_default(self, object=EMPTY):
        if object is not EMPTY and object is not None:
            yield self.reflect(Schema.Dict(default=object))

    def expand_all_of(self):
        all = self.get("allOf")
        if all and isinstance(all, (list, tuple)):
            yield self
            for i in range(len(all)):
                yield Schema.expand(all[i])
        return self
    
    def expand_ref(self):
        """expand the $ref and $dynamicRef for this schema"""
        for dynamic, key in enumerate(("$ref", "$dynamicRef")):
            value = self.get(key)
            if isinstance(value, str):
                ref = (dynamic and DynamicRef or Ref)(value).pipe(self.reflect)
                ref.root = self.root
                if len(self) > 1:
                    # when the schema contains more key we yield an
                    # overridden version of the schema to continue passing along
                    # type information (eg meta-data meta-schema)
                    yield Schema(**{key: Expanded})
                    yield self
                yield Schema.expand(ref.resolve())


    # ALL schema can be expanded into a oneOf, this is the top level applicator
    # the oneOf expansion is the door into all json schema representation.
    def expand_one_of(self, object=EMPTY):
        """expand the oneOf for this schema, and if an object is provided, return the subschema that validates the object"""
        oneOf = self.get("oneOf")
        if oneOf is Expanded:
            return
        if oneOf and isinstance(oneOf, (list, tuple)):
            yield dict(oneOf=Expanded)
            if object is EMPTY:
                for subschema in oneOf:   
                    Schema.expand(subschema)
            else:
                for subschema in oneOf:
                    if Schema.is_valid(subschema, object):
                        yield Schema.expand(subschema)
            
    def expand_if_then_else(self, object=EMPTY):
            oneOf = []
            i, t, e = self.get("if"), self.get("then"), self.get("else", Schema.Dict())
            if i is not None and i is not Expanded:
                yield {
                    "if": Expanded,
                    "then": Expanded,
                    "else": Expanded,
                }
                if Schema.is_valid(i, object):
                    # yield i
                    if t is not None:
                        yield Schema.expand(t)
                else:
                    yield Schema.expand(e)

    def expand_role(self):
        from .roles import aria_role

        return self.reflect(Schema(self, role=aria_role(self)))
    def expand_type_array(self):
        type = self.get("type")
        if type and isinstance(type, (list, tuple)):
            subschemas = []
            if not isinstance(self, Schema):
                self = Schema(self)
            if len(type) > 1:
                # override type
                if not isinstance(self, Schema):
                    self = Schema(self)
                expanded = dict(type=Expanded)
                if self.get("oneOf") is not Expanded:
                    expanded["oneOf"] = [
                        dict(type=t) for t in type
                    ]
                self.insert(0, expanded)
            else:
                self.insert(0, type=type[0])
        # elif not type:
        #     objects = []
        #     if "default" in self:
        #         objects.append(Schema.default(self))
        #     if objects:
        #         return self.reflect(Schema(infer_schema(*objects), self))
        return self
        
    

class Repr:
    # def repr(self, type=None):
    #     if type is None:
    #         type = self.type()
    #     return f"{type}({self.id()})"
    pass
class Form:
    pass

class Validate:
    ValidationErrors = ValidationErrors
    def errors(self, object, raises=True):
        import jsonschema
        jsonschema._types.bool = jsonschema._keywords.bool = Boolean
        if isinstance(object, collections.ChainMap):
            return Schema.validator(object.maps[0])
        object = object.builtin() if isinstance(object, Object) else object
        # try:
        return list(Schema.validator(self).iter_errors(object))
        # finally:
        #     del jsonschema._types.bool, jsonschema._keywords.bool
    
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

    def validate(self, object=EMPTY, raises=True, all=True):
        """validate the given object against this schema, and return the object with defaults filled in"""
        if object is EMPTY:
            object = Schema.default(self)
        errors = Schema.validator(self).iter_errors(object)
        if all:
            errors = list(errors)
            if errors and raises:
                raise ValidationErrors(object.id(), errors)
        elif raises:
            for error in errors:
                raise error
        return errors
    
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
    
    def instance(self, object=None, **kwargs):
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
    __call__ = instance

    def as_default(self, object=EMPTY):
        """create an instance of this schema from the given object, validating it and filling in defaults"""
        if object is EMPTY:
            object = self.default()
        return self.reflect(Schema(self, default=object))
    
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
                if key == "default":
                    object = self.first_dict(key, expand=False).set_parent(self).set_path(self.path + [key])
                else:
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

    def first_dict(self, key, expand=True):
        for map in getattr(self, "maps", [self]):
            if key in map:
                value = map[key]
                if isinstance(value, (dict, collections.ChainMap)):
                    if expand:
                        return Schema.expand(value)
                    return value
        return None
    
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
                        # expanded = self.reflect(Schema(value), key).expand()
                        expanded = Schema.expand(value)
                        maps = getattr(expanded, "maps", [expanded])
                        if len(maps) == 1:
                            values.append(value)
                        else:
                            values.extend(maps)
                    else:
                        values.append(value)
        if len(values) == 1:
            return values[0]
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
    
    def get(self, key, default=EMPTY):
        try:
            return self[key]
        except KeyError:
            if self.schema:
                if default is EMPTY:
                    from .schemas import Schema
                    subschema = Schema.property(self.schema, key)
                    return Schema.default(subschema)
            return None if default is EMPTY else default
        
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

    def get(self, key, default=EMPTY):
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
            # can probably clean this up with referncing
            url = Uri.parse(map)
            if url.scheme in ("http", "https"):
                cached = Schema._cached_schemas.get(map)
                if cached is None:
                    return Schema.expand(Ref(map).resolve())
                return cached
        elif isinstance(map, (bool, Boolean)):
            if map:
                return Dict()
            else:
                return Dict({"not": Dict()})
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
        return super().from_file(file, format=format)

    @classmethod
    def dispatch(cls, value):
        from .objects import dispatch
        return cls(
            dispatch(value)
        )
    def role(self):
        from .roles import aria_role
        return aria_role(self)
    from .objects import Object, Dict, Boolean, Uri, Ref, Array, Null, String, Expanded
   
from .objects import dispatch, dispatch_object
Object.dispatcher.register(Schema)(dispatch_object)

class Meta(Schema):
    def __call__(self, *schema, **kwargs):
        return Schema(*schema, **kwargs).set_schema(self)
        
Schema.Meta = Meta
Schema.Schema = Schema
from .referencing import Ref, DynamicRef
Schema.Ref = Ref
Schema.DynamicRef = DynamicRef