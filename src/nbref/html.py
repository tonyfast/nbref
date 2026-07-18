# TODO handle array of schema types


from bs4 import Tag
from collections.abc import Generator
from functools import wraps
from .objects import Null, Object
from .schemas import Schema
from .utils import el, separate_schema
import collections

# containers and regions

from bs4 import Tag
from collections.abc import Generator
from functools import wraps
from .objects import Null, Object
from .schemas import Schema
from .utils import el, infer_schema, separate_schema
import collections

# an html formatter based on a schema. the schema provides the representation of the space
# that the objects occupy. 
class Formatter(Schema):
    # def __new__(cls, *args, **kwargs):
    #     self = super().__new__(cls)
    #     if len(args) == 1 and not kwargs:
    #         object = args[0]
    #         if isinstance(object, Schema):
    #             self.__init__(*object.maps, **kwargs)
    #             self.set_root(object.root).set_parent(object.parent).set_path(object.path)
    #             return self
        
    #     self.__init__(*args, **kwargs)
    #     return self
    
    # def __init__(self, *args, **kwargs):
    #     super().__init__(*args, **kwargs)
    #     if args: 
    #         if isinstance(args[0], Object):
    #             object = args[0]
    #             self.set_root(object.root).set_parent(object.parent).set_path(object.path)
    
    @classmethod
    def format_object_schema(cls, object, schema=None):
        object = Object.dispatch(object)
        if schema is None:
            if object.schema:
                schema = object.schema
            else:
                object.infer_schema()
                object.schema.set_root(object.root.schema)
        else:
            object.schema = schema
        return object
    
    @classmethod
    def from_object(cls, object, schema=None):
        object = Object.dispatch(object)
        return cls(schema or object.schema)
    
    @classmethod
    def format_object(cls, object, schema=None):
        object  = Object.dispatch(object)
        return cls.from_object(object, schema).format(object)
    
    def format(self, object):
        return self.applicator(
            Object.dispatch(object)
        )
    
class Python(Formatter):
    def format(self, object, schema=None):
        if isinstance(object, Object):
            return object.builtin()
        return object


