from datetime import datetime, timedelta
from typing import List
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy import update
from models import User, Service, ScheduleSlot, Appointment, AppointmentStatus
from schemas import (
    ServiceCreate, ServiceUpdate, ServiceResponse,
    SlotCreate, SlotResponse, AppointmentResponse, AdminStatsResponse
)
from dependencies import get_db, get_current_admin
from bot_instance import bot
from datetime import datetime, timezone
from calendar import monthrange
from collections import defaultdict
from sqlalchemy import select, func, case, desc, Date
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

@router.put("/appointments/{appointment_id}/status/done")
async def change_status(
    appointment_id: int,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin)
):
    update_stmt = (
        update(Appointment)
        .where(Appointment.id == appointment_id)
        .values(status="COMPLETED")
    )
    res = await db.execute(update_stmt)
    
    if res.rowcount == 0:
        raise HTTPException(status_code=404, detail="Запись не найдена")
        
    await db.commit()
    return {"status": "success", "message": "Статус успешно обновлен"}
    
@router.delete('/schedule/slots/{slot_id}/delete')
async def delete_slot(
    slot_id:int,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin)
    
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

@router.get("/schedule/slots/{month}")
async def get_slots_per_month(
    month: str, 
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin)
):
    try:
        year_str, month_str = month.split("-")
        year = int(year_str)
        month_int = int(month_str)
        _, days_in_month = monthrange(year, month_int)
        
        start_date = datetime(year, month_int, 1, 0, 0, 0, tzinfo=timezone.utc)
        end_date = datetime(year, month_int, days_in_month, 23, 59, 59, 999999, tzinfo=timezone.utc)
    except (ValueError, IndexError):
        raise HTTPException(
            status_code=400, 
            detail="Неверный формат месяца. Используйте YYYY-MM (например, 2026-10)"
        )

    stmt = (
        select(ScheduleSlot)
        .options(
            selectinload(ScheduleSlot.appointment).options(
                selectinload(Appointment.client),
                selectinload(Appointment.service)
            )
        )
        .where(
            ScheduleSlot.datetime_start >= start_date,
            ScheduleSlot.datetime_start <= end_date
        )
        .order_by(ScheduleSlot.datetime_start)
    )
    
    res = await db.execute(stmt)
    slots = res.scalars().all()
    
    grouped_data = defaultdict(list)
    
    for slot in slots:
        date_key = slot.datetime_start.date().isoformat()
        
        slot_data = {
            "id": slot.id,
            "datetime_start": slot.datetime_start,
            "is_available": slot.is_available,
            "appointment": None
        }
        
        if slot.appointment and slot.appointment.status in (AppointmentStatus.BOOKED, AppointmentStatus.COMPLETED):
            slot_data["appointment"] = {
                "id": slot.appointment.id,
                "status": slot.appointment.status,
                "slot":{
                    "id": slot.id,
                    "datetime_start": slot.datetime_start,
                    "is_available": slot.is_available,
                },
                "client": {
                    "id": slot.appointment.client.id,
                    "first_name": slot.appointment.client.first_name,
                    "username": slot.appointment.client.username,
                } if slot.appointment.client else None,
                "service": {
                    "id": slot.appointment.service.id,
                    "title": slot.appointment.service.title,
                    "price": slot.appointment.service.price,
                    "duration_minutes": slot.appointment.service.duration_minutes
                
                } if slot.appointment.service else None
            }
            
        grouped_data[date_key].append(slot_data)
        
    return grouped_data
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
    """Статистика за текущую неделю (Пн-Вс) или текущий календарный месяц (1-31)."""
    now = datetime.now()

    if period == "week":
        start_date = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=now.weekday())
        end_date = start_date + timedelta(days=6, hours=23, minutes=59, seconds=59)
    else: 
        start_date = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if now.month == 12:
            next_month = now.replace(year=now.year + 1, month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        else:
            next_month = now.replace(month=now.month + 1, day=1, hour=0, minute=0, second=0, microsecond=0)
        
        end_date = next_month - timedelta(seconds=1)

    time_filter = Appointment.created_at.between(start_date, end_date)

    metrics_stmt = (
        select(
            func.count(Appointment.id).label("total"),
            func.count(case((Appointment.status == AppointmentStatus.COMPLETED, 1))).label("completed"),
            func.count(
                case((Appointment.status.in_([
                    AppointmentStatus.CANCELLED_BY_CLIENT, 
                    AppointmentStatus.CANCELLED_BY_ADMIN
                ]), 1))
            ).label("cancelled"),
            func.count(case((Appointment.status == AppointmentStatus.BOOKED, 1))).label("waiting")
        )
        .where(time_filter)
    )
    metrics_res = await db.execute(metrics_stmt)
    general_metrics = metrics_res.mappings().first()

    revenue_q = await db.execute(
        select(func.sum(Service.price))
        .join(Appointment, Appointment.service_id == Service.id)
        .where(
            time_filter,
            Appointment.status == AppointmentStatus.COMPLETED
        )
    )
    total_revenue = revenue_q.scalar() or 0.0

    top_services_stmt = (
        select(
            Service.title.label("service_name"),
            func.count(Appointment.id).label("total_ordered"),
            func.count(case((Appointment.status == AppointmentStatus.COMPLETED, 1))).label("completed_count")
        )
        .join(Service, Appointment.service_id == Service.id)
        .where(time_filter)
        .group_by(Service.id, Service.title)
        .order_by(desc("total_ordered"))
        .limit(4)
    )
    top_res = await db.execute(top_services_stmt)
    top_services = [dict(row) for row in top_res.mappings().all()]

    date_field = func.strftime("%Y-%m-%d", Appointment.created_at)
    
    daily_stmt = (
        select(
            date_field.label("date"),
            func.count(Appointment.id).label("total_booked"),
            func.count(case((Appointment.status == AppointmentStatus.COMPLETED, 1))).label("completed_count")
        )
        .where(time_filter)
        .group_by(date_field)
        .order_by(date_field.asc())
    )
    daily_res = await db.execute(daily_stmt)
    
    daily_stats_db = {row["date"]: row for row in daily_res.mappings().all()}

    daily_stats = []
    current_day = start_date.date()
    end_day = end_date.date()

    while current_day <= end_day:
        date_str = current_day.strftime("%Y-%m-%d")
        
        if date_str in daily_stats_db:
            daily_stats.append({
                "date": date_str,
                "total_booked": daily_stats_db[date_str]["total_booked"],
                "completed_count": daily_stats_db[date_str]["completed_count"]
            })
        else:
            daily_stats.append({
                "date": date_str,
                "total_booked": 0,
                "completed_count": 0
            })
        current_day += timedelta(days=1)

    return AdminStatsResponse(
        period=period,
        total_appointments=general_metrics["total"] or 0,
        completed_appointments=general_metrics["completed"] or 0,
        cancelled_appointments=general_metrics["cancelled"] or 0,
        waiting_appointments=general_metrics["waiting"] or 0,  
        total_revenue=float(total_revenue),
        top_services=top_services,  
        daily_stats=daily_stats  
    )