from sqlalchemy import func

from shared.db.models import ErrorReport, User
from shared.internal_api.operations import remote_operation


@remote_operation('error_reports.create', mutating=True)
def create_error_report(
    session,
    user_id: int,
    description: str,
    attachment_type: str | None = None,
    telegram_file_id: str | None = None,
    file_name: str | None = None,
    mime_type: str | None = None,
):
    description = description.strip()
    if not 10 <= len(description) <= 2000:
        raise ValueError('Invalid error report description length')
    if attachment_type not in {None, 'photo', 'document'}:
        raise ValueError('Invalid error report attachment type')
    if attachment_type is None:
        telegram_file_id = None
        file_name = None
        mime_type = None
    elif not telegram_file_id:
        raise ValueError('Attachment file ID is required')
    report = ErrorReport(
        user_id=user_id,
        description=description,
        attachment_type=attachment_type,
        telegram_file_id=telegram_file_id,
        file_name=file_name,
        mime_type=mime_type,
    )
    session.add(report)
    session.flush()
    return report


@remote_operation('error_reports.list')
def list_error_reports(session, page: int = 0, page_size: int = 5) -> dict:
    page = max(0, page)
    page_size = min(20, max(1, page_size))
    total = session.query(func.count(ErrorReport.id)).scalar() or 0
    rows = (
        session.query(ErrorReport, User)
        .join(User, User.id == ErrorReport.user_id)
        .order_by(ErrorReport.created_at.desc(), ErrorReport.id.desc())
        .offset(page * page_size)
        .limit(page_size)
        .all()
    )
    return {
        'total': total,
        'page': page,
        'page_size': page_size,
        'items': [
            {
                'id': report.id,
                'status': report.status,
                'description': report.description,
                'attachment_type': report.attachment_type,
                'created_at': report.created_at,
                'user_display_name': user.display_name,
                'user_username': user.username,
            }
            for report, user in rows
        ],
    }


@remote_operation('error_reports.get')
def get_error_report(session, report_id: int) -> dict | None:
    row = (
        session.query(ErrorReport, User)
        .join(User, User.id == ErrorReport.user_id)
        .filter(ErrorReport.id == report_id)
        .first()
    )
    if row is None:
        return None
    report, user = row
    return {
        'id': report.id,
        'status': report.status,
        'description': report.description,
        'attachment_type': report.attachment_type,
        'telegram_file_id': report.telegram_file_id,
        'file_name': report.file_name,
        'mime_type': report.mime_type,
        'created_at': report.created_at,
        'user_display_name': user.display_name,
        'user_username': user.username,
        'user_telegram_id': user.telegram_id,
    }
