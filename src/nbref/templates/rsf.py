from abc import ABC
from collections import ChainMap
from typing import Generator

from bs4 import Tag
import bs4

UNDEFINED = object()

class Pointer(list):
    def json(self):
        import jsonpointer
        return str(jsonpointer.JsonPointer.from_parts(self))[1:]
    
class HasPointer:
    path: list
    parent: object
    root: object

    def set_path(self, path: list):
        self.path = Pointer(path)
        return self

    def set_parent(self, parent):
        self.parent = parent
        return self

    def set_root(self, root):
        self.root = root
        return self

class HasSchema:
    schema: "Schema"

    def set_schema(self, schema: dict=None, **kwargs):
        if schema is None:
            schema = Schema()
        if kwargs:
            schema.update(kwargs)
        self.schema = schema
        return self

class Object(HasSchema, HasPointer):
    def __init__(self, *args, **kwargs):
        if isinstance(self, dict | list | ChainMap):
            super().__init__(*args, **kwargs)
        self.schema = None
        self.root = self
        self.parent = self
        self.path = Pointer(["#"])

    @classmethod
    def dispatch(cls, data):
        dict_type = Schema if isinstance(cls, Schema) else Dict
        if isinstance(data, Object):
            return data
        match data:
            case dict():
                return dict_type(data)
            case list() | tuple() | set():
                return List(data)
            case str():
                return String(data)
            case bool():
                return Boolean(data)
            case float() | int():
                return Number(data)
            
        if isinstance(data, type(None)):
            return None
        raise TypeError(f"Unsupported data type: {type(data)}")
    
    
    def validate(self, exception=True):
        try:
            self.schema.validate(self)
        except BaseException as e:
            if exception:
                raise e
            import traceback
            traceback.print_exc()
            
        return self

    def html(self, **opts):
        return self.schema.html(self, **opts)
    
class PathGetter:

    def __getitem__(self, key):
        object = super().__getitem__(key)
        object = self.root.dispatch(object).set_parent(self).set_root(self.root).set_path(
            self.path + [key]
        )
        object.set_schema(
            schema_property(self.schema, key, object)
        )
        return object
    
class Dict(Object, PathGetter, dict):
    def get(self, key, default=None):
        if key in self:
            return self[key]
        return default
    
    def expand(self):
        return schemas(self)
    
class Schema(Dict):
    def expand(self):
        return schemas(self)

def flatten(schemas):
    if isinstance(schemas, (dict, ChainMap)):
        object = {}
        for key in schemas:
            object[key] = flatten(schemas[key])
    elif isinstance(schemas, list):
        object = list(map(flatten, schemas))
    else:
        return schemas
    return object

class Bunch:
    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError:
            super().__getattribute__(name)
    flatten = flatten

class Properties(Object, PathGetter, Bunch, ChainMap):
    def __getitem__(self, key):
        schema = Schemas().set_parent(self).set_root(self.root).set_path(self.path + [key])
        for map in self.maps:
            if key in map:
                schema.maps.append(map[key])
        if len(schema.maps) == 0:
            super().__getitem__(key)

        if len(schema.maps) == 1:
            return schema.maps[0]
        return schema
    flatten = flatten

    
