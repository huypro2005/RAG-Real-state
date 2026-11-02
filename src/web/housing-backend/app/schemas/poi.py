from typing import Literal

from pydantic import BaseModel, ConfigDict

PoiType = Literal["truong_hoc", "benh_vien", "cho"]


class NearbyPoiOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    poi_id: int  # pois.id
    poi_type: str
    name: str
    distance_m: float