class Html(Formatter):    
    def form(self, object, schema=None):
        path = object.path
        aria = dict(
            labelledby=str(path + [":region", ":title"]),
            describedby=str(path + [":region", ":desc"])
        )
        name = self.get("attrs", {}).get("name", str(object.path[-1]))
        form = el("form", self.hgroup(object), aria=aria, id=str(path + [":form"]), klass="root schema".split(), name=name)
        return el("section", form, id=str(path + [":region"]), aria=aria)

    def comments(self, object):
        for comment in Schema.comment(self):
            yield el("p", comment, klass=["comment"])


    def hgroup(self, object):
        path = object.path + [":region"]
        hgroup = el("hgroup", id=str(path), aria=dict(
            labelledby=str(path + [":title"]),
            describedby=str(path + [":desc"])
        ))
        el(hgroup, el(f"h{len(path) - 1}", self.get("title", object.path[-1]), id=self.id(":title"), klass=["title"]))
        el(hgroup, el("p", self.get("description", ""), id=self.id(":desc"), klass=["desc"]))
        return hgroup
    

    def region(self, object):
        # dispatch the container type
        role = self.get("role")
        if role in ("dialog", "alertdialog"):
            return self.dialog(object)
        if role in ("details", "group", None):
            return self.details(object)
        if role in ("table", "grid"):
            return self.table(object)
        return self.section(object)


    def section(self, object):
        path = object.path + [":region"]
        attrs = {k: v for k, v in self.attrs(object).items() if k in ["class"]}

        section = el("section", el("hgroup"), id=self.id(":region"), aria=dict(
            labelledby=self.id(":title"),
            describedby=self.id(":desc"),
        ))
        el(section.hgroup, el(f"h{len(path) - 1}", self.title(), id=self.id(":title")))
        el(section.hgroup, el("p", self.description(), id=self.id(":desc")))
        return section


    def table(self, object):
        #  the table could be an independent formatter
        if isinstance(object, list):
            return self.table_list(object)
        elif isinstance(object, dict):
            return self.table_dict(object)
        raise NotImplementedError(f"self.table not type {type(object)}")
    
    
    def details(self, object):
        attrs = {}
        if self.get("aria", {}).get("expanded", True):
            attrs["open"] = ""
        path = object.path + [":region"]
        attrs["id"] = str(path)
        attrs.setdefault("aria", {}).update(
            labelledby=str(path + [":title"]),
            describedby=str(path + [":desc"])
        )
        details = el("details", el("summary", self.get("title", str(object.path[-1])), id=self.id(":title")), **attrs)
        el(details, el("p", self.get("description", ""), id=self.id(":desc")))
        [el(details, comment) for comment in self.comments(object)]
        return details
    
    def applicator(self, object):
        if self:
            if "oneOf" in self:
                return self.one_of(object)
            if "anyOf" in self:
                return self.any_of(object)
            for type in self.types():
                if type == "object":
                    return self.object(object)
                elif type == "array":   
                    return self.array(object)
        return self.input(object)
    
    def one_of(self, object):
        one_of = self["oneOf"]
        list = el("ul")
        for subschema in one_of:
            validator = Schema(subschema)
            attrs = {}
            try:
                validator.validate(object)
                attrs["checked"] = ""
                value = object
            except BaseException:
                # value = Schema.default(subschema).set_parent(object.parent).set_root(object.root).set_path(object.path)
                value = object.reflect(Schema.default(subschema))
                        
            selected = el("input", type="radio", **attrs)
            el(list, el("li", selected, type(self)(subschema).applicator(value)))
        return el(self.region(object), list)
    
    def any_of(self, object):
        pass

    def object(self, object):
        list = el("ul", aria=dict(
            labelledby=str(object.path + [":region", ":title"]),
            describedby=str(object.path + [":region", ":desc"])
        ), item=dict(scope="", prop=object.path[-1], type="object"))
        # print(555555, is_readonly(self), self is self.root, is_readonly(self.root))
        # stacked list of required, properties, and additionalProperties
        required = self.required()
        for property in required:
            value = object.get(property)
            if value is None:
                subschema = Schema.property(self, property)
                value = Schema.default(subschema).set_parent(object.parent).set_root(object.root).set_path(object.path + [property]).set_schema(subschema)
            el(list, el("li", self.format_object(value), klass=["property", property, "required"], **self.attrs_numeric(value)))

        properties = self.properties()
        for property in properties:
            if property not in required:
                try:
                    value = object[property]
                except KeyError:
                    continue
                # value = object.get(property)
                # if value is None:
                #     subschema = Schema.property(self, property)
                #     value = Schema.default(subschema).set_parent(object.parent).set_root(object.root).set_path(object.path + [property]).set_schema(subschema)
                    
                el(list, el("li", self.format_object(value, value.schema), klass=["property", property, "optional"], **self.attrs_numeric(value)))

        for property in object or ():
            if property not in required and property not in properties:
                value = object.get(property)
                if value is None:
                    subschema = Schema.property(self, property)
                    value = Schema.default(subschema)
                    if value is None:
                        value = Null()
                    # value = value.set_parent(object.parent).set_root(object.root).set_path(object.path + [property]).set_schema(subschema)
                    value = self.reflect(value, property).set_schema(subschema)
                el(list, el("li", self.format_object(value, value.schema), klass=["property", property, "additional"], **self.attrs_numeric(value)))

        additional_properties = self.additional()
        # print(is_readonly(self))
        if additional_properties and not is_readonly(self):
            add = el("button", "add property", klass=["add", "property"])

        if len(object.path) == 1:
            form = self.form(object)
            el(form.form, list)
            if additional_properties:
                el(form.form, add)
            el(form, self.comments(object))
            yield form
        else:
            region = self.region(object)
            el(region, list, data=dict(length=str(len(object))), klass=["object"])
            if additional_properties:
                el(region, add)
            el(region, self.comments(object))
            yield region

    def array(self, object):
        # print(self is self.root)
        list = el("ol", aria=dict(
            labelledby=str(object.path + [":region", ":title"]),
            describedby=str(object.path + [":region", ":desc"])
        ), item=dict(
            scope="", prop=str(object.path[-1]), type="array"
        ))
        items = self.get("items", False)
        length = len(object)
        minItems = self.get("minItems", 0)
        if minItems > length:
            length = minItems
        for index in range(min(self.get("maxItems", length), length)):
            value = object[index]
            index += 1
            if value.schema is None:
                subschema = Schema().set_parent(self).set_root(self.root).set_path(self.path + ["items"])
            else:
                subschema = Schema(value.schema).set_root(self.root)
            aria = dict(
                posinset=index,
                setsize=len(object)
            )
            subschema.append(dict(title=str(index)))
            el(list, el("li", type(self).format_object(value, subschema), klass=["item"], aria=aria, **self.attrs_numeric(value)))
            # print(4444,is_readonly(subschema), subschema is subschema.root, is_readonly(subschema.root))
        region = self.region(object)
        el(region, list, data=dict(length=str(len(object))), klass=["array"])
        if items and not is_readonly(self):
            add = el("button", "add item", klass=["add", "item"])
            el(region, add)
        el(region, self.comments(object))
        yield region

    def input(self, object):
        role = self.get("role")
        elements = self.input_element(object)
        if role:
            yield el(self.region(object), elements, klass=["input", role])
        else:
            yield from elements

    def input_element(self, object, units=True):
        type = Object.type(object)
        if "boolean" not in type:
            yield self.label(object)
        if self and "enum" in self:
            yield from self.enum(object)
        else:
            type = Object.type(object)
            if "string" in type:
                yield from self.string(object)
            elif "boolean" in type:
                yield self.label(object)
                yield from self.boolean(object)
            elif type in ("number", "integer"):
                yield from self.number(object)
            elif "null" in type:
                yield from self.null(object)
            elif "array" in type:
                yield from self.array(object)
            elif "object" in type:      
                yield from self.object(object)
            if units:
                yield from self.unit(object)
        yield from el("p.description", "".join(self.get("description", "")))
        yield from self.comments(object)

    
    def label(self, object):
        path = object.path
        attrs = {"for": str(path)}
        # support editable labels
        if self:
            return el("label", self.get("title", path[-1]), **attrs)
        return el("label", path[-1], **attrs)
    
    def enum(self, object):
        path = object.path 
        attrs = self.attrs(object)
        attrs.setdefault("item", {}).update(
            prop=str(object.path[-1]),
            type="enum"
        )
        select = el("select", id=str(path), **attrs)
        for option in self["enum"]:
            attrs = {}
            if object == option:
                attrs["selected"] = ""
            el(select, el("option", option, **attrs))
        yield select

    def dialog(self, object):
        path = object.path
        attrs = self.attrs(object)
        dialog = el("dialog", id=str(path), **attrs)
        el(dialog, self.hgroup(object))
        return dialog

    def string(self, object):
        attrs = self.string_attrs(object)
        
        path = object.path 
        attrs["id"] = str(path)
        format = self.get("format", "text")
        contentMediaType = self.get("contentMediaType", None)
        object = "".join(object)
        if format == "textarea":
            attrs.update(rows=object.count("\n")  + 1)
            yield el("textarea", object, **attrs)
        elif contentMediaType == "text/html":
            from .utils import parse_html
            yield parse_html(object)
        elif contentMediaType == "application/json":
            yield self.script(object)
        else:
            yield el("input", type=format, value=object, **attrs)

    def string_attrs(self, object):
        attrs = self.attrs(object)
        attrs.setdefault("item", {}).update(
            prop=str(object.path[-1]),
            type="string"
        )
        if "minLength" in self:
            attrs["minlength"] = str(self["minLength"])
        if "maxLength" in self:
            attrs["maxlength"] = str(self["maxLength"])
        if "pattern" in self:
            attrs["pattern"] = self["pattern"]
        attrs.update(name=str(object.path[-1]))
        return attrs
    
    def number_attrs(self, object):
        attrs = self.attrs(object)
        attrs.setdefault("item", {}).update(
            prop=str(object.path[-1]),
            type="number"
        )
        type = object.type()
        if "minimum" in self:
            attrs["min"] = str(self["minimum"])
        if "exclusiveMinimum" in self:
            attrs["min"] = str(self["exclusiveMinimum"])
        if "exclusiveMaximum" in self:
            attrs["max"] = str(self["exclusiveMaximum"])
        if "maximum" in self:
            attrs["max"] = str(self["maximum"])
        if type == "integer":
            attrs["step"] = "1"
        if "multipleOf" in self:
            attrs["step"] = str(self["multipleOf"])
        attrs.update(
            value=str(object),
            type="number",
            name=str(object.path[-1])
        )
        return attrs
    
    def number(self, object):
        attrs = self.number_attrs(object)
        path = object.path
        attrs["id"] = str(path)
        if "unit" in self:
            attrs.setdefault("aria", {})["owns"] = str(path + ["unit"])
        # print(self.builtin())
        yield el("input", **attrs)

    def boolean(self, object):
        attrs = self.attrs(object)
        path = object.path 
        attrs["id"] = str(path)
        if object:
            attrs["checked"] = ""
        yield el("input", type="checkbox", **attrs)

    def unit(self, object):
        # microdata will need a reference to this because it is out of the nesting order
        if isinstance(self, (dict, collections.ChainMap)) and  "unit" in self:
            subschema = self["unit"]
            default = Schema.default(subschema)
            default.set_parent(object.parent).set_root(object.root).set_path(object.path + ["unit"])
            yield from self.format_object(default, subschema)

    def null(self, object):
        return el("span", "null")
    
    def classes(self, object):
        classes = self.get("attrs", {}).get("class", [])
        if self:
            if self.get("writeOnly") or self.get("writeonly"):
                classes.append("writeOnly")
            if self.get("readOnly") or self.get("readonly"):
                classes.append("readOnly")
        return classes

    def attrs_numeric(self, object, attrs=None):
        # numeric attributes are practical for styling.
        # selectors can be written on data attributes while
        # the css variables can be used for styling.
        if attrs is None:
            attrs = {}
        if isinstance(object, dict):
            for k, v in object.items():
                if isinstance(v, (int, float)):
                    print(k)
                    attrs.setdefault("data", {})[k] = str(v)
                    attrs.setdefault("style", {})[f"--{k}"] = str(v)
        return attrs

        
    def attrs(self, object):
        attrs = {}
        if self:
            classes = self.classes(object)
            if classes:
                attrs["class"] = classes
            if "attrs" in self:
                attrs.update(self["attrs"])
            if "on" in self:
                for event, handler in self["on"].items():
                    attrs[f"on{event}"] = handler
            if "aria" in self:
                for attribute, value in self["aria"].items():
                    if attribute not in {"expanded"}:
                        attrs[f"aria-{attribute}"] = value
            if "data" in self:
                for attribute, value in self["data"].items():
                    attrs[f"data-{attribute}"] = value
            if "item" in self:
                for attribute, value in self["item"].items():
                    attrs[f"item{attribute}"] = value
            if "style" in self:
                attrs["style"] = "; ".join(f"{k}: {v}" for k, v in self["style"].items())
            if is_readonly(self):
                attrs["readonly"] = ""
                # well strip the pointer and keyboard events
                attrs["tabindex"] = "-1"
        return attrs
    
    def render(self, object):
        from IPython.display import HTML
        return HTML("\n".join(map(str, self.format(object))))
    
    @classmethod
    def render_object(cls, object, schema=None):
        return cls.from_object(object, schema).render(object)
    
    def extract_metadata(self, object):
        from extruct import extract
        return extract(self.render_object(object).value)

