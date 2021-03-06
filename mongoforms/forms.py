import types

from django import forms, VERSION as django_version
if django_version < (1, 9):
    from django.utils.datastructures import SortedDict
    from django.forms.util import ErrorList
else:
    from collections import OrderedDict as SortedDict
    from django.forms.utils import ErrorList

from mongoengine.base import BaseDocument
from fields import MongoFormFieldGenerator, FormsetField
from utils import mongoengine_validate_wrapper, iter_valid_fields
from mongoengine.fields import ReferenceField

__all__ = ('MongoForm',)

class MongoFormMetaClass(type):
    """Metaclass to create a new MongoForm."""

    def __new__(cls, name, bases, attrs):
        # get all valid existing Fields and sort them
        fields = [(field_name, attrs.pop(field_name)) for field_name, obj in \
            attrs.items() if isinstance(obj, forms.Field)]
        fields.sort(lambda x, y: cmp(x[1].creation_counter, y[1].creation_counter))

        # get all Fields from base classes
        for base in bases[::-1]:
            if hasattr(base, 'base_fields'):
                fields = base.base_fields.items() + fields

        # add the fields as "our" base fields
        # discards fields specified for embeddeddocuments
        attrs['base_fields'] = SortedDict([f for f in fields if '__' not in f[0]])

        # Meta class available?
        if 'Meta' in attrs and hasattr(attrs['Meta'], 'document') and \
           issubclass(attrs['Meta'].document, BaseDocument):
            labels = getattr(attrs['Meta'], 'labels', {})
            doc_fields = SortedDict()

            meta_fields = list(getattr(attrs['Meta'], 'fields', []))
            formfield_generator = getattr(attrs['Meta'], 'formfield_generator', \
                MongoFormFieldGenerator)(meta_fields, overriden_fields=fields, exclude=getattr(attrs['Meta'], 'exclude', ()))

            overriden_fields = dict(fields)

            # walk through the document fields
            for field_name, field in iter_valid_fields(attrs['Meta']):
                if field_name == '_cls':
                    continue
                # add field and override clean method to respect mongoengine-validator
                if field_name in overriden_fields:
                    doc_fields[field_name] = overriden_fields[field_name]
                else:
                    doc_fields[field_name] = formfield_generator.generate(field_name, field)
                doc_fields[field_name].clean = mongoengine_validate_wrapper(
                    doc_fields[field_name].clean, field._validate, field.required)
                if labels.get(field_name):
                    doc_fields[field_name].label = labels[field_name]

            # write the new document fields to base_fields
            doc_fields.update(attrs['base_fields'])
            attrs['base_fields'] = doc_fields

        # maybe we need the Meta class later
        attrs['_meta'] = attrs.get('Meta', object())

        return super(MongoFormMetaClass, cls).__new__(cls, name, bases, attrs)

class MongoForm(forms.BaseForm):
    """Base MongoForm class. Used to create new MongoForms"""
    __metaclass__ = MongoFormMetaClass

    def __init__(self, data=None, files=None, auto_id='id_%s', prefix=None,
        initial=None, error_class=ErrorList, label_suffix=':',
        empty_permitted=False, instance=None, **kwargs):
        """ initialize the form"""

        assert isinstance(instance, (types.NoneType, BaseDocument)), \
            'instance must be a mongoengine document, not %s' % \
                type(instance).__name__

        assert hasattr(self, 'Meta'), 'Meta class is needed to use MongoForm'
        # new instance or updating an existing one?
        if instance is None:
            if self._meta.document is None:
                raise ValueError('MongoForm has no document class specified.')
            self.instance = self._meta.document()
            object_data = {}
            self.instance._adding = True
        else:
            self.instance = instance
            self.instance._adding = False
            object_data = {}

            # walk through the document fields
            for field_name, field in iter_valid_fields(self._meta):
                # add field data if needed
                field_data = getattr(instance, field_name)
                if isinstance(self._meta.document._fields[field_name], ReferenceField):
                    # field data could be None for not populated refs
                    field_data = field_data and str(field_data.id)
                object_data[field_name] = field_data

        # additional initial data available?
        if initial is not None:
            object_data.update(initial)

        self._validate_unique = False
        super(MongoForm, self).__init__(data, files, auto_id, prefix,
            object_data, error_class, label_suffix, empty_permitted, **kwargs)

        if prefix:
            for k, v in self.fields.items():
                if isinstance(v, FormsetField):
                    v.widget.name = "%s-%s" % (prefix, v.widget.name)

    def save(self, commit=True):
        """save the instance or create a new one.."""

        # walk through the document fields
        for field_name, field in iter_valid_fields(self._meta):
            setattr(self.instance, field_name, self.cleaned_data.get(field_name))

        if commit:
            self.instance.save()

        return self.instance


def mongoform_factory(embedded_document, extra_bases=None, extra_attrs=None, extra_meta=None):

    bases = (MongoForm, )

    if extra_bases:
        bases = extra_bases + bases

    meta_attrs = {'document': embedded_document}

    if extra_meta:
        meta_attrs.update(extra_meta)

    attrs = {
        'Meta': type('Meta', tuple(), meta_attrs)
    }

    if extra_attrs:
        attrs.update(extra_attrs)

    return MongoFormMetaClass('%sForm' % embedded_document.__name__, bases, attrs)
