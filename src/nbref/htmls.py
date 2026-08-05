
import collections
from dataclasses import dataclass, field
from functools import partial
from turtle import title


from .schemas import Schema
from .utils import el, parse_html

def html_label(schema, object, options, **attrs):
    yield from ()

def html_description(schema, object, options, **attrs):
    yield from ()

def html_details(schema, object, options, **attrs):
    yield from ()

def html_controls(schema, object, options, **attrs):
    yield from ()

def html_owns(schema, object, options, **attrs):
    yield from ()

def html_disabled(schema, object, options, **attrs):
    yield from ()

def html_errors(schema, object, options, **attrs):
    yield from ()


# the renderers use iterators to yield the elements
# and the renderer function coalesces the elements into a single element.
def html_render(schema, object, options=None, *children, **attrs):
    """render an schema and object as html"""
    
    # initialize the options if they were not provided.
    if options is None:
        options = Options()
    # make the element concrete)
    result = list(
        html_applicator(schema, object, options, **attrs)
    )
    if len(result) == 1:
        # return a single element if there is only one child
        if children:
            result[0].extend(children)
        return result[0]
    # coalesce all the elements
    return options.el("div", *result, *children, **attrs)

def html_applicator(schema, object, options, **attrs):
    """render keys in the applicator schema"""
    # the first intervention in the schema and object is use either the
    # schema of object patcher to modify the schema and object before rendering.
    schema, object, options = html_patch(schema, object, options, **attrs)
    if not schema:
        schema = object.schema
    if not schema:
        schema = object.schema = Schema.infer(object)
    # the allof schema is doesn't need to be handled because the schema are aggregated.
    # nopes = list(html_not(schema, object, options, **attrs))
    # if nopes:
    #     yield from nopes
    # maybe if then doesnt have. visual represntation
    # an else representation means not then
    yield from html_if_then(schema, object, options, **attrs)
    # every schema can be represented as a one of schema so we use
    # that applicator generally for diving deeper into a schema representation
    yield from html_one_of(schema, object, options, **attrs)

def html_patch(schema, object, options, **attrs):
    """allows for modifying schema, object, and options in a scope."""
    for mapping, relative in [(options.schema_patch, schema.path), (options.object_patch, object.path)]:
        patch = mapping.get(tuple(relative))
        if patch:
            patched = patch(schema, object, options, **attrs)
            if patched is not None:
                if len(patched) == 1:
                    schema = patched[0]
                elif len(patched) == 2:
                    schema, object = patched
                elif len(patched) == 3:
                    schema, object, options = patched
                object.schema = schema
    return schema, object, options

def html_repr(schema, object, options, **attrs):
    yield from ()

def html_format_role_content(schema, object, options, **attrs):
    """handle the representation of the role, format, or content schema."""
    # process the format, then the content media type, and then the role.
    # this order was chosen because the format is the most flexible as it describes the
    # the content media type is specific to the type space.
    # the role is slowest to change and is codified in the WAI specifications.
    # we want a generic function that can call entry points
    repr = list(html_repr(schema, object, options, **attrs))
    if repr:
        yield from repr
        return
    format = list(html_format(schema, object, options, **attrs))
    if format:
        yield from format
        return
    content = list(html_content(schema, object, options, **attrs))
    if content:
        yield from content
        return
    # note: this is not the inferred role, that is handled in another role.
    role = schema.get("role")
    if role:
        # the next line will naturally raise when the explicit role can't be processed.
        callable = options.role_mapping.get(role)
        if callable is not None:
            yield from callable(schema, object, options, **attrs)
        return

def html_if_then(schema, object, options, **attrs):
    yield from ()


