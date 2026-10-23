from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict
from models import UserRole, AppointmentStatus
from datetime import date as DateType

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
    description: Optional[str] = None
    title: Optional[str] = None
    duration_minutes: Optional[int] = None
    price: Optional[int] = None


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
    personal_data_checkbox: bool
    portfolio_checkbox: bool

class UserResponse(BaseModel):
    first_name: str
    username: str

class AppointmentResponse(BaseModel):
    id: int
    client_id: int
    service_id: int
    client: UserResponse
    slot_id: int
    status: AppointmentStatus
    created_at: datetime
    service: ServiceResponse
    slot: SlotResponse
    personal_data_checkbox: bool
    portfolio_checkbox: bool
    model_config = ConfigDict(from_attributes=True)


class TopServiceItem(BaseModel):
    service_name: str
    total_ordered: int
    completed_count: int

class DailyStatsItem(BaseModel):
    date: DateType  
    total_booked: int
    completed_count: int

class AdminStatsResponse(BaseModel):
    period: str
    total_appointments: int
    completed_appointments: int
    cancelled_appointments: int
    waiting_appointments: int
    total_revenue: float
    top_services: List[TopServiceItem]
    daily_stats: List[DailyStatsItem]