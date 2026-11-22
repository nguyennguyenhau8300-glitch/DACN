from sqlalchemy import func

from models.operations import ParkingSession, Payment


def successful_payments(db, sessions):
    return db.query(Payment).filter(
        Payment.parking_session_id.in_(sessions.with_entities(ParkingSession.id)),
        Payment.status == 'SUCCESS',
    )


def is_sandbox_payment():
    return func.coalesce(Payment.transaction_code.like('SANDBOX-%'), False)