def html_one_of(schema, object, options, **attrs):
    """handle the one of and not schema representations"""

    # return the results for explicit role, format, or content schema.
    # this pass does not use the inferred role.
    explicit = list(html_format_role_content(schema, object, options, **attrs))
    if explicit:
        yield from html_parent(schema, object, options, *explicit)
        return

    one_of = schema.get("oneOf", [schema])
    if one_of is Schema.Expanded:
        one_of = [schema]

    # what role making the most sense for a oneOf schema?
    only_one = len(one_of) == 1
    ol = options.el("ol.oneof", klass=[object.type()], role="group")

    errors = []
    for subschema in one_of:
        # print(subschema)
        # subschema = Schema.expand(subschema)
        t = Schema.type(subschema)
        # print(22, t)
        # i make the mistake of not using this form a lot.
        # calling subschema.type() doesnt give the expected outcomes.
        # print(object.path, t)
        # print(t, subschema.path, object.path)
        value = object
        attrs = {}
        # print(t, subschema)
        if t in ["string", "number", "integer", "boolean", "null"]:
            errors.append(Schema.errors(subschema, value))
            if errors[-1]:
                # when there is a default and we can render the a valid value we use the default
                value = Schema.default(subschema).set_path(object.path).set_root(object.root)
            else:
                attrs["checked"] = ""
        elif t and t is not Schema.Expanded:
            # there is an error and this value is not valid
            error = Schema.errors(Schema(type=t), object)
            errors.append(error) # make the decision based on the length of the errors. 
            # errors.append(True)
        classes = html_classes(subschema, value, options, **attrs)
        item = options.el("li.oneof", klass=classes)
        # wheres the radio label? 
        radio = options.el(
            "input.radio", type="radio", name=object.id("oneof"), value=str(subschema.path[-1]), 
            **attrs,
            aria=html_aria_labelledby(subschema, value, options, **attrs)
            | dict(owns=object.id())
        )
        options.el(item, radio)
        # subschema = subschema.reflect(Schema(subschema)).append(title=F"{subschema.type()}")
        iterator = only_one and html_validator or html_applicator
        children = list(iterator(subschema, value, options, **attrs))
        options.el(item, *children)
        options.el(ol, item)
    # print(errors)
    if only_one:
        # when a schema of one is valid return just the children
        if not any(errors):
            # this drops the radio button
            children = (x for i, x in enumerate(ol.li.children) if i)
            yield from html_parent(schema, object, options, *children, **attrs)
            return

    # we would have escaped at this point if we dont need to record errors
    # any invalid references are considered to be an extension of one of.
    # errors are different than explicit not value.
    # not could define a null space or singular values.
    # errors are generated.
    # explicit not values make sense at the bottom while 
    # errors make sense at the top
    negative_schema = schema.get("not")
    if any(errors):
        # TODO: compound schema if not lready exists
        negative_schema = ~Schema(Schema.infer(object), title=object.title())
    # print(negative_schema)
    if negative_schema:
        negative_schema = negative_schema.append(tags=["not"])
        # add the negative schema and value to the list of children
        invalid = options.el("li.invalid.not", klass=[object.type(), object.path[-1]])
        # generate a synthetic not schema
        value = object.copy()
        value.schema = negative_schema
        radio = options.el(
            "input.radio", type="radio", name=object.id("oneof"), value=str(negative_schema.path[-1]), 
            checked="", aria=html_aria_labelledby(subschema, object, options, **attrs)
        )
        options.el(invalid, radio, html_not(negative_schema, value, options, errors, **attrs))
        # print(errors)
        # el(invalid, html_validation_errors(negative_schema, errors, options, **attrs))
        ol.insert(0, invalid)
    
    yield from html_parent(schema, object, options, ol, **attrs)

def html_validation_errors(schema, object, options, **attrs):
    """create a representation of the validation errors"""
    for errors in object:
        features = []
        for error in errors:
            feature = dict(
                    exception=str(error.__class__),
                    path=error.absolute_path,
                    schema_path=error.absolute_schema_path,
                    message=str(error.message),
            )
            features.append(feature)
        features = Schema.Array(features).set_schema(role="table", type="object")
        if features:
            yield from html_role(
                features.schema, features, options
            )

def html_not(schema, object, options, errors=None, **attrs):
    """create a representation of the not schema"""
    nope = schema.get("not")
    if nope is not None:
        if errors is None:
            errors = [Schema.errors(schema, object)]
        if not nope:
            nope = Schema.infer(object)
        nope = nope.reflect(Schema(nope, tags=["not"]))
        value = object.copy()
        value.schema = nope
        repr = html_applicator(nope, value, options, **attrs)
        error_repr = html_validation_errors(nope, errors, options, **attrs)
        error_repr = html_parent(Schema(
            parent=dict(role="group", title="invalid"), tags=["not"]
        ), value, options, *error_repr, **attrs)
        # not sure if we need parent here
        yield from html_parent(schema, object, options, *repr, error_repr, **attrs)

def html_parent(schema, object, options, *children, **attrs):
    parent = schema.get("parent")
    if parent:
        role = Schema.role(parent)
        yield from options.role_mapping.get(role)(parent, object, options, *children)
        return
    yield from children