class Schemas(Object, PathGetter, Bunch, ChainMap):
    def __init__(self, *maps, **kwargs):
        if kwargs or not maps:
            maps = maps + (kwargs,)
        super().__init__(*map(Schema.dispatch, maps))
        self.type = UNDEFINED
        self._expanded = False
        if self.maps[0]:
            self.schema = self.maps[0].schema
            self.root = self.maps[0].root    
            self.parent = self.maps[0].parent
            self.path = self.maps[0].path

    object_properties = ("properties", "additionalProperties", "patternProperties", "dependentSchemas")
    array_properties = ("required", "type")
    string_properties = ("description", "$comment")
    unary_properties = "type",

    def __getitem__(self, key):
        if key not in self:
            raise KeyError(key)
        if key in self.object_properties:
            properties = Properties()
            for map in self.maps:
                value = map.get(key)
                if value is not None:   
                    if isinstance(value, dict):
                        properties.maps.append(value)
            return properties.set_path(self.path + [key]).set_root(self.root).set_parent(self)
        
        if key in self.array_properties:
            object = List([]).set_path(self.path + [key]).set_root(self.root).set_parent(self)
            for map in self.maps:
                value = map.get(key)
                if value is not None:
                    if isinstance(value, list):
                        object.extend(value)
                    else:
                        object.append(value)
            if key in self.unary_properties and len(object) == 1:
                 return object[0]
            return object
        return self.dispatch(super().__getitem__(key)).set_path(self.path + [key]).set_root(self.root).set_parent(self)

    def validate(self, data):
        import jsonschema
        schema 
        jsonschema.Draft202012Validator(self.maps[0]).validate(data)
        return self

    def html(self, data, **opts):
        return schema_html(self, data, **opts)
    
    def py(self, data=UNDEFINED):
        return schema_type_python(self, data)
    
    def expand(self):
        if not isinstance(self, ChainMap):
            self = Schemas(self)
        ref = schema_ref(self.maps[0])
        if ref:
            self.maps.append(Schema(ref).expand())
        # handle $ref and $dynamicRef
        allof = schema_allOf(self.maps[0])
        for i in range(len(allof)):
            self.maps.append(Schema(allof[i]).expand())
        if len(self.maps) == 1:
            return self.maps[0]
        self.type = schema_type_core(self, UNDEFINED)
        self._expanded = True
        return self

class List(Object, PathGetter, list):
    pass

class Number(Object, float):
    pass

class Boolean(ABC, Number):
    def __repr__(self):
        return str(bool(self))

Boolean.register(bool)

class String(Object, str):
    pass

def data_type(data):
    return schema_type(data.schema, data)

def css_parsed(parsed, attrs=None, level=0):
    """lexical analysis of a parsed css selector, returning the tag name and attributes, supporting a subset of css selectors, and some custom syntax for forms"""
    from cssselect.parser import (
        Selector,
        Class,
        Element,
        Hash,
        Attrib,
        CombinedSelector,
    )

    if attrs is None:
        attrs = dict()
    match parsed:
        case Selector():
            return css_parsed(parsed.parsed_tree, attrs, level=level + 1)
        case Class():
            klasses = attrs.setdefault("klass", [])
            if parsed.class_name not in klasses:
                klasses.append(parsed.class_name)
            return css_parsed(parsed.selector, attrs, level=level + 1)
        case CombinedSelector():
            first = element_from_selector(parsed.selector, attrs, level=level + 1)
            second = element_from_selector(parsed.subselector, None, level=level + 1)
            if parsed.combinator in "> ":
                return el(first, second)
            raise NotImplementedError(f"combinator {parsed.combinator} not implemented")
        case Element():
            return el(Tag(name=parsed.element), **attrs)
        case Attrib():
            attrs.update({parsed.attrib: parsed.value.value})
            return css_parsed(parsed.selector, attrs, level=level + 1)
        case Hash():
            attrs.update(id=parsed.id)
            return css_parsed(parsed.selector, attrs, level=level + 1)
        case list():
            for tree in parsed:
                return css_parsed(tree, attrs, level=level + 1)