def is_readonly(schema):
    if schema.get("readOnly") or schema.get("readonly"):
            return True
    elif schema is not schema.root:
            if schema.root.get("readOnly") or schema.root.get("readonly"):
                return True
    return False
    


# @separate_schema
# def self.form(object, schema):
#     path = object.path
#     aria = dict(
#         labelledby=str(path + [":region", ":title"]),
#         describedby=str(path + [":region", ":desc"])
#     )
#     form = el("form", html_hgroup(object, schema), html_applicator(object, schema), aria=aria, id=str(path + [":form"]), klass="root schema".split())
#     section = el(
#         "section", form, id=str(path + [":region"]), aria=aria
#     )
#     return section


# def html_comments(object, schema):
#     for comment in Schema.all_strings(schema, "$comment"):
#         yield el("p", comment, klass=["comment"])

# def html_hgroup(object, schema):
#     path = object.path + [":region"]
#     hgroup = el("hgroup", id=str(path), aria=dict(
#         labelledby=str(path + [":title"]),
#         describedby=str(path + [":desc"])
#     ))
#     el(hgroup, el(f"h{len(path) - 1}", schema.get("title", object.path[-1]), id=str(path + [":title"]), klass=["title"]))
#     el(hgroup, el("p", schema.get("description", ""), id=str(path + [":desc"]), klass=["desc"]))
#     return hgroup

