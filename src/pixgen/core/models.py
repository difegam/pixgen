from typing import Annotated

from pydantic import StringConstraints

# Regular expression pattern for validating model IDs
model_id_regex = r"^[a-z0-9][a-z0-9-]*/.+$"  # namespace/model-name

type ModelId = Annotated[
    str,
    StringConstraints(pattern=model_id_regex, min_length=3),
]