def html_validator(schema, object, options, **attrs):
    # create a representation based on the role the schema refers to.
    children = list(html_format_role_content(schema, object, options, **attrs))
    if not children:
        yield from html_role(schema, object, options, **attrs)
    yield from html_dependent_schemas(schema, object, options, **attrs)
    

def html_dependent_schemas(schema, object, options, **attrs):
    # for units to work efficiently in dependent schemas we should
    # use aria-owns off the parent input. this way the parent input 
    # can concatenate all the values.

    # dependentRequired should be implemented near here possibly using something
    # similar to the Schema.column pattern because that doesnt create defaults.
    dependent_schemas = schema.get("dependentSchemas", {})
    # yield from ()
    for key, subschema in dependent_schemas.items():
        # the dependent schema values probably wont actually be in the object,
        # so we should recover them fromt he settings but for the meantime we'll use defaults.
        # since the valid isn't guarenteed we need to manually expand the schema.
        value = Schema.default(Schema.expand(subschema)).set_path(object.path + [key]).set_root(object.root)
        yield from html_applicator(subschema, value, options, **attrs)

def html_role(schema, object, options, **attrs):
    # infer the implicit or explicit role of the schema.
    role = Schema.role(schema, options, object)
    # print(role, schema.path, object.path)
    callable = options.role_mapping.get(role)
    if callable is None:
        # print("role", role, object.path, object)
        yield from html_input(schema, object, options, **attrs)
        return
    # print(callable, object)
    yield from callable(schema, object, options, **attrs)

# the html object and array renders have navigation above and below.
# the top navigation operates like tabs in a tabbed interface,
# while the bottom navigation works better for pagination.
# the options/schema should control. for example {aria: {activedescendent: false}}
# would indicates a lack of tabs. the pagination would handlded by 
# a modulo of some kids if there are 100 things pagination is 1000 then we have 
# one navigation which would be suppressed.
def html_object(schema, object, options, **attrs):
    klass = html_classes(schema, object, options)
    ul = options.el("ul.object", klass=klass)
    columns = Schema.columns(schema, object)
    navigation = []
    for subschema, value in columns:
        k = html_classes(subschema, value, options)
        item = options.el("li", klass=k)
        title = html_title(subschema, value, options)
        link = options.el("a.link", title, id=value.id("link"), href="#" + value.id("link"), klass=k)
        options.el(item, link, *html_applicator(subschema, value, options))
        options.el(ul, item)

        
    # yield activate descendent navigation
    yield ul
    # yield pagination    

def html_array(schema, object, options, **attrs):
    klass=html_classes(schema, object, options, **attrs)
    attrs = html_attrs(schema, object, options, **attrs)
    ol = options.el("ol.array", **attrs)
    for index in range(len(object)):
        value = object[index]
        # print(value.path, value)
        subschema = value.schema
        k = html_classes(subschema, value, options)
        # add data attributes for the numeric values in the object
        for s, o in Schema.columns(subschema, value):
            # this is the first place where rdf comes into play
            t = s.get("@type", "")
            if "rdfs:label" in t:
                k.append(o)
            # if Schema.type(s) in ["number", "integer", "boolean"]:
            #     # let numeric values become css values.
            #     attrs.setdefault("data", {}).update({s.path[-1]: o})
            #     attrs.setdefault("style", {}).update({f"--{s.path[-1]}": o})
            html_attrs_numeric_data(s, o, options)
            html_attrs_numeric_style(s, o, options)
                # missing dependentSchema variables here.
        item = options.el("li", klass=k, aria=dict(posinset=index + 1, setsize=len(object)))
        title = html_title(subschema, value, options, **attrs)
        link = options.el("a.link", title, id=value.id("link"), href="#" + value.id("link"), klass=k)
        options.el(item, link, *html_applicator(subschema, value, options, **attrs))
        # add role to item class
        options.el(ol, item)
    options.el(ol, klass=klass, **attrs)
    # the group role adds label, description, details for the list.
    yield ol
    

def html_attrs_numeric_style(schema, object, options, **attrs):
    for s, o in Schema.columns(schema, object):
        t = Schema.types(s)
        if set(t).intersection(["number", "integer", "boolean"]):
            # let numeric values become css values.
            # attrs.setdefault("data", {}).update({s.path[-1]: o})
            attrs.setdefault("style", {}).update({f"--{s.path[-1]}": o})
    return attrs