# def html_region(object, schema):
#     # dispatch the container type
#     role = schema.get("role")
#     if role in ("details", "group", None):
#         return html_details(object, schema)
#     if role in ("table", "grid"):
#         return html_table(object, schema)
#     return html_section(object, schema)

# def html_section(object, schema):
#     path = object.path + [":region"]
#     section = el("section", el("hgroup"), id=str(path), aria=dict(
#         labelledby=str(path + [":title"]),
#         describedby=str(path + [":desc"])
#     ))
#     el(section.hgroup, el(f"h{len(path) - 1}", schema.get("title", object.path[-1]), id=str(path + [":title"])))
#     el(section.hgroup, el("p", schema.get("description", ""), id=str(path + [":desc"])))
#     return section

# def html_table(object, schema):
#     if isinstance(object, list):
#         return html_table_list(object, schema)
#     elif isinstance(object, dict):
#         return html_table_dict(object, schema)
#     raise NotImplementedError(f"html_table not implemented for type {type(object)}")

# def html_table_list(object, schema):
#     table = el("table", el("thead"), el("tbody"))
#     # prefixItems will have a list of the schemas.
#     # additionalItems will have a single schema for the rest of the items.
    
#     return table

# def html_row_list(object, schema):
#     row = el("tr")
#     return row

