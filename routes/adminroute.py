from datetime import datetime, timedelta
from typing import List
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from models import User, Service, ScheduleSlot, Appointment, AppointmentStatus
from schemas import (
    ServiceCreate, ServiceUpdate, ServiceResponse,
    SlotCreate, SlotResponse, AppointmentResponse, AdminStatsResponse
)
from dependencies import get_db, get_current_admin
from bot_instance import bot

router = APIRouter(prefix="/api/admin", tags=["Admin"])


@router.get("/appointments/coming", response_model=List[AppointmentResponse])
async def get_upcoming_appointments(
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin)
):
    stmt = (
        select(Appointment)
        .join(ScheduleSlot)
        .join(Appointment.client)
        .options(selectinload(Appointment.service), selectinload(Appointment.slot), selectinload(Appointment.client))
        .where(
            Appointment.status == AppointmentStatus.BOOKED,
            ScheduleSlot.datetime_start >= datetime.now()
        )
        .order_by(ScheduleSlot.datetime_start)
    )
    res = await db.execute(stmt)
    return res.scalars().all()

@router.get("/schedule/", response_model=List[SlotResponse])
async def get_available_slots(db: AsyncSession = Depends(get_db)):
    now = datetime.now()
    stmt = (
        select(ScheduleSlot)
        .where(ScheduleSlot.datetime_start >= now)
        .order_by(ScheduleSlot.datetime_start)
    )
    result = await db.execute(stmt)
    return result.scalars().all()

@router.post("/appointments/{appointment_id}/cancel")
async def cancel_by_admin(
    appointment_id: int,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin)
):
    """Отмена записи мастером с оповещением клиента."""
    stmt = (
        select(Appointment)
        .options(selectinload(Appointment.slot), selectinload(Appointment.service), selectinload(Appointment.client))
        .where(Appointment.id == appointment_id)
    )
    res = await db.execute(stmt)
    appointment = res.scalar_one_or_none()

    if not appointment:
        raise HTTPException(status_code=404, detail="Запись не найдена")

    appointment.status = AppointmentStatus.CANCELLED_BY_ADMIN
    appointment.slot.is_available = True
    await db.commit()

    try:
        await bot.send_message(
            chat_id=appointment.client_id,
            text=(
                f"❌ **Ваша запись отменена мастером**\n\n"
                f"Услуга: {appointment.service.title}\n"
                f"Время: {appointment.slot.datetime_start.strftime('%d.%m.%Y %H:%M')}\n\n"
                f"Вы можете выбрать другое удобное время в приложении."
            )
        )
    except Exception as e:
        print(f"Ошибка уведомления клиента: {e}")

    return {"status": "ok", "message": "Запись отменена, клиент уведомлен"}

@router.delete('/schedule/slots/{slot_id}/delete')
async def delete_slot(
    slot_id:int,
    db: AsyncSession = Depends(get_db),
    
):
    stmt =(
        select(ScheduleSlot)
        .where(ScheduleSlot.id == slot_id)
    )
    res = await db.execute(stmt)
    slot = res.scalar_one_or_none()
    if not slot:
        raise HTTPException(status_code=404, detail="Слот не найден")
    await db.delete(slot)
    await db.commit()
    return

@router.post("/schedule/slots", response_model=List[SlotResponse])
async def create_schedule_slots(
    payload: SlotCreate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin)
):
    """Добавить новые слоты времени."""
    created_slots = []
    for dt in payload.datetimes:
        slot = ScheduleSlot(datetime_start=dt, is_available=True)
        db.add(slot)
        created_slots.append(slot)
    
    await db.commit()
    for slot in created_slots:
        await db.refresh(slot)
    return created_slots


@router.post("/services", response_model=ServiceResponse)
async def create_service(
    payload: ServiceCreate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin)
):
    service = Service(**payload.model_dump())
    db.add(service)
    await db.commit()
    await db.refresh(service)
    return service


@router.put("/services/{service_id}", response_model=ServiceResponse)
async def update_service(
    service_id: int,
    payload: ServiceUpdate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin)
):
    service = await db.get(Service, service_id)
    if not service:
        raise HTTPException(status_code=404, detail="Услуга не найдена")

    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(service, key, value)

    await db.commit()
    await db.refresh(service)
    return service
@router.delete("/services/delete/{service_id}")
async def update_service(
    service_id: int,
    db: AsyncSession = Depends(get_db),
):
    
    stmt =(
        select(Service)
        .where(Service.id == service_id)
    )
    res = await db.execute(stmt)
    service = res.scalar_one_or_none()
    if not service:
        raise HTTPException(status_code=404, detail="Слот не найден")
    service.is_active = False
    await db.commit()
    await db.refresh(service)
    return


@router.get("/stats", response_model=AdminStatsResponse)
async def get_admin_stats(
    period: str = Query("week", enum=["week", "month"]),
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin)
):
    """Статистика за неделю или месяц."""
    now = datetime.now()
    start_date = now - timedelta(days=7 if period == "week" else 30)

    total_q = await db.execute(
        select(func.count(Appointment.id)).where(Appointment.created_at >= start_date)
    )
    total_appointments = total_q.scalar() or 0

    completed_q = await db.execute(
        select(func.count(Appointment.id)).where(
            Appointment.created_at >= start_date,
            Appointment.status == AppointmentStatus.COMPLETED
        )
    )
    completed_appointments = completed_q.scalar() or 0

    cancelled_q = await db.execute(
        select(func.count(Appointment.id)).where(
            Appointment.created_at >= start_date,
            Appointment.status.in_([AppointmentStatus.CANCELLED_BY_CLIENT, AppointmentStatus.CANCELLED_BY_ADMIN])
        )
    )
    cancelled_appointments = cancelled_q.scalar() or 0

    revenue_q = await db.execute(
        select(func.sum(Service.price))
        .join(Appointment, Appointment.service_id == Service.id)
        .where(
            Appointment.created_at >= start_date,
            Appointment.status == AppointmentStatus.COMPLETED
        )
    )
    total_revenue = revenue_q.scalar() or 0.0

    return AdminStatsResponse(
        period=period,
        total_appointments=total_appointments,
        completed_appointments=completed_appointments,
        cancelled_appointments=cancelled_appointments,
        total_revenue=float(total_revenue)
    )