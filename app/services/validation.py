from pydantic import BaseModel, ValidationError

from app.core.exceptions import invalid_response


def parse_collection[T: BaseModel](payload: dict, key: str, model: type[T]) -> list[T]:
    rows = payload.get(key)
    if not isinstance(rows, list):
        raise invalid_response()
    try:
        return [model.model_validate(row) for row in rows]
    except (ValidationError, TypeError, ValueError):
        raise invalid_response() from None