def el(
    tag: Tag | str,
    *content: str | Tag,
    klass: list | None = None,
    data: list | None = None,
    aria: list | None = None,
    on: list | None = None,
    item: list | None = None,
    **attrs,
) -> Tag:
    """create or update tag(s) given tag as a selector, content, and attributes

    a fault tolerant way to manipulate html elements, supporting a subset of css selectors, and some custom syntax for forms, and some custom syntax for forms,
    when the tag is an `Tag`, the content and attributes will be added to the tag, otherwise a new tag will be created from the selector and content and attributes added to it.
    """

    if isinstance(tag, str):
        tag = element_from_selector(tag)

    tag.attrs.update(attrs)
    if klass is not None:
        if isinstance(klass, str):
            klass = klass.split()
        klasses = tag.attrs.setdefault("class", [])
        for k in klass:
            if k not in klasses:
                klasses.append(k)
    if data is not None:
        # the data dict is for custom data attributes, like {"id": "123"}
        tag.attrs.update({f"data-{k}": v for k, v in data.items()})
    if aria is not None:
        # the aria dict is for ARIA attributes, like {"checked": "true"}
        tag.attrs.update({f"aria-{k}": v for k, v in aria.items()})
    if on is not None:
        # the on dict is for event handlers, like {"click": "doSomething()"}
        tag.attrs.update({f"on{k}": v for k, v in on.items()})
    if item is not None:
        # the item dict is for microdata
        tag.attrs.update({f"item{k}": v for k, v in item.items()})

    content = [c for c in content if c is not None]
    for object in content:
        if not object:
            continue
        if isinstance(object, (list, tuple, Generator)):
            el(tag, *object)
        else:
            if isinstance(object, (int, float)):
                object = str(object)
            tag.append(object)
    return tag


def element_from_selector(selector, attrs=None, level=0) -> Tag:
    """create a Tag from a css selector, supporting a subset of css selectors, and some custom syntax for forms"""

    if attrs is None:
        attrs = dict()
    if isinstance(selector, str):
        import cssselect
        selector = cssselect.parse(selector)

    tag = css_parsed(selector, attrs)
    if tag is None:
        tag = Tag(name=attrs.pop("tag"), attrs=attrs)
    return el(tag, **attrs)

def schema_type(schema, data):
    if schema is not None:
        if "enum" in schema:
            return "enum"
        
        if "type" in schema:
            t = schema["type"]
            if isinstance(t, list):
                return "anyOf"
            return t
    
        if "if" in schema:
            return "ifThenElse"
    
        if "oneOf" in schema:
            return "oneOf"
        if "anyOf" in schema:
            return "anyOf"
    
        
        if (
            "properties" in schema
            or "additionalProperties" in schema
            or "patternProperties" in schema
        ):
            return "object"
        if "items" in schema or "prefixItems" in schema:
            return "array"
        
        if "$ref" in schema:
            return schema_type(schema_ref(schema, data), data)

    if isinstance(data, str):
        return "string"
    if isinstance(data, bool):
        return "boolean"
    if isinstance(data, float | int):
        return "number"
    if data is None:
        return "null"

    if isinstance(data, dict):
        return "object"
    if isinstance(data, list | tuple | set):
        return "array"
    raise "any"



def schema_type_core(schema, data):
    if schema is not None:
        if "enum" in schema:
            return "enum"
        
        if "type" in schema:
            t = schema["type"]
            return t
       
        if (
            "properties" in schema
            or "additionalProperties" in schema
            or "patternProperties" in schema
        ):
            return "object"
        if "items" in schema or "prefixItems" in schema:
            return "array"
        
        if "$ref" in schema:
            return schema_type(schema_ref(schema, data), data)

    if isinstance(data, str):
        return "string"
    if isinstance(data, bool):
        return "boolean"
    if isinstance(data, float | int):
        return "number"
    if data is None:
        return "null"

    if isinstance(data, dict):
        return "object"
    if isinstance(data, list | tuple | set):
        return "array"
    return UNDEFINED



def getitem_schema(self, key):
    if self.schema is None:
        object = Schema()
    else:
        pass

def html_object(schema, data, level=0, **opts):
    section = el("section", klass="schema object")
    section.append(el(
        "hgroup",
        el("h{level}".format(level=level + 1), schema_title(schema, data)),
        el("p", schema_description(schema, data)),
        klass="schema header",
    ))
    ol = el("ol", klass="schema object")
    section.append(ol)
    required = schema_required(schema)
    properties = schema_properties(schema)
    additional = schema_additional_properties(schema)

    for key in required:
        value = data.get(key, None)
        subschema = schema_property(schema, key, value) or additional
        ol.append(
            el("li", schema_html(subschema, value, level + 1, **opts))
        )

    for key in properties:
        if key in required:
            continue
        value = data.get(key, None)
        subschema = schema_property(schema, key, value)
        ol.append(
            el("li", schema_html(subschema, value, level + 1, **opts))
        )

    if additional and data:
        for key in data:
            if key in required or key in properties:
                continue
            value = data[key]
            ol.append(
                el("li", schema_html(additional, value, level + 1, **opts))
            )
    return section

