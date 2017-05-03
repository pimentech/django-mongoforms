# -*- coding:utf-8 -*-

from django import forms
from django.conf import settings
from django.forms.formsets import (formset_factory, BaseFormSet, TOTAL_FORM_COUNT, INITIAL_FORM_COUNT,
                                MAX_NUM_FORM_COUNT, DEFAULT_MAX_NUM, DELETION_FIELD_NAME, ORDERING_FIELD_NAME)
from django.forms.fields import IntegerField, BooleanField
from django.forms.util import ErrorList
from django.template import Context, Template
from django.utils.encoding import smart_unicode
from django.utils.translation import ugettext as _
from bson.errors import InvalidId
from bson.objectid import ObjectId
from mongoengine import StringField, EmbeddedDocumentField, ObjectIdField, IntField, ReferenceField as Mongoengine_ReferenceField
from mongoforms.utils import mongo_to_dict


class ReferenceWidget(forms.Select):
    def render(self, name, value, attrs=None, choices=()):
        try:
            value = value.id
        except:
            pass
        return super(ReferenceWidget, self).render(name, value, attrs, choices)


class ReferenceField(forms.ChoiceField):
    """
    Reference field for mongo forms. Inspired by `django.forms.models.ModelChoiceField`.
    """
    widget=ReferenceWidget
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

        self._choices = [('', '----')] + [(obj.pk, smart_unicode(obj)) for obj in self.queryset]
        return self._choices

    choices = property(_get_choices, forms.ChoiceField._set_choices)

    def clean(self, value):
        try:
            id_field = self.queryset._document._meta.get('id_field', 'id')
            if isinstance(self.queryset._document._fields[id_field], ObjectIdField):
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


class BaseReferenceForm(StringForm):

    @classmethod
    def format_initial(cls, initial):
        if initial:
            return [{'da_string': i.id} for i in initial if i]

    @classmethod
    def to_python(cls, cleaned_data):
        doc_id = cleaned_data.get('da_string')
        if doc_id:
            return cls.document.objects.get(id=doc_id)


class DictForm(forms.Form):
    key = forms.CharField(required=True)
    value = forms.CharField(required=True)

    @classmethod
    def format_initial(cls, initial):
        if initial:
            return [{'key': k, "value": v } for k, v in initial.iteritems()]

    @classmethod
    def to_python(cls, cleaned_data):
        try:
            return {cleaned_data['key']: cleaned_data['value']}
        except KeyError:
            return {}

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
                return mongo_to_dict(initial)
            except AttributeError:
                return initial

    @classmethod
    def to_python(cls, cleaned_data):
        return cls.Meta.document(**cleaned_data)

    @classmethod
    def format_values(cls, datas):
        return datas


class MixinEmbeddedFormset(MixinEmbeddedForm):

    @classmethod
    def format_initial(cls, initial):
        if initial:
            try:
                return [mongo_to_dict(d) for d in initial]
            except AttributeError:
                return initial

class MongoFormFormSet(BaseFormSet):
    def __init__(self, data=None, files=None, auto_id='id_%s', prefix=None,
                 initial=None, error_class=ErrorList, form_attrs=None):
        self.form_attrs = form_attrs or {}
        super(MongoFormFormSet, self).__init__(data=data, files=files,
            auto_id=auto_id, prefix=prefix, initial=initial, error_class=error_class)

    def _construct_forms(self):
        # instantiate all the forms and put them in self.forms
        self.forms = []
        for i in xrange(min(self.total_form_count(), self.absolute_max)):
            self.forms.append(self._construct_form(i, **self.form_attrs))

    def add_fields(self, form, index):
        """A hook for adding extra fields on to each form instance."""
        if self.can_order:
            # Only pre-fill the ordering field for initial forms.
            if index is not None and index < self.initial_form_count():
                form.fields[ORDERING_FIELD_NAME] = IntegerField(label=_(u'Order'), initial=index+1, required=False, widget=forms.HiddenInput())
            else:
                form.fields[ORDERING_FIELD_NAME] = IntegerField(label=_(u'Order'), required=False, widget=forms.HiddenInput())
        if self.can_delete:
            form.fields[DELETION_FIELD_NAME] = BooleanField(label=_(u'Delete'), required=False)


