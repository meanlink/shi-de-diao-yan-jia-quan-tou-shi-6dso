from sqlalchemy import String, JSON, Double, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from src.config.database import Base
class RuleVersion(Base):
    __tablename__ = 'rule_versions'
    id: Mapped[int] = mapped_column(primary_key=True)
    version: Mapped[int] = mapped_column(Integer)
    label: Mapped[str] = mapped_column(String(160))
    definition: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(20), default='candidate')
    replay_epoch: Mapped[int] = mapped_column(Integer, default=1)
    created_by: Mapped[int | None] = mapped_column(ForeignKey('users.id'), nullable=True)
    created_at: Mapped[float] = mapped_column(Double)
    activated_at: Mapped[float | None] = mapped_column(Double, nullable=True)
    retired_at: Mapped[float | None] = mapped_column(Double, nullable=True)
class ReplayItem(Base):
    __tablename__ = 'replay_items'
    __table_args__ = (UniqueConstraint('rule_id', 'job_id', name='uq_replay_rule_job'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    rule_id: Mapped[int] = mapped_column(ForeignKey('rule_versions.id'))
    job_id: Mapped[int] = mapped_column(ForeignKey('jobs.id'))
    epoch: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(20), default='pending')
    frozen_params: Mapped[dict] = mapped_column(JSON, default=dict)
    frozen_checksum: Mapped[str] = mapped_column(String(64), default='')
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str] = mapped_column(String(1000), default='')
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    finished_at: Mapped[float | None] = mapped_column(Double, nullable=True)
