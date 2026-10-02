from datetime import datetime
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from models import User, Service, ScheduleSlot, Appointment, AppointmentStatus
from schemas import ServiceResponse, SlotResponse, AppointmentCreate, AppointmentResponse
from dependencies import get_db, get_current_user
from bot_instance import bot
from dotenv import load_dotenv
import os
load_dotenv()
ADMIN_TELEGRAM_ID = os.getenv("ADMIN_TELEGRAM_ID")

router = APIRouter(prefix="/api", tags=["Client"])
@router.get("/services", response_model=List[ServiceResponse])
async def get_active_services(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Service).where(Service.is_active == True))
    return result.scalars().all()

@router.get("/schedule/available", response_model=List[SlotResponse])
async def get_available_slots(db: AsyncSession = Depends(get_db)):
    now = datetime.now()
    stmt = (
        select(ScheduleSlot)
        .where(ScheduleSlot.is_available == True, ScheduleSlot.datetime_start >= now)
        .order_by(ScheduleSlot.datetime_start)
    )
    result = await db.execute(stmt)
    return result.scalars().all()

@router.post("/appointments", response_model=AppointmentResponse)
async def create_appointment(
    payload: AppointmentCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    slot = await db.get(ScheduleSlot, payload.slot_id)
    if not slot or not slot.is_available:
        raise HTTPException(status_code=400, detail="Слот недоступен для бронирования")
    
    service = await db.get(Service, payload.service_id)
    if not service or not service.is_active:
        raise HTTPException(status_code=400, detail="Услуга не найдена или неактивна")

    slot.is_available = False

    appointment = Appointment(
        client=user,
        client_id=user.id,
        service_id=service.id,
        slot_id=slot.id,
        status=AppointmentStatus.BOOKED
    )
    db.add(appointment)
    await db.commit()
    await db.refresh(appointment)

    try:
        await bot.send_message(
            chat_id=ADMIN_TELEGRAM_ID,
            text=(
                f"🚨 **Новая запись!**\n\n"
                f"👤 Клиент: {user.first_name} (@{user.username})\n"
                f"💅 Услуга: {service.title}\n"
                f"📅 Дата: {slot.datetime_start.strftime('%d.%m.%Y %H:%M')}"
            )
        )
    except Exception as e:
        print(f"Ошибка отправки уведомления админу: {e}")

    stmt = (
        select(Appointment)
        .options(selectinload(Appointment.service), selectinload(Appointment.slot))
        .where(Appointment.id == appointment.id)
    )
    res = await db.execute(stmt)
    return res.scalar_one()

@router.post("/appointments/{appointment_id}/cancel-by-client")
async def cancel_by_client(
    appointment_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    stmt = (
        select(Appointment)
        .options(selectinload(Appointment.slot), selectinload(Appointment.service))
        .where(Appointment.id == appointment_id, Appointment.client_id == user.id)
    )
    res = await db.execute(stmt)
    appointment = res.scalar_one_or_none()

    if not appointment:
        raise HTTPException(status_code=404, detail="Запись не найдена")

    if appointment.status != AppointmentStatus.BOOKED:
        raise HTTPException(status_code=400, detail="Запись нельзя отменить")

    appointment.status = AppointmentStatus.CANCELLED_BY_CLIENT
    appointment.slot.is_available = True
    await db.commit()

    try:
        await bot.send_message(
            chat_id=ADMIN_TELEGRAM_ID,
            text=(
                f"⚠️ **Клиент отменил запись**\n\n"
                f"👤 Клиент: {user.first_name} (@{user.username})\n"
                f"📅 Время: {appointment.slot.datetime_start.strftime('%d.%m.%Y %H:%M')}\n"
                f"Окно снова свободно для записи!"
            )
        )
    except Exception as e:
        print(f"Ошибка уведомления: {e}")

    return {"status": "ok", "message": "Запись отменена"}

@router.get("/clients/appointments/upcoming", response_model=List[AppointmentResponse])
async def get_upcoming_appointments(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    stmt = (
        select(Appointment)
        .join(ScheduleSlot)
        .options(selectinload(Appointment.service), selectinload(Appointment.slot))
        .where(
            Appointment.status == AppointmentStatus.BOOKED,
            ScheduleSlot.datetime_start >= datetime.now()
        )
        .where(
            Appointment.client_id == user.id
        )
        .order_by(ScheduleSlot.datetime_start)
    )
    res = await db.execute(stmt)
    return res.scalars().all()

