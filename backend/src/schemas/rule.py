from pydantic import BaseModel, Field
class RuleInput(BaseModel):
    label: str = Field(min_length=2, max_length=160)
    definition: dict = Field(default_factory=dict)
    job_ids: list[int] | None = None