def html_enum(schema, data=UNDEFINED, level=0, **opts):
    select = el("select", klass="schema enum")
    data = schema_default(schema, data)
    for key, value in schema_enum(schema, data).items():
        option = el("option", str(value), value=key)
        if key == data:
            option.attrs["selected"] = ""
        select.append(option)
    return html_label(schema, data), select, html_description(schema, data)

def html_description(schema, data):
    # include comments and examples here
    return el("p", schema_description(schema, data), klass="schema description"), el("p", schema_comment(schema, data), klass="schema comment")

def html_input(schema, data, type="text", **opts):
    yield html_label(schema, data)

    type = schema_type(schema, data)
    attrs = html_attrs(schema)
    attrs["value"] = data
    if type == "number":
        attrs["type"] = "number"
    elif type == "string":
        attrs["type"] = "text"
    elif type == "boolean":
        attrs["type"] = "checkbox"
        if attrs.pop("value", False):
            attrs["checked"] = ""
    yield el("input", **attrs)
    dependentSchemas = schema_dependent(schema, data)
    if dependentSchemas:
        for key in dependentSchemas:
            subschema = dependentSchemas[key]
            yield schema_html(subschema, data, **opts)
    yield html_description(schema, data)
    
def html_label(schema, data):
    return el("label", schema_title(schema, data))

def schema_allOf(schema, data=UNDEFINED):
    if "allOf" in schema:
        return schema["allOf"]
    return List()

def schema_comment(schema, data):
    if "comment" in schema:
        return schema["comment"]
    return ""


def schema_description(schema, data):
    if "description" in schema:
        return schema["description"]
    return ""

def schema_dependent(schema, data):
    if "dependentSchemas" in schema:
        return schema["dependentSchemas"]
    return {}


def schema_enum(schema, data):
    if "enum" in schema:
        enum = schema["enum"]
        if isinstance(enum, list):
            return dict(zip(enum, enum))
        return enum
    return UNDEFINED

def schema_ref(schema, data=UNDEFINED):
    import jsonpointer, jsonschema_specifications, referencing

    ref = schema.get("$ref")
    if ref is None:
        return None
    if isinstance(ref, list):
        ref = str(jsonpointer.JsonPointer.from_parts(ref))[1:]
    print(ref)
    resolver = jsonschema_specifications.REGISTRY.resolver_with_root(
        referencing.Resource.from_contents(schema.root, referencing.jsonschema.DRAFT202012)
    )
    resolved = Object.dispatch(resolver.lookup(ref).contents)
    resolved.set_path(ref.split("/")).set_root(schema.root)
    return resolved

def schema_resolve(schema, data):
    if "$ref" in schema:
        ref = schema_ref(schema, data)
        if ref:
            schema.update(ref)
    return schema

def schemas(combined_schemas, data=UNDEFINED):
    # while we walk through the schemas we should interpret the types we find
    if not isinstance(combined_schemas, ChainMap):
        combined_schemas = Schemas(combined_schemas)

    # when there are many schema, many constraints, they need to be synthesized.
    # we need to look for the primary type(s) of the object. 
    # we should leave with a known type and that type can be help by the schema
    ref = schema_ref(combined_schemas.maps[0], data)
    if ref:
        combined_schemas.maps.append(schemas(ref, data))
    # handle $ref and $dynamicRef
    allof = schema_allOf(combined_schemas.maps[0], data)
    for i in range(len(allof)):
       combined_schemas.maps.append(schemas(allof[i], data))
    if len(combined_schemas.maps) == 1:
        return combined_schemas.maps[0]
    return combined_schemas