# def html_row_dict(object, schema):
#     row = el("tr")
#     return row

# def html_table_dict(object, schema):
#     table = el("table", el("thead"), el("tbody"))

#     return table

# def html_details(object, schema):
#     attrs = {}
#     if schema.get("aria", {}).get("expanded", True):
#         attrs["open"] = ""
#     path = object.path + [":region"]
#     attrs["id"] = str(path)
#     attrs.setdefault("aria", {}).update(
#         labelledby=str(path + [":title"]),
#         describedby=str(path + [":desc"])
#     )
#     details = el("details", el("summary", schema.get("title", str(object.path[-1])), id=str(path + [":title"])), **attrs)
#     el(details, el("p", schema.get("description", ""), id=str(path + [":desc"])))
#     [el(details, comment) for comment in html_comments(object, schema)]
#     return details

# def html_applicator(object, schema):
#     if schema:
#         if "oneOf" in schema:
#             return html_one_of(object, schema)
#         if "anyOf" in schema:
#             return html_any_of(object, schema)
#         for type in schema.types():
#             if type == "object":
#                 return html_object(object, schema)
#             elif type == "array":   
#                 return html_array(object, schema)
#     return html_input(object, schema)

# def html_one_of(object, schema):
#     one_of = schema["oneOf"]
#     list = el("ul")
#     for subschema in one_of:
#         validator = Schema.validator(subschema)
#         attrs = {}
#         try:
#             validator.validate(object)
#             attrs["checked"] = ""
#             value = object
#         except BaseException:
#             value = Schema.default(subschema).set_parent(object.parent).set_root(object.root).set_path(object.path)
                        