def html_attrs_numeric_data(schema, object, options, **attrs):
    for s, o in Schema.columns(schema, object):
        if Schema.type(s) in ["number", "integer", "boolean"]:
            # let numeric values become css values.
            attrs.setdefault("data", {}).update({s.path[-1]: o})
            # attrs.setdefault("style", {}).update({f"--{s.path[-1]}": o})
    return attrs


def html_details(schema, object, options, *children, **attrs):
    classes = html_classes(schema, object, options, **attrs)    
    details = options.el("details", klass=classes)
    if schema.get("attrs", {}).get("open", True):
        details.attrs["open"] = ""
    attrs = html_attrs(schema, object, options, **attrs)
    attrs["id"] = object.id("title")
    yield options.el(
        details, options.el("summary.label", *html_title(schema, object, options, **attrs), klass=classes), 
        *html_description(schema, object, options),
        *children, *html_comments(schema, object, options),
        **attrs
    )

def html_fieldset(schema, object, options, *children, **attrs):
    fieldset = options.el("fieldset", klass=[object.type()])
    attrs = html_attrs(schema, object, options, **attrs)
    yield options.el(
        fieldset, options.el("legend", str(object.title())), 
        *html_description(schema, object, options),
        *children, *html_comments(schema, object, options),
        **attrs
    )

def html_label(schema, object, options, **attrs):
    attrs["for"] = object.id()
    attrs["id"] = object.id("label")
    label = options.el("label.label", **attrs)
    options.el(label, *html_title(schema, object, options, **attrs), **attrs)
    yield label

def html_title(schema, object, options, **attrs):
    title = Schema.title(schema)
    tags = schema.get("tags", [])
    type = object.type()
    
    if "not" in tags:
        yield options.el("span.invalid", "invalid")

    key = object.path[-1]
    if key != title:
        if isinstance(key, int):
            key = str(key + 1)
        yield options.el("span.key", key, klass=[type])
    if isinstance(title, int):
        title = str(title + 1)
    yield options.el("span.title", title, klass=[type])
    yield options.el("span.type", type, klass=[type])
    
def html_description(schema, object, options, **attrs):
    """a description from the schema of the object"""
    description = schema.get("description")
    if description:
        attrs["id"] = object.id("desc")
        yield from options.role_mapping["paragraph"](schema, description, options, **attrs)

def html_comments(schema, object, options, **attrs):
    """comments from the object"""
    comments = schema.get("comments", [])
    if comments:
        attrs["id"] = object.id("comments")
        yield from options.role_mapping["group"](schema, object, options, *[options.el("p", comment) for comment in comments], **attrs)

def html_input(schema, object, options, **attrs):
    format = list(html_format(schema, object, options, **attrs))
    if format:
        yield from format
        return
    
    type = object.type()

    if type == "string":
        yield from html_string(schema, object, options, **attrs)
    elif type == "boolean":
        yield from html_checkbox(schema, object, options, **attrs)
    elif type in ["number", "integer"]:
        yield from html_input_number(schema, object, options, **attrs)
    elif type == "null":
        yield from html_paragraph(schema, object, options, **attrs)

def html_input_number(schema, object, options, **attrs):
    attrs = html_attrs(schema, object, options, **attrs)
    attrs.update(html_aria_labelledby(schema, object, options, **attrs))
    if "parent" not in schema:
        yield from html_label(schema, object, options, **attrs)
    yield options.el("input.number", type="number", value=str(object), **attrs)
    # dependent_schemas = schema.get("dependentSchemas", {})
    # for key, subschema in dependent_schemas.items():
    #     yield from html_validator(subschema, object, options, **attrs)

def html_string(schema, object, options, **attrs):
    if schema.get("aria", {}).get("multiline"):
        # remove the multiline attribute
        yield from html_textarea(schema, object, options, **attrs)
        return
    attrs = html_attrs(schema, object, options, **attrs)
    attrs.update(html_aria_labelledby(schema, object, options, **attrs))
    if "parent" not in schema:
        yield from html_label(schema, object, options, **attrs)
    # print(object.path, object)
    yield options.el("input.string", type="text", value=str(object), **attrs)

