# -*- coding:utf-8 -*-

from django import forms
from django.core import validators
from django.core.exceptions import ValidationError
from django.forms.formsets import formset_factory, BaseFormSet
from django.utils.encoding import smart_unicode
from bson.errors import InvalidId
from bson.objectid import ObjectId
from mongoengine import StringField, EmbeddedDocumentField


class ReferenceField(forms.ChoiceField):
    """
    Reference field for mongo forms. Inspired by `django.forms.models.ModelChoiceField`.
    """
    def __init__(self, queryset, *aargs, **kwaargs):
        forms.Field.__init__(self, *aargs, **kwaargs)
        self.queryset = queryset

    def _get_queryset(self):
        return self._queryset

    def _set_queryset(self, queryset):
        self._queryset = queryset
        self.widget.choices = self.choices

    queryset = property(_get_queryset, _set_queryset)

    def _get_choices(self):
        if hasattr(self, '_choices'):
            return self._choices

        self._choices = [(obj.id, smart_unicode(obj)) for obj in self.queryset]
        return self._choices

    choices = property(_get_choices, forms.ChoiceField._set_choices)

    def clean(self, value):
        try:
            oid = ObjectId(value)
            oid = super(ReferenceField, self).clean(oid)
            if 'id' in self.queryset._query_obj.query:
                obj = self.queryset.get()
            else:
                obj = self.queryset.get(id=oid)
        except (TypeError, InvalidId, self.queryset._document.DoesNotExist):
            raise forms.ValidationError(self.error_messages['invalid_choice'] % {'value':value})
        return obj

class StringForm(forms.Form):
    da_string = forms.CharField(required=True)

    @classmethod
    def format_initial(cls, initial):
        if initial:
            return [{'da_string': i} for i in initial]

    @classmethod
    def get_data(cls, cleaned_data):
        return [data['da_string'] for data in cleaned_data]

class MixinEmbeddedForm:
    @classmethod
    def format_initial(cls, initial):
        if initial:
            return [d.__dict__['_data'] for d in initial]

    @classmethod
    def get_data(cls, cleaned_data):
        return [cls.Meta.document(**data) for data in cleaned_data]

class FormsetInput(forms.Widget):

    def __init__(self, form=None, name='', attrs=None):
        super(FormsetInput, self).__init__(attrs=attrs)
        self.form_cls = form
        self.name = name
        self.formset = formset_factory(self.form_cls, formset=BaseFormSet, extra=0, can_delete=True)

    def _instanciate_formset(self, data=None, initial=None):
        initial = self.form_cls.format_initial(initial)
        self.form = self.formset(data, initial=initial, prefix=self.name)

    def render(self, name, value, attrs=None):
        self._instanciate_formset(initial=value)
        management_javascript = """
        <a href="#add_%s" id="add_%s">Add an entry</a>
        <script type="text/javascript">
        function add_form(src_form, str_id, insertbefore) {
          var num = $('#id_'+str_id+'-TOTAL_FORMS').val();
          $('#id_'+str_id+'-TOTAL_FORMS').val(parseInt(num)+1);

          var html = $(src_form).html().replace(/__prefix__/g, ''+num);
          $(html).insertBefore($(insertbefore));
          return false;
        }
        $(document).ready(function(){
          $('a#add_%s').click(function(event){
            add_form('#empty_%s', '%s', this);
            return false;
          });
        });
        </script>
        """ % (self.name, self.name, self.name, self.name, self.name)

        empty_form = '<div id="empty_%s" style="display: none;">%s</div>' % (self.name, self.form.empty_form.as_p())

        return self.form.as_p()+ empty_form + management_javascript

    def value_from_datadict(self, data, files, name):
        """
        Given a dictionary of data and this widget's name, returns the value
        of this widget. Returns None if it's not provided.
        """
        self._instanciate_formset(data=data)
        return self.form_cls.get_data(self.form.cleaned_data)

class FormsetField(forms.Field):
    widget = FormsetInput
    def __init__(self, form=None, name=None, required=True, widget=None, label=None, initial=None, instance=None):
        self.widget = FormsetInput(form=form, name=name)

        super(FormsetField, self).__init__(required=required, label=label, initial=initial)

    def validate(self, value):
        if value in validators.EMPTY_VALUES and self.required:
            if not (type(value) == list and len(value) == 0):
                raise ValidationError(self.error_messages['required'])

class MongoFormFieldGenerator(object):
    """This class generates Django form-fields for mongoengine-fields."""

    def generate(self, field_name, field):
        """Tries to lookup a matching formfield generator (lowercase
        field-classname) and raises a NotImplementedError of no generator
        can be found.
        """
        if hasattr(self, 'generate_%s' % field.__class__.__name__.lower()):
            return getattr(self, 'generate_%s' % \
                field.__class__.__name__.lower())(field_name, field)
        else:
            raise NotImplementedError('%s is not supported by MongoForm' % \
                field.__class__.__name__)

    def generate_stringfield(self, field_name, field):
        if field.regex:
            return forms.CharField(
                regex=field.regex,
                required=field.required,
                min_length=field.min_length,
                max_length=field.max_length,
                initial=field.default
            )
        elif field.choices:
            choices = tuple(field.choices)
            if not isinstance(field.choices[0], (tuple, list)):
                choices = zip(choices, choices)
            return forms.ChoiceField(
                required=field.required,
                initial=field.default,
                choices=choices
            )
        elif field.max_length is None:
            return forms.CharField(
                required=field.required,
                initial=field.default,
                min_length=field.min_length,
                widget=forms.Textarea
            )
        else:
            return forms.CharField(
                required=field.required,
                min_length=field.min_length,
                max_length=field.max_length,
                initial=field.default
            )

    def generate_emailfield(self, field_name, field):
        return forms.EmailField(
            required=field.required,
            min_length=field.min_length,
            max_length=field.max_length,
            initial=field.default
        )

    def generate_urlfield(self, field_name, field):
        return forms.URLField(
            required=field.required,
            min_length=field.min_length,
            max_length=field.max_length,
            initial=field.default
        )

    def generate_intfield(self, field_name, field):
        return forms.IntegerField(
            required=field.required,
            min_value=field.min_value,
            max_value=field.max_value,
            initial=field.default
        )

    def generate_floatfield(self, field_name, field):
        return forms.FloatField(
            required=field.required,
            min_value=field.min_value,
            max_value=field.max_value,
            initial=field.default
        )

    def generate_decimalfield(self, field_name, field):
        return forms.DecimalField(
            required=field.required,
            min_value=field.min_value,
            max_value=field.max_value,
            initial=field.default
        )

    def generate_booleanfield(self, field_name, field):
        return forms.BooleanField(
            required=field.required,
            initial=field.default
        )

    def generate_datetimefield(self, field_name, field):
        return forms.DateTimeField(
            required=field.required,
            initial=field.default
        )

    def generate_referencefield(self, field_name, field):
        return ReferenceField(field.document_type.objects)

    def generate_listfield(self, field_name, field):
        if isinstance(field.field, StringField):
            return FormsetField(
                form=StringForm,
                name=field_name,
            )
        elif isinstance(field.field, EmbeddedDocumentField):
            # avoid circular dependencies
            from forms import MongoFormMetaClass, MongoForm
            return FormsetField(
                form=MongoFormMetaClass(
                    '%sForm'%field.field.document_type_obj.__name__,
                    (MongoForm, MixinEmbeddedForm),
                    {
                        'Meta': type('Meta', tuple(), {'document': field.field.document_type_obj})
                    }
                ),
                name=field_name,
            )
        else:
            raise NotImplementedError('This Listfield is not supported by MongoForm yet')