#         selected = el("input", type="radio", **attrs)
#         el(list, el("li", selected, html_applicator(value, subschema)))
#     return el(html_region(object, schema), list)

# def html_object(object, schema):
#     list = el("ul", aria=dict(
#         labelledby=str(object.path + [":region", ":title"]),
#         describedby=str(object.path + [":region", ":desc"])
#     ))
#     # stacked list of required, properties, and additionalProperties
#     for property in object.properties():
#         value = object.get(property)
#         if value is None:
#             subschema = Schema.property(schema, property)
#             value = Schema.default(subschema).set_parent(object).set_root(object.root).set_path(object.path + [property])
#         if value.schema is None:
#             value.set_schema(Schema().set_parent(schema).set_root(schema.root).set_path(schema.path + ["items"]))
#         el(list, el("li", html_applicator(value, value.schema), klass=["property", property]))

#     additional_properties = schema.get("additionalProperties", False)
#     if additional_properties and not is_readonly(schema):
#         add = el("button", "add property")

#     if len(object.path) == 1:
#         yield list
#         if additional_properties:
#             yield add
#     else:
#         region = html_region(object, schema)
#         el(region, list, data=dict(length=str(len(object))), klass=["object"])
#         if additional_properties:
#             el(region, add)
#         el(region, html_comments(object, schema))
#         yield region

# def html_array(object, schema):
#     list = el("ol", aria=dict(
#         labelledby=str(object.path + [":region", ":title"]),
#         describedby=str(object.path + [":region", ":desc"])
#     ))
#     additional_items = schema.get("additionalItems", False)        
#     for index, value in enumerate(object, start=1):
#         if value.schema is None:
#             value.set_schema(Schema().set_parent(schema).set_root(schema.root).set_path(schema.path + ["items"]))
#         aria = dict(
#             posinset=index,
#             setsize=len(object)
#         )
#         el(list, el("li", html_applicator(value, value.schema), klass=["item"], aria=aria))
#     region = el(html_region(object, schema), list, data=dict(length=str(len(object))), klass=["array"])
#     if additional_items and not is_readonly(schema):
#         add = el("button", "add item")
#         el(region, add)
#     el(region, html_comments(object, schema))
#     yield region

# # html value representation

# def html_input(object, schema):
#     type = Object.type(object)
#     role = schema.get("role") if schema else None

#     if "boolean" not in type:
#         yield html_label(object, schema)
#     if schema and "enum" in schema:
#         yield from html_enum(object, schema)
#     elif "string" in type:
#         yield from html_string(object, schema)
#     elif "boolean" in type:
#         yield html_label(object, schema)
#         yield from html_boolean(object, schema)
#     elif type in ("number", "integer"):
#         yield from html_number(object, schema)
#     elif "null" in type:
#         yield from html_null(object, schema)
#     elif "array" in type:
#         yield from html_array(object, schema)
#     elif "object" in type:      
#         yield from html_object(object, schema)
#     yield from html_unit(object, schema)
#     yield from html_comments(object, schema)

# def html_label(object, schema):
#     path = object.path
#     attrs = {"for": str(path)}
#     # support editable labels
#     if schema:
#         return el("label", schema.get("title", path[-1]), **attrs)
#     return el("label", path[-1], **attrs)


# def html_enum(object, schema):
#     path = object.path 
#     attrs = html_attrs(object, schema)
#     select = el("select", id=str(path), **attrs)
#     for option in schema["enum"]:
#         attrs = {}
#         if object == option:
#             attrs["selected"] = ""
#         el(select, el("option", option, **attrs))
#     yield select

