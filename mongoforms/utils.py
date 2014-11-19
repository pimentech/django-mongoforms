from django import forms
from django.core.validators import EMPTY_VALUES

from mongoengine.base import ValidationError
from mongoengine.base.fields import ObjectIdField

from mongoforms.fields import FormsetField, FormField

def mongoengine_validate_wrapper(old_clean, new_clean, required):
    """
    A wrapper function to validate formdata against mongoengine-field
    validator and raise a proper django.forms ValidationError if there
    are any problems.
    """

    def inner_validate(value):
        value = old_clean(value)

        if not issubclass(new_clean.im_class, (FormsetField, FormField)):
            if not required and value in EMPTY_VALUES:
                value = new_clean.im_self.default
                if callable(value):
                    value = value()
                return value
        try:
            new_clean(value)
            return value
        except ValidationError, e:
            raise forms.ValidationError(e)
    return inner_validate

def iter_valid_fields(meta):
    """walk through the available valid fields.."""

    # fetch field configuration and always add the id_field as exclude
    meta_fields = getattr(meta, 'fields', ())
    meta_exclude = getattr(meta, 'exclude', ())
    id_field = meta.document._meta.get('id_field', 'id')
    if isinstance(meta.document._fields.get(id_field), ObjectIdField):
        meta_exclude += (id_field,)

    # walk through meta_fields or through the document fields to keep
    # meta_fields order in the form
    if meta_fields:
        for field_name in meta_fields:
            if '__' in field_name:
                field_name = field_name.split('__', 1)[0]

            field = meta.document._fields.get(field_name)
            if field:
                yield (field_name, field)
    else:
        for field_name in meta.document._fields_ordered:
            # skip excluded fields
            if field_name not in meta_exclude:
                field = meta.document._fields.get(field_name)
                yield (field_name, field)
