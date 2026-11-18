from typing import Any
from sqlalchemy.orm import DeclarativeBase, declared_attr


class Base(DeclarativeBase):
    id: Any
    __name__: str

    # Generate __tablename__ automatically from lowercase class name if not specified
    @declared_attr.directive
    def __tablename__(cls) -> str:
        return cls.__name__.lower()
