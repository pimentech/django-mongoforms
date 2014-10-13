# -*- coding:utf-8 -*-

from django import forms
from django.conf import settings
from django.forms.formsets import (formset_factory, TOTAL_FORM_COUNT,
                                   DELETION_FIELD_NAME)
from django.template import Context, Template
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
            id_field = self.queryset._document._meta.get('id_field', 'id')
            if isinstance(self.queryset._document._fields[id_field], ObjectId):
                pk_value = ObjectId(value)
            else:
                pk_value = value
            oid = super(ReferenceField, self).clean(pk_value)
            if 'id' in self.queryset._query_obj.query:
                obj = self.queryset.get()
            else:
                obj = self.queryset.get(id=oid)
        except (TypeError, InvalidId, self.queryset._document.DoesNotExist):
            raise forms.ValidationError(self.error_messages['invalid_choice'] % {'value':value})
        return obj


class StringForm(forms.Form):
    da_string = forms.CharField(label=" ", required=True)

    @classmethod
    def format_initial(cls, initial):
        if initial:
            return [{'da_string': i} for i in initial]

    @classmethod
    def to_python(cls, cleaned_data):
        return cleaned_data.get('da_string')

    @classmethod
    def format_values(cls, datas):
        return datas


class DictForm(forms.Form):
    key = forms.CharField(required=True)
    value = forms.CharField(required=True)

    @classmethod
    def format_initial(cls, initial):
        if initial:
            return [{'key': k, "value": v } for k, v in initial.iteritems()]

    @classmethod
    def to_python(cls, cleaned_data):
        return {cleaned_data['key']: cleaned_data['value']}

    @classmethod
    def format_values(cls, datas):
        d = {}
        for dico in datas:
            d.update(dico)
        return d


class MixinEmbeddedForm(object):

    @classmethod
    def format_initial(cls, initial):
        if initial:
            try:
                return [d._data for d in initial]
            except AttributeError:
                return initial

    @classmethod
    def to_python(cls, cleaned_data):
        return cls.Meta.document(**cleaned_data)

    @classmethod
    def format_values(cls, datas):
        return datas

class FormsetInput(forms.Widget):

    def __init__(self, form=None, name='', attrs=None):
        super(FormsetInput, self).__init__(attrs=attrs)
        self.form = None
        self.form_cls = form
        self.name = name
        self.formset = formset_factory(self.form_cls, extra=0, can_delete=True)


    def _instanciate_formset(self, data=None, initial=None):
        initial = self.form_cls.format_initial(initial)
        self.form = self.formset(data, initial=initial, prefix=self.name)
        if data:
            self.form.is_valid()

    def render(self, name, value, attrs=None):
        if 'bootstrap3' in settings.INSTALLED_APPS:
            return self.render_bootstrap3(name, value, attrs=attrs)
        else:
            return self.render_vanilla(name, value, attrs=attrs)

    def render_vanilla(self, name, value, attrs=None):
        if not self.form:
            self._instanciate_formset(initial=value)
        name_as_funcname = self.name.replace('-', '_')
        management_javascript = """
        <a href="#add_%s" id="add_%s">Add an entry</a>
        <script type="text/javascript">
          function add_form_%s(src_form, str_id, append_to) {
            var num = $('#id_'+str_id+'-%s').val();
            $('#id_'+str_id+'-%s').val(parseInt(num)+1);

            var html = $(src_form).html().replace(/__prefix__/g, ''+num);
            $('<li class="list-group-item">'+html+'</li>').appendTo($(append_to));
            return false;
          }
          $(document).ready(function(){
            $('a#add_%s').click(function(event){
              add_form_%s('#empty_%s', '%s', 'ul.%s');
              return false;
            });
          });
        </script>
        """ % (self.name, self.name, name_as_funcname, TOTAL_FORM_COUNT, TOTAL_FORM_COUNT,
               self.name, name_as_funcname, self.name, self.name, self.name)
        empty_form = '<div id="empty_%s" style="display: none;">' \
                     '<li><ul>%s</ul></li></div>' % \
                      (self.name, self.form.empty_form.as_ul())

        form_html = self.form.management_form.as_p()
        form_html += '<ul class="formset %s">%s</ul>' % (self.name,
         ''.join(['<li><ul>%s</ul></li>' % f.as_ul() for f in self.form.forms]))

        return form_html + empty_form + management_javascript

    def render_bootstrap3(self, name, value, attrs=None):
        if not self.form:
            self._instanciate_formset(initial=value)
        name_as_funcname = self.name.replace('-', '_')
        management_javascript = """
        <a href="#add_%s" id="add_%s">Add an entry</a>
        <script type="text/javascript">
          function add_form_%s(src_form, str_id, append_to) {
            var num = $('#id_'+str_id+'-%s').val();
            $('#id_'+str_id+'-%s').val(parseInt(num)+1);

            var html = $(src_form).html().replace(/__prefix__/g, ''+num);
            $('<li class="list-group-item">'+html+'</li>').appendTo($(append_to));
            return false;
          }
          $(document).ready(function(){
            $('a#add_%s').click(function(event){
              add_form_%s('#empty_%s', '%s', 'ul.%s');
              return false;
            });
          });
        </script>
        """ % (self.name, self.name, name_as_funcname, TOTAL_FORM_COUNT, TOTAL_FORM_COUNT,
               self.name, name_as_funcname, self.name, self.name, self.name)
        t = Template('{% load bootstrap3 %}'+
            '<div id="empty_%s" style="display: none;">'% self.name +
            '{% bootstrap_form form %}</div>' )
        c = Context({'form': self.form.empty_form})
        empty_form = t.render(c)

        form_html = self.form.management_form.as_p()
        form_html += '<ul class="list-group formset %s">%s</ul>' % (self.name,
            Template('{% load bootstrap3 %}{% for f in form.forms %}<li class="list-group-item">{% bootstrap_form f %}{% endfor %}</li>').render(Context({'form': self.form})))
        return form_html + empty_form + management_javascript

    def value_from_datadict(self, data, files, name):
        """
        Given a dictionary of data and this widget's name, returns the value
        of this widget. Returns None if it's not provided.
        """
        self._instanciate_formset(data=data)
        values = []

        if self.form.is_valid():
            for form in self.form.forms:
                if not form.cleaned_data.get(DELETION_FIELD_NAME):
                    values.append(self.form_cls.to_python(form.cleaned_data))

        if values:
            return self.form_cls.format_values(values)

        return values

