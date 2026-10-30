from datetime import date, datetime
from types import SimpleNamespace

from sqlalchemy.inspection import inspect as sqlalchemy_inspect


class DTO(SimpleNamespace):
    """Small attribute-access object compatible with existing bot handlers."""

    def __bool__(self):
        return True


def encode_value(value):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value

    if isinstance(value, datetime):
        return {'__type__': 'datetime', 'value': value.isoformat()}

    if isinstance(value, date):
        return {'__type__': 'date', 'value': value.isoformat()}

    if isinstance(value, dict):
        return {str(key): encode_value(item) for key, item in value.items()}

    if isinstance(value, (list, tuple, set)):
        return [encode_value(item) for item in value]

    if isinstance(value, DTO):
        return {
            '__type__': 'model',
            **{key: encode_value(item) for key, item in vars(value).items()},
        }

    try:
        mapper = sqlalchemy_inspect(value).mapper
    except (TypeError, AttributeError):
        raise TypeError(f'Unsupported internal API value: {type(value).__name__}')

    return {
        '__type__': 'model',
        '__model__': mapper.class_.__name__,
        **{
            column.key: encode_value(getattr(value, column.key))
            for column in mapper.columns
        },
    }


def decode_value(value):
    if isinstance(value, list):
        return [decode_value(item) for item in value]

    if not isinstance(value, dict):
        return value

    value_type = value.get('__type__')

    if value_type == 'datetime':
        return datetime.fromisoformat(value['value'])

    if value_type == 'date':
        return date.fromisoformat(value['value'])

    if value_type == 'model':
        return DTO(**{
            key: decode_value(item)
            for key, item in value.items()
            if not key.startswith('__')
        })

    return {key: decode_value(item) for key, item in value.items()}