def schema_html(schema, data, level=0, **opts):
    if isinstance(schema, bool):
        schema = {}

    schema = schema_resolve(schema, data)
        
    type = schema_type(schema, data)
    if type == "object":
        return html_object(schema, data, level, **opts)
    elif type == "array":
        return html_array(schema, data, level, **opts)
    elif type == "enum":
        return html_enum(schema, data, level, **opts)
    elif type == "ifThenElse":
        return html_if_then_else(schema, data, level, **opts)
    elif type == "oneOf":
        return html_one_of(schema, data, level, **opts)
    elif type == "string":
        return html_input(schema, data, level, **opts)
    elif type == "number":
        return html_input(schema, data, level, **opts)
    elif type == "boolean":
        return html_input(schema, data, level, **opts)
    elif type == "null":
        return html_input(schema, data, level, **opts)
    return html_text(schema, data, level, **opts)

def schema_property(schema, key, value):
    """extract the subschema for a specific key and value. some schema will run validation"""
    type = schema_type(schema, value)
    if schema is not None:
        if type == "object":
            if "properties" in schema and key in schema["properties"]:
                return schema["properties"][key]
            if "additionalProperties" in schema:
                return schema["additionalProperties"]
            if "patternProperties" in schema:
                patterns = schema["patternProperties"]
                for pattern in patterns:
                    import re
                    subschema = patterns[pattern]
                    if re.match(pattern, key):
                        return subschema
        elif type == "array":
            if "prefixItems" in schema:
                prefixItems = schema["prefixItems"]
                if len(prefixItems) > key:
                    return prefixItems[key]
            if "items" in schema:
                return schema["items"]
    return Schema()


def schema_title(schema, data):
    if "title" in schema:
        return schema["title"]
    if schema.path:
        return schema.path[-1]
    if "$id" in schema:
        return schema["$id"]
    if data.path:
        return data.path[-1]
    return ""

def schema_type_python(schema, data):
    type = schema_type(schema, data)
    default = schema_default(schema, data)
    if default is not UNDEFINED:
        return Object.dispatch(default).set_schema(schema)
    
    if type == "object":
        return Dict().set_schema(schema)
    elif type == "array":
        return List().set_schema(schema)
    elif type == "string":
        return String().set_schema(schema)
    elif type in ["number", "integer"]:
        return Number().set_schema(schema)
    elif type == "boolean":
        return Boolean().set_schema(schema)
    elif type == "null":
        return None
    return None

def schema_additional_properties(schema):
    if schema:
        return schema.get("additionalProperties", Schema().set_path(schema.path + ["additionalProperties"]))
    return True

    
def schema_properties(schema):
    if schema:
        return schema.get("properties") or {}
    return {}

def schema_required(schema):
    if schema:
        return schema.get("required") or []
    return []


def html_attrs(schema):
    attrs = {}
    if "on" in schema:
        attrs.update({f"on{k}": v for k, v in schema["on"].items()})
    if "item" in schema:
        attrs.update({f"item{k}": v for k, v in schema["item"].items()})
    if "data" in schema:
        attrs.update({f"data-{k}": v for k, v in schema["data"].items()})
    if "aria" in schema:
        attrs.update({f"aria-{k}": v for k, v in schema["aria"].items()})
    return attrs

def schema_one_of(schema, data):
    if "oneOf" in schema:
        return schema["oneOf"]
    return []

def html_one_of(schema, data, level=0, **opts):
    frame = el("section", klass="schema oneof")
    ol = el("ol", klass="schema oneof")
    frame.append(ol)
    one_of = schema_one_of(schema, data)

    for i in range(len(one_of)):
        subschema = one_of[i]
        item = el("li")
        ol.append(item)
        selected_attrs = {}
        try:
            value = subschema.validate(data)
            selected_attrs["checked"] = ""
        except Exception as e: 
            value = subschema.py()
        el(item, el("input", type="radio", name=data.path, value=i, **selected_attrs), schema_html(subschema, value, level=level + 1, **opts))
    return frame

def schema_default(schema, data=UNDEFINED):
    if "default" in schema:
        return schema["default"]
    return data