from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict
from models import UserRole, AppointmentStatus


class TelegramAuthSchema(BaseModel):
    init_data: str  


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: UserRole


class ServiceBase(BaseModel):
    title: str
    description: Optional[str] = None
    duration_minutes: int = 60
    price: float


class ServiceCreate(ServiceBase):
    pass


class ServiceUpdate(ServiceBase):
    is_active: Optional[bool] = None


class ServiceResponse(ServiceBase):
    id: int
    is_active: bool
    model_config = ConfigDict(from_attributes=True)


class SlotCreate(BaseModel):
    datetimes: List[datetime] 

class SlotResponse(BaseModel):
    id: int
    datetime_start: datetime
    is_available: bool
    model_config = ConfigDict(from_attributes=True)


class AppointmentCreate(BaseModel):
    service_id: int
    slot_id: int


class AppointmentResponse(BaseModel):
    id: int
    client_id: int
    service_id: int
    slot_id: int
    status: AppointmentStatus
    created_at: datetime
    service: ServiceResponse
    slot: SlotResponse
    model_config = ConfigDict(from_attributes=True)


class AdminStatsResponse(BaseModel):
    period: str
    total_appointments: int
    completed_appointments: int
    cancelled_appointments: int
    total_revenue: float