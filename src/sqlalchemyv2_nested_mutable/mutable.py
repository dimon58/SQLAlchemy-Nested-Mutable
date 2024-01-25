from __future__ import annotations

from typing import Iterable
from typing import List
from typing import TypeVar

import sqlalchemy as sa
from pydantic import BaseModel
from sqlalchemy import Dialect
from sqlalchemy.ext.mutable import Mutable
from sqlalchemy.sql.type_api import TypeEngine
from typing_extensions import Self

from ._typing import _T
from .trackable import TrackedDict
from .trackable import TrackedList
from .trackable import TrackedObject
from .trackable import TrackedPydanticBaseModel

_P = TypeVar("_P", bound='MutablePydanticBaseModel')


class MutableList(TrackedList, Mutable, List[_T]):
    """
    A mutable list that tracks changes to itself and its children.

    Used as top-level mapped object. e.g.

        aliases: Mapped[list[str]] = mapped_column(MutableList.as_mutable(ARRAY(String(128))))
        schedule: Mapped[list[list[str]]] = mapped_column(MutableList.as_mutable(ARRAY(sa.String(128), dimensions=2)))
    """

    @classmethod
    def coerce(cls, key, value):
        return value if isinstance(value, cls) else cls(value)

    def __init__(self, __iterable: Iterable[_T] = []):
        super().__init__(TrackedObject.make_nested_trackable(__iterable, self))


class MutableDict(TrackedDict, Mutable):
    @classmethod
    def coerce(cls, key, value):
        return value if isinstance(value, cls) else cls(value)

    def __init__(self, source=(), **kwds):
        super().__init__(TrackedObject.make_nested_trackable(dict(source, **kwds), self))


class PydanticType(sa.types.TypeDecorator, TypeEngine[_P]):
    """
    Inspired by https://gist.github.com/imankulov/4051b7805ad737ace7d8de3d3f934d6b
    """

    cache_ok = True
    impl = sa.types.JSON

    def __init__(self, pydantic_type: type[_P], sqltype: TypeEngine[_T] | None = None):
        super().__init__()
        if not issubclass(pydantic_type, BaseModel):
            raise ValueError(f"pydantic_type should be subclass of BaseModel not {type(pydantic_type)}")

        self.pydantic_type = pydantic_type
        self.sqltype = sqltype

    def load_dialect_impl(self, dialect):
        from sqlalchemy.dialects.postgresql import JSONB

        if self.sqltype is not None:
            return dialect.type_descriptor(self.sqltype)

        if dialect.name == "postgresql":
            return dialect.type_descriptor(JSONB())
        return dialect.type_descriptor(sa.JSON())

    def __repr__(self):
        # NOTE: the `__repr__` is used by Alembic to generate the migration script.
        return f"{self.__class__.__name__}({self.pydantic_type.__name__})"

    def process_bind_param(self, value: _P | None, dialect: Dialect):
        return value.model_dump(mode="json") if value else None

    def process_result_value(self, value, dialect: Dialect) -> _P | None:
        return self.pydantic_type.model_validate(value) if value else None


class MutablePydanticBaseModel(TrackedPydanticBaseModel, Mutable):
    @classmethod
    def coerce(cls, key, value) -> Self:
        return value if isinstance(value, cls) else cls.model_validate(value)

    def dict(self, *args, **kwargs):
        res = super().model_dump(*args, **kwargs)
        res.pop('_parents', None)
        return res

    @classmethod
    def as_mutable(cls, sqltype: TypeEngine[_T] | None = None) -> TypeEngine[Self]:
        return super().as_mutable(PydanticType(cls, sqltype))
