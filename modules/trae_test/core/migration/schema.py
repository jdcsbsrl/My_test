from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


def _newid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(UTC)


class KBFile(Base):
    __tablename__ = "kb_files"

    id = Column(String(36), primary_key=True, default=_newid)
    title = Column(String(256), nullable=False)
    file_id = Column(String(256), nullable=False)
    original_path = Column(String(512), nullable=False)
    tags = Column(JSONB, nullable=False, default=list)
    classification = Column(String(128), nullable=False, default="")
    original_hash = Column(String(64), nullable=False)
    total_size = Column(Integer, nullable=False, default=0)
    chunk_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)

    chunks = relationship("KBChunk", back_populates="file", cascade="all, delete-orphan")
    requirements = relationship("KBRequirement", back_populates="file", cascade="all, delete-orphan")
    business_rules = relationship("KBBusinessRule", back_populates="file", cascade="all, delete-orphan")
    problems = relationship("KBProblem", back_populates="file", cascade="all, delete-orphan")
    test_cases = relationship("KBTestCase", back_populates="file", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_kb_files_title", "title"),
        Index("idx_kb_files_classification", "classification"),
        Index("idx_kb_files_original_hash", "original_hash"),
    )


class KBChunk(Base):
    __tablename__ = "kb_chunks"

    id = Column(String(36), primary_key=True, default=_newid)
    file_id = Column(String(36), ForeignKey("kb_files.id", ondelete="CASCADE"), nullable=False)
    chunk_index = Column(Integer, nullable=False, default=0)
    content = Column(JSONB, nullable=False)
    summary = Column(Text, nullable=True)
    keywords = Column(JSONB, nullable=True, default=list)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)

    file = relationship("KBFile", back_populates="chunks")

    __table_args__ = (
        Index("idx_kb_chunks_file_id", "file_id"),
        Index("idx_kb_chunks_content_gin", "content", postgresql_using="gin"),
    )


class KBRequirement(Base):
    __tablename__ = "kb_requirements"

    id = Column(String(36), primary_key=True, default=_newid)
    file_id = Column(String(36), ForeignKey("kb_files.id", ondelete="CASCADE"), nullable=False)
    module = Column(String(128), nullable=False, default="")
    requirement_id = Column(String(128), nullable=False, default="")
    title = Column(String(512), nullable=False, default="")
    description = Column(Text, nullable=True)
    priority = Column(String(32), nullable=True)
    status = Column(String(32), nullable=True)
    data = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)

    file = relationship("KBFile", back_populates="requirements")

    __table_args__ = (
        Index("idx_kb_requirements_file_id", "file_id"),
        Index("idx_kb_requirements_module", "module"),
        Index("idx_kb_requirements_data_gin", "data", postgresql_using="gin"),
    )


class KBBusinessRule(Base):
    __tablename__ = "kb_business_rules"

    id = Column(String(36), primary_key=True, default=_newid)
    file_id = Column(String(36), ForeignKey("kb_files.id", ondelete="CASCADE"), nullable=False)
    module = Column(String(128), nullable=False, default="")
    rule_name = Column(String(256), nullable=True)
    rule_content = Column(Text, nullable=True)
    data = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)

    file = relationship("KBFile", back_populates="business_rules")

    __table_args__ = (
        Index("idx_kb_business_rules_file_id", "file_id"),
        Index("idx_kb_business_rules_module", "module"),
        Index("idx_kb_business_rules_data_gin", "data", postgresql_using="gin"),
    )


class KBProblem(Base):
    __tablename__ = "kb_problems"

    id = Column(String(36), primary_key=True, default=_newid)
    file_id = Column(String(36), ForeignKey("kb_files.id", ondelete="CASCADE"), nullable=False)
    module = Column(String(128), nullable=False, default="")
    problem_title = Column(String(512), nullable=True)
    problem_description = Column(Text, nullable=True)
    severity = Column(String(32), nullable=True)
    status = Column(String(32), nullable=True)
    data = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)

    file = relationship("KBFile", back_populates="problems")

    __table_args__ = (
        Index("idx_kb_problems_file_id", "file_id"),
        Index("idx_kb_problems_data_gin", "data", postgresql_using="gin"),
    )


class KBTestCase(Base):
    __tablename__ = "kb_test_cases"

    id = Column(String(36), primary_key=True, default=_newid)
    file_id = Column(String(36), ForeignKey("kb_files.id", ondelete="CASCADE"), nullable=False)
    module = Column(String(128), nullable=False, default="")
    case_title = Column(String(512), nullable=True)
    case_description = Column(Text, nullable=True)
    priority = Column(String(32), nullable=True)
    data = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)

    file = relationship("KBFile", back_populates="test_cases")

    __table_args__ = (
        Index("idx_kb_test_cases_file_id", "file_id"),
        Index("idx_kb_test_cases_data_gin", "data", postgresql_using="gin"),
    )