def html_textarea(schema, object, options, **attrs):
    attrs = html_attrs(schema, object, options, **attrs)
    attrs.update(html_aria_labelledby(schema, object, options, **attrs))
    body = "".join(object)
    attrs["rows"] = body.count("\n") + 1
    if "parent" not in schema:
        yield from html_label(schema, object, options, **attrs)
    yield options.el("textarea.string", body , **attrs)

def html_checkbox(schema, object, options, **attrs):
    attrs = html_attrs(schema, object, options, **attrs)
    attrs.update(html_aria_labelledby(schema, object, options, **attrs))
    attrs["type"] = "checkbox"
    if object:
        attrs["checked"] = ""
    yield options.el("input.boolean", **attrs)
    yield from html_label(schema, object, options, **attrs)

def html_paragraph(schema, object, options, *children, **attrs):
    yield options.el("p", str(object), *children, **attrs)


# html attributes
def html_aria_labelledby(schema, object, options, **attrs):
    """return the id of the label for the object"""
    aria = {
    }
    if not schema.get("aria", True):
        return aria
    aria["aria-labelledby"] = object.id("title")
    description = object.description()
    if description:
        aria["aria-describedby"] = object.id("desc")
    return aria


def html_classes(schema, object, options, **attrs):
    classes = []
    classes += attrs.get("class", [])
    classes += attrs.get("klass", [])
    classes += schema.get("attrs", {}).get("class", [])
    classes += schema.get("tags", [])
    if len(object.path) == 1:
        if object.name:
            classes += [object.name]
    else:
        classes += [object.path[-1]]
    classes += [object.type(), object.title()]
    if isinstance(object, dict):
        pass # look for key, values with tag references
    output = []
    # for s, o in Schema.columns(schema, object):
    #     t = s.get("@type", "")
    #     if "rdfs:label" in t:
    #         classes.append(o)
    #     if "@id" in t:
    #         classes.append(o)
    for klass in classes:
        if isinstance(klass, str):
            klass = "".join(
                c if c.isalnum() or c in ["-", "_"] else "_" for c in klass
            )
            if klass not in output:
                output.append(klass)
    return output

def html_attrs(schema, object, options=None, itemscope=False, **attrs):
    """convert a schema into html attributes for the object"""
    if itemscope:
        attrs.setdefault("item", {}).update(
            prop=object.path[-1]
        )
        if object.type() in ["object", "array"]:
            attrs["item"]["scope"] = ""
    if "attrs" in schema:
        attrs.update(schema["attrs"])
    if "on" in schema:
        for event, handler in schema["on"].items():
            attrs[f"on{event}"] = handler
    if "aria" in schema:
        aria = schema["aria"]
        if aria:
            for attribute, value in schema["aria"].items():
                if attribute not in {"expanded"}:
                    attrs[f"aria-{attribute}"] = value
    if "data" in schema:
        for attribute, value in schema["data"].items():
            attrs[f"data-{attribute}"] = value
    if "item" in schema:
        for attribute, value in schema["item"].items():
            attrs[f"item{attribute}"] = value
    if "style" in schema:
        attrs["style"] = "; ".join(f"{k}: {v}" for k, v in schema["style"].items())
    # if "role" in schema:
    #     attrs["role"] = schema["role"]
    # if is_readonly(schema):
    #     attrs["readonly"] = ""

    classes = html_classes(schema, object, options, **attrs)
    if classes:
        attrs["class"] = classes
    return attrs
    
landmark_tags = dict(
    main="main",
    form="form",
    region="section",
    complementary="aside",
    banner="header",
    contentinfo="footer",
)

def html_region(schema, object, options, *children, tag=None, **attrs):
    role = schema.get("role", "region")
    tag = tag or "section"
    attrs = html_attrs(schema, object, options, **attrs)
    if tag in {"section"}:
        attrs["role"] = role
    attrs.update(html_aria_labelledby(schema, object, options, **attrs))
    yield options.el(tag, *children, **attrs)

def html_form(schema, object, options, *children, **attrs):
    attrs = html_attrs(schema, object, options, **attrs)
    yield options.el("form", *children, **attrs)

def html_dialog(schema, object, options, *children, **attrs):
    if schema.get("aria", {}).get("expanded"):
        yield from html_region(schema, object, options, *children, tag="section", **attrs)
        # yield and expand button
        return
    attrs = html_attrs(schema, object, options, **attrs)
    button_schema = Schema(schema, on=dict(
        click="""event.target.ariaControlsElements.forEach((target)=>{
            target.showModal()
        })"""
    ), aria=dict(controls=object.id("dialog")))
    yield from options.role_mapping["button"](button_schema, object, options, **attrs)
    close_button = options.el("button.close", "close", html_title(schema, object, options, **attrs))
    form = options.el("form", *children, close_button, method="dialog", **attrs)
    yield options.el("dialog", form, id=object.id("dialog"), **attrs)

