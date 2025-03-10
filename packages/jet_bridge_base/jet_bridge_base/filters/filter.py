from jet_bridge_base.utils.classes import is_instance_or_subclass
from jet_bridge_base.utils.queryset import get_session_engine
from sqlalchemy import Unicode, and_, or_
from sqlalchemy.dialects.postgresql import JSON, ENUM
from sqlalchemy.sql import sqltypes
from six import string_types

from jet_bridge_base.fields import field, CharField, BooleanField
from jet_bridge_base.filters import lookups

EMPTY_VALUES = ([], (), {}, None)


def safe_startswith(column, value):
    field_type = column.property.columns[0].type if hasattr(column, 'property') else column.type

    if is_instance_or_subclass(field_type, (ENUM, sqltypes.NullType)):
        return column.cast(Unicode).ilike('{}%'.format(value))
    else:
        return column.ilike('{}%'.format(value))


def safe_endswith(column, value):
    field_type = column.property.columns[0].type if hasattr(column, 'property') else column.type

    if is_instance_or_subclass(field_type, (ENUM, sqltypes.NullType)):
        return column.cast(Unicode).ilike('%{}'.format(value))
    else:
        return column.ilike('%{}'.format(value))


def safe_icontains(column, value):
    field_type = column.property.columns[0].type if hasattr(column, 'property') else column.type

    if is_instance_or_subclass(field_type, (ENUM, sqltypes.NullType)):
        return column.cast(Unicode).ilike('%{}%'.format(value))
    else:
        return column.ilike('%{}%'.format(value))


def json_icontains(column, value):
    field_type = column.property.columns[0].type if hasattr(column, 'property') else column.type

    if is_instance_or_subclass(field_type, (JSON, sqltypes.NullType)) or not hasattr(column, 'astext'):
        return column.cast(Unicode).ilike('%{}%'.format(value))
    else:
        return column.astext.ilike('%{}%'.format(value))


def is_null(column, value):
    if value:
        return column.__eq__(None)
    else:
        return column.isnot(None)


def is_empty(column, value):
    field_type = column.property.columns[0].type if hasattr(column, 'property') else column.type

    if is_instance_or_subclass(field_type, sqltypes.String):
        if value:
            return or_(column.__eq__(None), column == '')
        else:
            return and_(column.isnot(None), column != '')
    else:
        return is_null(column, value)


def coveredby(column, value):
    return column.ST_CoveredBy(value)


def safe_not_array(value):
    if isinstance(value, list):
        if len(value):
            return value[0]
        else:
            return ''
    else:
        return value


def safe_array(value):
    if isinstance(value, list):
        return value
    elif isinstance(value, string_types):
        if value != '':
            return value.split(',')
        else:
            return []
    else:
        return [value]


class Filter(object):
    field_class = field
    lookup_operators = {
        lookups.EXACT: {'operator': '__eq__', 'pre_process': lambda x: safe_not_array(x)},
        lookups.GT: {'operator': '__gt__', 'pre_process': lambda x: safe_not_array(x)},
        lookups.GTE: {'operator': '__ge__', 'pre_process': lambda x: safe_not_array(x)},
        lookups.LT: {'operator': '__lt__', 'pre_process': lambda x: safe_not_array(x)},
        lookups.LTE: {'operator': '__le__', 'pre_process': lambda x: safe_not_array(x)},
        lookups.ICONTAINS: {'operator': False, 'func': safe_icontains, 'pre_process': lambda x: safe_not_array(x)},
        lookups.IN: {'operator': 'in_', 'field_class': CharField, 'field_kwargs': {'many': True}, 'pre_process': lambda x: safe_array(x)},
        lookups.STARTS_WITH: {'operator': False, 'func': safe_startswith, 'pre_process': lambda x: safe_not_array(x)},
        lookups.ENDS_WITH: {'operator': False, 'func': safe_endswith, 'pre_process': lambda x: safe_not_array(x)},
        lookups.IS_NULL: {'operator': False, 'func': is_null, 'field_class': BooleanField, 'pre_process': lambda x: safe_not_array(x)},
        lookups.IS_EMPTY: {'operator': False, 'func': is_empty, 'field_class': BooleanField, 'pre_process': lambda x: safe_not_array(x)},
        lookups.JSON_ICONTAINS: {'operator': False, 'func': json_icontains, 'pre_process': lambda x: safe_not_array(x)},
        lookups.COVEREDBY: {'operator': False, 'func': coveredby, 'pre_process': lambda x: safe_not_array(x)}
    }

    def __init__(self, name=None, column=None, lookup=lookups.DEFAULT_LOOKUP, exclude=False):
        self.name = name
        self.column = column
        self.lookup = lookup
        self.exclude = exclude

    def clean_value(self, value):
        return value

    def get_loookup_criterion(self, value):
        lookup_operator = self.lookup_operators[self.lookup]
        operator = lookup_operator['operator']
        pre_process = lookup_operator.get('pre_process')
        post_process = lookup_operator.get('post_process')
        field_class = lookup_operator.get('field_class')
        field_kwargs = lookup_operator.get('field_kwargs', {})
        func = lookup_operator.get('func')

        if pre_process:
            value = pre_process(value)

        if field_class:
            value = field_class(**field_kwargs).to_internal_value(value)

        if post_process:
            value = post_process(value)

        if func:
            if self.exclude:
                return ~func(self.column, value)
            else:
                return func(self.column, value)
        elif callable(operator):
            op = operator(value)

            if self.exclude:
                return ~getattr(self.column, op[0])(op[1])
            else:
                return getattr(self.column, op[0])(op[1])
        else:
            if self.exclude:
                return ~getattr(self.column, operator)(value)
            else:
                return getattr(self.column, operator)(value)

    def apply_lookup(self, qs, value):
        criterion = self.get_loookup_criterion(value)
        return qs.filter(criterion)

    def filter(self, qs, value):
        value = self.clean_value(value)
        if value in EMPTY_VALUES:
            return qs
        return self.apply_lookup(qs, value)
