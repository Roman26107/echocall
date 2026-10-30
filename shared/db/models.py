from datetime import date, datetime, timezone

from sqlalchemy import BigInteger, Boolean, Date, DateTime, Float, ForeignKey, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.db.base import Base


class User(Base):
    __tablename__ = 'users'

    id: Mapped[int] = mapped_column(primary_key=True)

    telegram_id: Mapped[int] = mapped_column(
        BigInteger,
        unique=True,
        index=True,
        nullable=False,
    )
    username: Mapped[str | None] = mapped_column(
        String(32),
        unique=True,
        index=True,
        nullable=True,
    )
    display_name: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
    )
    timezone: Mapped[str] = mapped_column(
        String(64),
        default='Europe/Moscow',
        nullable=False,
    )
    incoming_call_policy: Mapped[str] = mapped_column(
        String(32),
        default='everyone',
        nullable=False,
    )
    call_notification_mode: Mapped[str] = mapped_column(
        String(32),
        default='disabled',
        nullable=False,
    )
    call_notification_interval: Mapped[int] = mapped_column(
        default=5,
        nullable=False,
    )
    theme: Mapped[str] = mapped_column(
        String(16),
        default='light',
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    created_calls = relationship(
        'Call',
        back_populates='creator',
    )

    participants = relationship(
        'CallParticipant',
        back_populates='user',
    )

    error_reports = relationship(
        'ErrorReport',
        back_populates='user',
        cascade='all, delete-orphan',
    )

    contacts = relationship(
        'Contact',
        foreign_keys='Contact.user_id',
        back_populates='user',
        cascade='all, delete-orphan',
    )

    contact_of = relationship(
        'Contact',
        foreign_keys='Contact.contact_user_id',
        back_populates='contact_user',
        cascade='all, delete-orphan',
    )

    blacklist_entries = relationship(
        'BlacklistEntry',
        foreign_keys='BlacklistEntry.user_id',
        back_populates='user',
        cascade='all, delete-orphan',
    )

    blocked_by_entries = relationship(
        'BlacklistEntry',
        foreign_keys='BlacklistEntry.blocked_user_id',
        back_populates='blocked_user',
        cascade='all, delete-orphan',
    )


class Call(Base):
    __tablename__ = 'calls'

    id: Mapped[int] = mapped_column(primary_key=True)

    creator_id: Mapped[int] = mapped_column(
        ForeignKey('users.id'),
        nullable=False,
    )

    call_type: Mapped[str] = mapped_column(
        String(32),
        default='direct',
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(32),
        default='ringing',
        nullable=False,
    )

    max_participants: Mapped[int] = mapped_column(
        default=2,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    ended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    transport_mode: Mapped[str | None] = mapped_column(
        String(16),
        nullable=True,
    )

    creator = relationship(
        'User',
        back_populates='created_calls',
    )

    participants = relationship(
        'CallParticipant',
        back_populates='call',
        cascade='all, delete-orphan',
    )


class CallParticipant(Base):
    __tablename__ = 'call_participants'
    __table_args__ = (
        UniqueConstraint('call_id', 'user_id', name='uq_call_user'),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    call_id: Mapped[int] = mapped_column(
        ForeignKey('calls.id'),
        nullable=False,
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey('users.id'),
        nullable=False,
    )

    access_token: Mapped[str] = mapped_column(
        String(128),
        unique=True,
        index=True,
        nullable=False,
    )

    role: Mapped[str] = mapped_column(
        String(32),
        default='member',
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(32),
        default='invited',
        nullable=False,
    )

    joined_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    left_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    telegram_message_id: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
    )

    telegram_chat_id: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
    )

    call = relationship(
        'Call',
        back_populates='participants',
    )

    user = relationship(
        'User',
        back_populates='participants',
    )


class Contact(Base):
    __tablename__ = 'contacts'
    __table_args__ = (
        UniqueConstraint(
            'user_id',
            'contact_user_id',
            name='uq_user_contact',
        ),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey('users.id'),
        index=True,
        nullable=False,
    )
    contact_user_id: Mapped[int] = mapped_column(
        ForeignKey('users.id'),
        index=True,
        nullable=False,
    )

    is_favorite: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    user = relationship(
        'User',
        foreign_keys=[user_id],
        back_populates='contacts',
    )

    contact_user = relationship(
        'User',
        foreign_keys=[contact_user_id],
        back_populates='contact_of',
    )


class BlacklistEntry(Base):
    __tablename__ = 'blacklist_entries'
    __table_args__ = (
        UniqueConstraint(
            'user_id',
            'blocked_user_id',
            name='uq_user_blocked_user',
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey('users.id'),
        index=True,
        nullable=False,
    )
    blocked_user_id: Mapped[int] = mapped_column(
        ForeignKey('users.id'),
        index=True,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    user = relationship(
        'User',
        foreign_keys=[user_id],
        back_populates='blacklist_entries',
    )

    blocked_user = relationship(
        'User',
        foreign_keys=[blocked_user_id],
        back_populates='blocked_by_entries',
    )


class ErrorReport(Base):
    __tablename__ = 'error_reports'

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey('users.id'),
        index=True,
        nullable=False,
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    attachment_type: Mapped[str | None] = mapped_column(String(16), nullable=True)
    telegram_file_id: Mapped[str | None] = mapped_column(String(512), nullable=True)
    file_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    mime_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(
        String(16),
        default='open',
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    user = relationship('User', back_populates='error_reports')


class SystemMetricSample(Base):
    __tablename__ = 'system_metric_samples'

    id: Mapped[int] = mapped_column(primary_key=True)
    server: Mapped[str] = mapped_column(String(16), index=True, nullable=False)
    cpu_percent: Mapped[float] = mapped_column(Float, nullable=False)
    memory_percent: Mapped[float] = mapped_column(Float, nullable=False)
    disk_percent: Mapped[float] = mapped_column(Float, nullable=False)
    services: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        index=True,
        nullable=False,
    )


class AnalyticsSnapshot(Base):
    __tablename__ = 'analytics_snapshots'

    id: Mapped[int] = mapped_column(primary_key=True)
    snapshot_date: Mapped[date] = mapped_column(Date, unique=True, index=True, nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