def html_dialog_block(schema, object, options, *children, **attrs):
    """a section that can be opened as a dialog to trim that accessibility tree."""
    attrs = html_attrs(schema, object, options, **attrs)
    section = options.el("section.dialog", *children, **attrs)
    # gotta check if we are in a form before we create one other wise that is bad html
    button = options.role_mapping["button"](schema, object, options, **attrs)
    options.el(section, button)
    yield section


def html_script(schema, object, options, **attrs):
    attrs = html_attrs(schema, object, options, **attrs)
    attrs.setdefault("style", "display: block;")
    attrs["type"] = schema.get("contentMediaType", "text/plain")
    yield from html_details(
        schema, object, options, options.el("script", str(object), **attrs), **attrs
    )

def html_raw(schema, object, options, **attrs):
    yield from options.role_mapping["group"](schema, object, options, *parse_html("".join(object)), **attrs)

def html_markdown(schema, object, options, **attrs):
    from markdown_it import MarkdownIt
    md = MarkdownIt()
    html = md.render("".join(object))
    # handle attachments
    cell = (outputs:= (data:= object.parent).parent.parent).parent
    attachments = cell.get("attachments", {})
    for document in parse_html(html):
        if hasattr(document, "select"):
            for a in document.select("img"):
                if a.attrs.get("src", "").startswith("attachment:"):
                    attachment = a.attrs["src"].partition("attachment:")[2]
                    if attachment in attachments:
                        for mimetype, data in attachments[attachment].items():
                            datauri = f"data:{mimetype};base64,{data}"
                            a.attrs["src"] = datauri
        yield document

def html_button(schema, object, options, **attrs):
    attrs = html_attrs(schema, object, options, **attrs)
    if isinstance(object, (dict, list)):
        text = object.title()
    else:
        text = object

    yield options.el("button", str(text), **attrs)

def html_link(schema, object, options, *children, **attrs):
    attrs = html_attrs(schema, object, options, **attrs)
    yield options.el("a", str(object), *children, **attrs)

def html_table(schema, object, options, **attrs):
    thead = html_thead(schema, object[0], options, **attrs)
    tbody = html_tbody(schema, object, options, **attrs)
    table = options.el("table", *thead, *tbody, **attrs)
    yield table
    # create a prefixItems schema that is more practical

def html_thead(schema, object, options, **attrs):
    thead = options.el("thead", **attrs)
    tr = options.el("tr", **attrs)
    options.el(tr, options.el("th", "row"))
    for subschema, value in Schema.columns(schema, object):
        th = options.el("th", str(subschema.title()), **attrs)
        options.el(tr, th)
    yield options.el(thead, tr)

# on decimal alignment, only objects of type: number require it.

def html_tbody(schema, object, options, **attrs):
    tbody = options.el("tbody", **attrs)
    stats = {}
    for index, value in enumerate(object, 1):
        attrs = {"class": html_classes(schema, value, options, **attrs)}
        attrs = html_attrs_numeric_style(value.schema, value, options, **attrs)
        attrs.setdefault("data", {}).setdefault("style", {}).update({"-index": index})
        tr = options.el("tr", **attrs)
        k = []
        link = options.el("a.link", int(index), id=value.id("link"), href="#" + value.id("link"), klass=k)
        options.el(tr, options.el("th", link))
        for subschema, v in Schema.columns(schema, value):
            td = options.el("td", *html_applicator(subschema, v, options))
            options.el(td, klass=html_classes(subschema, v, options, **attrs))
            options.el(tr, td)
        options.el(tbody, tr)
    yield tbody

def html_datetime(schema, object, options, **attrs):
    attrs = html_attrs(schema, object, options, **attrs)
    attrs.update(html_aria_labelledby(schema, object, options, **attrs))    
    attrs["type"] = "datetime-local"
    yield options.el("input.datetime", value=str(object), **attrs)

def html_content(schema, object, options, **attrs):
    content = schema.get("contentMediaType")
    if content in options.content_mapping:
        yield from options.content_mapping[content](schema, object, options, **attrs)