class FormsetInput(forms.Widget):

    def __init__(self, form=None, form_attrs=None, name='', attrs=None):
        super(FormsetInput, self).__init__(attrs=attrs)
        self.form = None
        self.form_cls = form
        self.form_attrs = form_attrs or {}
        self.name = name
        self.formset = formset_factory(self.form_cls, formset=MongoFormFormSet, extra=0, can_delete=True, can_order=True)

    def _instanciate_formset(self, data=None, initial=None, readonly=False):
        initial = self.form_cls.format_initial(initial)
        self.form = self.formset(data, initial=initial, prefix=self.name, form_attrs=self.form_attrs)
        if readonly:
            self.formset.can_delete = False
            for form in self.form.forms:
                for field_name in form.fields.keys():
                    form.fields[field_name].widget.attrs['readonly'] = "readonly"
                    if form.fields[field_name].widget.attrs.get('class'):
                        form.fields[field_name].widget.attrs['class'] += " disabled"
                    else:
                        form.fields[field_name].widget.attrs['class'] = "disabled"
        if data:
            self.form.is_valid()

    def render(self, name, value, attrs=None):
        if 'bootstrap3' in settings.INSTALLED_APPS:
            return self.render_bootstrap3(name, value, attrs=attrs)
        else:
            return self.render_vanilla(name, value, attrs=attrs)

    def render_vanilla(self, name, value, attrs=None):
        if not self.form:
            self._instanciate_formset(initial=value, readonly=attrs.get('readonly'))

        form_html = self.form.management_form.as_p()
        form_html += '<ul class="formset %s">%s</ul>' % (self.name,
         ''.join(['<li><ul>%s</ul></li>' % f.as_ul() for f in self.form.forms]))

        if attrs.get('readonly'):
            return form_html
        name_as_funcname = self.name.replace('-', '_')
        management_javascript = """
        <a href="#add_%s" id="add_%s">Add an entry</a>
        <script type="text/javascript">
          function add_form_%s(src_form, str_id, append_to) {
            var num = parseInt($('#id_'+str_id+'-%s').val() || 0);
            $('#id_'+str_id+'-%s').val(num+1);

            var html = $(src_form).html().replace(/%s-__prefix__/g, '%s-'+num);
            $('<li class="list-group-item">'+html+'</li>').appendTo($(append_to));
            if($('input#id_%s-'+num+'-%s').length>0){
              $('input#id_%s-'+num+'-%s').val(num+1);
            }
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
               self.name, self.name,
               self.name, ORDERING_FIELD_NAME, self.name, ORDERING_FIELD_NAME,
               self.name, name_as_funcname, self.name, self.name, self.name)
        empty_form = '<div id="empty_%s" style="display: none;">' \
                     '<li><ul>%s</ul></li></div>' % \
                      (self.name, self.form._get_empty_form(**self.form_attrs).as_ul())

        return form_html + empty_form + management_javascript

    def render_bootstrap3(self, name, value, attrs=None):
        if not self.form:
            self._instanciate_formset(initial=value, readonly=attrs.get('readonly'))

        form_html = self.form.management_form.as_p()
        form_html += '<ul class="list-group formset %s">%s</ul>' % (self.name,
            Template('{% load bootstrap3 %}{% for f in form.forms %}<li id="anchor_{{ name }}-{{ forloop.counter0 }}" class="list-group-item anchor">{% bootstrap_form f %}</li>{% endfor %}').render(Context({'form': self.form, 'name': self.attrs['id']})))
        if attrs.get('readonly'):
            return form_html

        name_as_funcname = self.name.replace('-', '_')
        button_plus_one = """
        <a class="btn btn-primary btn-xs" href="#add_%s" id="add_%s" title="Add an entry">
            <span class="glyphicon glyphicon-plus"></span>
        </a>
        """ % (self.name, self.name)
        management_javascript = """
        <script type="text/javascript">
          function add_form_%s(src_form, str_id, append_to) {
            var num = parseInt($('#id_'+str_id+'-%s').val());
            $('#id_'+str_id+'-%s').val(num+1);

            var html = $(src_form).html().replace(/%s-__prefix__/g, '%s-'+num);
            $('<li class="list-group-item anchor">'+html+'</li>').appendTo($(append_to));
            if($('input#id_%s-'+num+'-%s').length>0){
              $('input#id_%s-'+num+'-%s').val(num+1);
            }
            return false;
          }
          $(document).ready(function(){
            $('a#add_%s').click(function(event){
              add_form_%s('#empty_%s', '%s', 'ul.%s');
              return false;
            });
          });
        </script>
        """ % (name_as_funcname, TOTAL_FORM_COUNT, TOTAL_FORM_COUNT,
               self.name, self.name,
               self.name, ORDERING_FIELD_NAME, self.name, ORDERING_FIELD_NAME,
               self.name, name_as_funcname, self.name, self.name, self.name)
        t = Template('{% load bootstrap3 %}'+
            '<div id="empty_%s" style="display: none;">'% self.name +
            '{% bootstrap_form form %}</div>' )
        c = Context({'form': self.form._get_empty_form(**self.form_attrs)})
        empty_form = t.render(c)
        return button_plus_one + management_javascript + form_html + empty_form + button_plus_one

    def value_from_datadict(self, data, files, name):
        """
        Given a dictionary of data and this widget's name, returns the value
        of this widget. Returns None if it's not provided.
        """
        self._instanciate_formset(data=data)
        values = []
        ordering = []

        for index in range(0, self.form.total_form_count()):

            subform_prefix = self.form.prefix + u'-' + unicode(index) + u'-'
            cleaned_data = {}
            for field_name, field in self.form.forms[index].fields.items():
                value = field.widget.value_from_datadict(data, None, subform_prefix+field_name)
                if value:
                    cleaned_data[field_name] = field.to_python(value)

            if not cleaned_data.get(DELETION_FIELD_NAME):
                if self.formset.can_order and ORDERING_FIELD_NAME in cleaned_data:
                    ordering.append(int(cleaned_data.pop(ORDERING_FIELD_NAME)))

                values.append(self.form_cls.to_python(cleaned_data))

        # TODO: fixer le pb avec ordering qui ne contient pas les elements nouvellement créés
        if ordering:
            values = sorted(values, cmp=lambda v1, v2: ordering[values.index(v1)] - ordering[values.index(v2)])

        return self.form_cls.format_values(values)


class FormsetField(forms.Field):
    widget_cls = FormsetInput
    def __init__(self, form=None, name=None, required=True, widget=None,
                 label=None, initial=None, instance=None, help_text=None, form_attrs=None):
        self.form_cls = form
        self.form_attrs = form_attrs or {}
        self.widget = self.widget_cls(form=form, form_attrs=form_attrs, name=name, **(self.get_widget_extra_args()))

        super(FormsetField, self).__init__(required=required, label=label,
                                           initial=initial, help_text=help_text)

    def clean(self, value):
        datas = self.form_cls.format_initial(value)
        if datas:
            index = 1
            for data in datas:
                for field_name, field in data.items():
                    if isinstance(field, list):
                        management_data = {
                            field_name + '-' + TOTAL_FORM_COUNT: len(field),
                            field_name + '-' + INITIAL_FORM_COUNT: 0,
                            field_name + '-' + MAX_NUM_FORM_COUNT: DEFAULT_MAX_NUM
                        }
                        data.update(management_data)
                        if self.form_cls.base_fields[field_name].form_cls is StringForm:
                            for idx, obj in enumerate(field):
                                data[field_name + '-' + str(idx) +'-da_string'] = obj
                        else:
                            for idx, obj in enumerate(field):
                                for k, v in obj.items():
                                    data[field_name + '-' + str(idx) +'-' + k] = v
                    elif isinstance(field, dict):
                        data.update({
                            field_name + '-' + TOTAL_FORM_COUNT: len(field.keys()),
                            field_name + '-' + INITIAL_FORM_COUNT: 0,
                            field_name + '-' + MAX_NUM_FORM_COUNT: DEFAULT_MAX_NUM
                        })
                f = self.form_cls(data, **self.form_attrs)
                if not f.is_valid():
                    raise forms.ValidationError(['%s %s : %s' % (field_name, index, errors[0]) for field_name, errors in f.errors.items()])
                index += 1
        return value

    def get_widget_extra_args(self):
        return {}


class FormInput(forms.Widget):
    def __init__(self, form=None, name='', attrs=None):
        super(FormInput, self).__init__(attrs=attrs)
        self.form = None
        self.form_cls = form
        self.name = name

    def _instanciate_form(self, data=None, initial=None, readonly=False):
        initial = self.form_cls.format_initial(initial)
        self.form = self.form_cls(data, initial=initial, prefix=self.name)
        if readonly:
            for field_name in self.form.fields.keys():
                self.form.fields[field_name].widget.attrs['readonly'] = "readonly"
                if self.form.fields[field_name].widget.attrs.get('class'):
                    self.form.fields[field_name].widget.attrs['class'] += " disabled"
                else:
                    self.form.fields[field_name].widget.attrs['class'] = "disabled"
        if data:
            self.form.is_valid()

    def render(self, name, value, attrs=None):
        if 'bootstrap3' in settings.INSTALLED_APPS:
            return self.render_bootstrap3(name, value, attrs=attrs)
        else:
            return self.render_vanilla(name, value, attrs=attrs)

    def render_vanilla(self, name, value, attrs=None):
        if not self.form:
            self._instanciate_form(initial=value, readonly=attrs.get('readonly'))
        return self.form.as_ul()

    def render_bootstrap3(self, name, value, attrs=None):
        if not self.form:
            self._instanciate_form(initial=value, readonly=attrs.get('readonly'))
        return Template('{% load bootstrap3 %}{% bootstrap_form form %}</li>').render(Context({'form': self.form}))

    def value_from_datadict(self, data, files, name):
        """
        Given a dictionary of data and this widget's name, returns the value
        of this widget. Returns None if it's not provided.
        """
        self._instanciate_form(data=data)

        subform_prefix = self.form.prefix + u'-'
        cleaned_data = {}
        for field_name, field in self.form.fields.items():
            value = field.widget.value_from_datadict(data, None, subform_prefix+field_name)
            if value:
                cleaned_data[field_name] = field.to_python(value)

        values = self.form_cls.to_python(cleaned_data)

        return self.form_cls.format_values(values)


class FormField(forms.Field):
    def __init__(self, form=None, name=None, required=True, widget=None,
                 label=None, initial=None, instance=None, help_text=None):
        self.widget = FormInput(form=form, name=name)

        super(FormField, self).__init__(required=required, label=label,
                                           initial=initial, help_text=help_text)


class MongoFormFieldGenerator(object):
    """This class generates Django form-fields for mongoengine-fields."""

    def __init__(self, fields, overriden_fields=None, exclude=None):
        self.fields = fields
        if exclude is None:
            exclude = []
        if overriden_fields is None:
            overriden_fields = []
        self.exclude = exclude
        self.overriden_fields = overriden_fields

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
        if callable(field.default):
            default = field.default()
        else:
            default = field.default

        return {
            'required': field.required,
            'initial': default,
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
        if isinstance(field.field, (StringField, IntField)):
            return FormsetField(
                form=StringForm,
                name=field_name,
                **(self.get_base_attrs(field))
            )
        if isinstance(field.field, Mongoengine_ReferenceField):
            return FormsetField(
                form=type(field.field.document_type.__name__+ 'ReferenceForm', (BaseReferenceForm,), {'da_string': ReferenceField(field.field.document_type.objects, label=" ", required=False), 'document': field.field.document_type})
,
                name=field_name,
                **(self.get_base_attrs(field))
            )
        elif isinstance(field.field, EmbeddedDocumentField):
            ## avoid circular dependencies
            #from forms import mongoform_factory
            return FormsetField(
                form=self.get_form_factory()(
                    field.field.document_type_obj,
                    extra_bases=(MixinEmbeddedFormset, ),
                    extra_meta={
                        'fields': tuple([f.split('__', 1)[1] for f in self.fields if f.startswith(field_name+'__')]),
                        'exclude': tuple([f.split('__', 1)[1] for f in self.exclude if f.startswith(field_name+'__')]),
                        'formfield_generator': self.__class__
                    },
                    extra_attrs=dict([(f[0].split('__', 1)[1], f[1]) for f in self.overriden_fields if f[0].startswith(field_name+'__')])
                ),
                name=field_name,
                **(self.get_base_attrs(field))
            )
        else:
            raise NotImplementedError('This Listfield is not supported by MongoForm yet')

    def generate_embeddeddocumentfield(self, field_name, field):
        #from forms import mongoform_factory
        extra_attrs = self.get_base_attrs(field)
        extra_attrs.update(dict([(f[0].split('__', 1)[1], f[1]) for f in self.overriden_fields if f[0].startswith(field_name+'__')]))
        return FormField(
            form=self.get_form_factory()(field.document_type_obj,
                extra_bases=(MixinEmbeddedForm, ),
                extra_attrs=extra_attrs,
                extra_meta={
                    'fields': tuple([f.split('__', 1)[1] for f in self.fields if f.startswith(field_name+'__')]),
                    'exclude': tuple([f.split('__', 1)[1] for f in self.exclude if f.startswith(field_name+'__')]),
                    'formfield_generator': self.__class__
                },
            ),
            name=field_name,
            **(self.get_base_attrs(field))
        )

    def get_form_factory(self):
        from forms import mongoform_factory
        return mongoform_factory

