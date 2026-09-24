import enum
from datetime import datetime
from typing import List, Optional

from sqlalchemy import BigInteger, Boolean, DateTime, Enum, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass

class UserRole(str, enum.Enum):
    CLIENT = "CLIENT"
    ADMIN = "ADMIN"


class AppointmentStatus(str, enum.Enum):
    BOOKED = "BOOKED"
    CANCELLED_BY_CLIENT = "CANCELLED_BY_CLIENT"
    CANCELLED_BY_ADMIN = "CANCELLED_BY_ADMIN"
    COMPLETED = "COMPLETED"


class User(Base):
    """Модель пользователя (Клиент / Администратор)"""
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    username: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    first_name: Mapped[str] = mapped_column(String(64), nullable=False)
    phone: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role_enum"),
        default=UserRole.CLIENT,
        nullable=False
    )
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )

    appointments: Mapped[List["Appointment"]] = relationship(
        "Appointment",
        back_populates="client",
        cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} username='{self.username}' role={self.role}>"


class Service(Base):
    """Модель услуги мастеров (например, 'Коррекция бровей')"""
    __tablename__ = "services"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    
    price: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )

    appointments: Mapped[List["Appointment"]] = relationship(
        "Appointment",
        back_populates="service"
    )

    def __repr__(self) -> str:
        return f"<Service id={self.id} title='{self.title}' price={self.price}>"


class ScheduleSlot(Base):
    """Модель временного слота / окна для записи"""
    __tablename__ = "schedule_slots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    
    datetime_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        unique=True,
        index=True,
        nullable=False
    )
    
    is_available: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)

    appointment: Mapped[Optional["Appointment"]] = relationship(
        "Appointment",
        back_populates="slot",
        uselist=False  
    )

    def __repr__(self) -> str:
        return f"<ScheduleSlot id={self.id} start={self.datetime_start} available={self.is_available}>"


class Appointment(Base):
    """Модель записи клиента на прием"""
    __tablename__ = "appointments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    
    client_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    service_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("services.id", ondelete="RESTRICT"),
        nullable=False
    )
    
    slot_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("schedule_slots.id", ondelete="RESTRICT"),
        unique=True, 
        nullable=False
    )
    
    status: Mapped[AppointmentStatus] = mapped_column(
        Enum(AppointmentStatus, name="appointment_status_enum"),
        default=AppointmentStatus.BOOKED,
        nullable=False,
        index=True
    )
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )

    client: Mapped["User"] = relationship("User", back_populates="appointments")
    service: Mapped["Service"] = relationship("Service", back_populates="appointments")
    slot: Mapped["ScheduleSlot"] = relationship("ScheduleSlot", back_populates="appointment")

    def __repr__(self) -> str:
        return f"<Appointment id={self.id} client_id={self.client_id} status={self.status}>"