class FormsetField(forms.Field):
    def __init__(self, form=None, name=None, required=True, widget=None,
                 label=None, initial=None, instance=None, help_text=None):
        self.widget = FormsetInput(form=form, name=name)

        super(FormsetField, self).__init__(required=required, label=label,
                                           initial=initial, help_text=help_text)


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

    def get_base_attrs(self, field):
        return {
            'required': field.required,
            'initial': field.default,
            'label': field.verbose_name,
            'help_text': field.help_text
        }

    def generate_stringfield(self, field_name, field):
        if field.regex:
            return forms.CharField(
                regex=field.regex,
                min_length=field.min_length,
                max_length=field.max_length,
                **(self.get_base_attrs(field))
            )
        elif field.choices:
            choices = tuple(field.choices)
            if not isinstance(field.choices[0], (tuple, list)):
                choices = zip(choices, choices)
            return forms.ChoiceField(
                choices=choices,
                **(self.get_base_attrs(field))
            )
        elif field.max_length is None:
            return forms.CharField(
                min_length=field.min_length,
                widget=forms.Textarea,
                **(self.get_base_attrs(field))
            )
        else:
            return forms.CharField(
                min_length=field.min_length,
                max_length=field.max_length,
                **(self.get_base_attrs(field))
            )
    def generate_slugfield(self, field_name, field):
        return forms.SlugField(
            min_length=field.min_length,
            max_length=field.max_length,
            **(self.get_base_attrs(field))
        )

    def generate_emailfield(self, field_name, field):
        return forms.EmailField(
            min_length=field.min_length,
            max_length=field.max_length,
            **(self.get_base_attrs(field))
        )

    def generate_urlfield(self, field_name, field):
        return forms.URLField(
            min_length=field.min_length,
            max_length=field.max_length,
            **(self.get_base_attrs(field))
        )

    def generate_intfield(self, field_name, field):
        return forms.IntegerField(
            min_value=field.min_value,
            max_value=field.max_value,
            **(self.get_base_attrs(field))
        )

    def generate_floatfield(self, field_name, field):
        return forms.FloatField(
            min_value=field.min_value,
            max_value=field.max_value,
            **(self.get_base_attrs(field))
        )

    def generate_decimalfield(self, field_name, field):
        return forms.DecimalField(
            min_value=field.min_value,
            max_value=field.max_value,
            **(self.get_base_attrs(field))
        )

    def generate_booleanfield(self, field_name, field):
        return forms.BooleanField(
            **(self.get_base_attrs(field))
        )

    def generate_datetimefield(self, field_name, field):
        return forms.DateTimeField(
            **(self.get_base_attrs(field))
        )

    def generate_referencefield(self, field_name, field):
        return ReferenceField(
            field.document_type.objects,
            **(self.get_base_attrs(field))
        )

    def generate_dictfield(self, field_name, field):
        return FormsetField(
            form=DictForm,
            name=field_name,
            **(self.get_base_attrs(field))
        )

    def generate_listfield(self, field_name, field):
        if isinstance(field.field, StringField):
            return FormsetField(
                form=StringForm,
                name=field_name,
                **(self.get_base_attrs(field))
            )
        elif isinstance(field.field, EmbeddedDocumentField):
            # avoid circular dependencies
            from forms import mongoform_factory
            return FormsetField(
                form=mongoform_factory(field.field.document_type_obj, extra_bases=(MixinEmbeddedForm, )),
                name=field_name,
                **(self.get_base_attrs(field))
            )
        else:
            raise NotImplementedError('This Listfield is not supported by \
                                      MongoForm yet')

