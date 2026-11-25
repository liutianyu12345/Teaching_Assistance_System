import hashlib
import math
from collections import Counter

from pydantic import BaseModel, ConfigDict, Field, model_validator
from typing import Literal


class Circuit(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    model: Literal["ohm_fixed_r"] = "ohm_fixed_r"
    resistance: float = Field(default=10, gt=0, le=10000)
    minimum: float = Field(default=0, ge=0)
    maximum: float = Field(default=6, gt=0, le=24)
    initial: float = 1
    voltage_unit: Literal["V"] = "V"
    current_unit: Literal["A"] = "A"
    resistance_unit: Literal["Ω"] = "Ω"

    @model_validator(mode="after")
    def consistent(self):
        if not self.minimum < self.maximum or not self.minimum <= self.initial <= self.maximum:
            raise ValueError("初始电压必须位于有效的调节区间")
        return self

    def reading(self, voltage):
        if not self.minimum <= voltage <= self.maximum:
            raise ValueError("电压超出教师设定范围")
        return round(voltage / self.resistance, 8)


def embedding(value):
    chars = "".join(value.lower().split())
    counts = Counter(chars[i : i + 2] for i in range(len(chars)))
    vector = [0.0] * 128
    for token, weight in counts.items():
        index = int.from_bytes(hashlib.blake2s(token.encode(), digest_size=2).digest(), "big") % 128
        vector[index] += weight
    norm = math.sqrt(sum(v * v for v in vector)) or 1
    return [v / norm for v in vector]