def html_format(schema, object, options, **attrs):
    format = schema.get("format")
    if format in options.format_mapping:
        yield from options.format_mapping[format](schema, object, options, **attrs)

def html_image(schema, object, options, **attrs):
    attrs = html_attrs(schema, object, options, **attrs)
    if object:
    # we dont have to deal with attachments here.
        datauri = "data:"
        mimetype = schema.get("contentMediaType", "image/png")
        datauri += mimetype + ";"
        datauri += ["base64,", "utf-8,"]["svg"  in mimetype]
        datauri += str(object)
        attrs["src"] = datauri
    yield options.el("img", **attrs)

def html_select(schema, object, options, **attrs):
    attrs = html_attrs(schema, object, options, **attrs)
    attrs.update(html_aria_labelledby(schema, object, options, **attrs))
    if "parent" not in schema:
        yield from html_label(schema, object, options, **attrs)
    select = options.el("select", **attrs)
    for option in schema.get("enum", []):
        option_attrs = html_attrs(schema, object, options, **attrs)
        option_attrs["value"] = str(option)
        if object == option:
            option_attrs["selected"] = ""
        options.el(select, options.el("option", str(option), **option_attrs))
    yield select


def html_uri_list(schema, object, options, **attrs):
    # this function should rely on mimetype dispatching.
    # it should be able to load uri list strings
    ol = options.el("ol.load", klass=[object.type()])
    for i, uri in enumerate(object.splitlines()):
        # there is a loader with ref that we can use already
        if not uri.strip():
            continue
        attrs = dict(itemid=uri)
        # should guess the mimetye from the file extension
        # and supply that as contentMediaType
        # we'll encounter local/remote files and data uri's
        # right now it only handles notebooks
        if "://" in uri:
            # this is a place where would want to await
            # ref = object.reflect(, i)
            object = Schema.Ref(uri).resolve().contents
            object.schema = Schema(contentMediaType=Schema.Ref.mimetype(uri))
        else:
            continue
        item = options.el("li.load", **attrs)
        options.el(ol, options.el(item, *html_applicator(object.schema, object, options, **attrs)))
    yield ol

def html_heading(schema, object, options, **attrs):
    attrs = html_attrs(schema, object, options, **attrs)
    attrs.update(html_aria_labelledby(schema, object, options, **attrs))
    level = 1
    yield options.el(F"h{level}", object, **attrs)

widget_role_mappings = dict()
structure_role_mappings = dict()
window_role_mappings = dict()

role_mappings = collections.ChainMap(widget_role_mappings, structure_role_mappings, window_role_mappings)


role_mapping = dict(
    associationlist=html_object,
    banner=partial(html_region, tag="header"),
    button=html_button,
    checkbox=html_checkbox,
    code=html_content,
    complementary=partial(html_region, tag="aside"),
    contentinfo=partial(html_region, tag="footer"),
    dialog=html_dialog,
    form=html_form,
    group=html_details,
    heading=html_heading,
    img=html_image,
    input=html_input,
    link=html_link,
    list=html_array,
    main=partial(html_region, tag="main"),
    navigation=partial(html_region, tag="nav"),
    paragraph=html_paragraph,
    region=html_region,
    select=html_select,
    spinbutton=html_input_number,
    table=html_table,
    textbox=html_string,
) | {None: html_paragraph}

section_role_mapping = {}
structure_role_mapping = {}
widget_role_mapping = role_mapping
format_mapping = {
    "datetime": html_datetime,
    "json-pointer": html_link,
}

def html_nb(schema, object, options, **attrs):
    """render a notebook as html"""
    from .nb import html_nb
    yield from html_nb(schema, object, options, **attrs)

content_mapping = {
    "text/html": html_raw,
    "text/markdown": html_markdown,
    "image/png": html_image,
    "image/jpeg": html_image,
    "image/bmp": html_image,
    "image/svg+xml": html_image,
    "text/uri-list": html_uri_list,
    "application/x-ipynb+json": html_nb,
}

@dataclass
class Options:
    role_mapping: dict = field(default_factory=role_mapping.copy)
    format_mapping: dict = field(default_factory=format_mapping.copy)
    content_mapping: dict = field(default_factory=content_mapping.copy)
    schema_patch: dict = field(default_factory=dict)
    object_patch: dict = field(default_factory=dict)
    from .utils import el
    el = staticmethod(el)

# handle units

Schema.Options = Options