# def html_script(object, schema):
#     attrs = html_string_attrs(object, schema)
#     contentMediaType = schema.get("contentMediaType", None)
#     yield el("script", "".join(object), type=contentMediaType, **attrs, id=str(object.path))

# def html_string(object, schema):
#     attrs = html_string_attrs(object, schema)
#     path = object.path 
#     attrs["id"] = str(path)
#     format = schema.get("format", "text")
#     contentMediaType = schema.get("contentMediaType", None)
#     object = "".join(object)
#     if format == "textarea":
#         attrs.update(rows=object.count("\n")  + 1)
#         yield el("textarea", object, **attrs)
#     elif contentMediaType == "text/html":
#         from .utils import parse_html
#         yield parse_html(object)
#     elif contentMediaType == "application/json":
#         yield html_script(object, schema)
#     else:
#         yield el("input", type=format, value=object, **attrs)

# def html_string_attrs(object, schema):
#     attrs = html_attrs(object, schema)
#     if "minLength" in schema:
#         attrs["minlength"] = str(schema["minLength"])
#     if "maxLength" in schema:
#         attrs["maxlength"] = str(schema["maxLength"])
#     if "pattern" in schema:
#         attrs["pattern"] = schema["pattern"]
#     return attrs

# def html_number_attrs(object, schema):
#     attrs = html_attrs(object, schema)
#     type = object.type()
#     if "minimum" in schema:
#         attrs["min"] = str(schema["minimum"])
#     if "exclusiveMinimum" in schema:
#         attrs["min"] = str(schema["exclusiveMinimum"])
#     if "exclusiveMaximum" in schema:
#         attrs["max"] = str(schema["exclusiveMaximum"])
#     if "maximum" in schema:
#         attrs["max"] = str(schema["maximum"])
#     if type == "integer":
#         attrs["step"] = "1"
#     if "multipleOf" in schema:
#         attrs["step"] = str(schema["multipleOf"])
#     return attrs

# def html_number(object, schema):
#     attrs = html_number_attrs(object, schema)
#     path = object.path
#     attrs["id"] = str(path)
#     if "unit" in schema:
#         attrs.setdefault("aria", {})["owns"] = str(path + ["unit"])
#     yield el("input", type="number", value=str(object), **attrs)


# def html_boolean(object, schema):
#     attrs = html_attrs(object, schema)
#     path = object.path 
#     attrs["id"] = str(path)
#     if object:
#         attrs["checked"] = ""
#     yield el("input", type="checkbox", **attrs)

# def html_unit(object, schema):
#     if isinstance(schema, (dict, collections.ChainMap)) and "unit" in schema:
#         subschema = Schema.expand(schema["unit"])
#         default = Schema.default(subschema).set_parent(object.parent).set_root(object.root).set_path(object.path + ["unit"])
#         yield from html_input(default, subschema)

# def html_null(object, schema):
#     return el("span", "null")


# def html_attrs(object, schema):
#     attrs = {}
#     if schema:
#         if "attrs" in schema:
#             attrs.update(schema["attrs"])
#         if "on" in schema:
#             for event, handler in schema["on"].items():
#                 attrs[f"on{event}"] = handler
#         if "aria" in schema:
#             for attribute, value in schema["aria"].items():
#                 if attribute not in {"expanded"}:
#                     attrs[f"aria-{attribute}"] = value
#         if "data" in schema:
#             for attribute, value in schema["data"].items():
#                 attrs[f"data-{attribute}"] = value
#         if "item" in schema:
#             for attribute, value in schema["item"].items():
#                 attrs[f"item{attribute}"] = value
#         if "style" in schema:
#             attrs["style"] = "; ".join(f"{k}: {v}" for k, v in schema["style"].items())
#         if is_readonly(schema):
#             attrs["readonly"] = ""
#     return attrs

# html = html_form

def is_readonly(schema):
    if schema.get("readOnly") or schema.get("readonly"):
            return True
    # elif schema is not schema.root:
    #         if schema.root.get("readOnly") or schema.root.get("readonly"):
    #             return True
    return False