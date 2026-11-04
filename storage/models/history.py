"""Immutable administrative history and nested snapshots (Alembic revision 0003).

Live hardware/recipes/controls use typed domain tables. Historic revision
snapshots and event details are immutable heterogeneous documents represented
as typed tree rows, NEVER JSON columns. Historic recipe revisions intentionally
have no FK to the mutable recipe: deleting a recipe cannot erase its history.
"""
from sqlalchemy import (
    Boolean, CheckConstraint, Column, Float, ForeignKey, Integer,
    String, Text, UniqueConstraint,
)
from sqlalchemy.orm import relationship

from storage.models.base import Base


class HistoryDocument(Base):
    __tablename__ = "bridge_history_documents_v2"
    id = Column(Integer, primary_key=True, autoincrement=True)
    kind = Column(String(32), nullable=False, index=True)
    sha256 = Column(String(64), nullable=False)
    nodes = relationship(
        "HistoryNode", back_populates="document", cascade="all, delete-orphan",
        order_by="HistoryNode.id",
    )


class HistoryNode(Base):
    """Reconstruct dict/list/scalar with exact types and original list order."""
    __tablename__ = "bridge_history_nodes_v2"
    id = Column(Integer, primary_key=True, autoincrement=True)
    document_id = Column(
        Integer, ForeignKey("bridge_history_documents_v2.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    parent_id = Column(
        Integer, ForeignKey("bridge_history_nodes_v2.id", ondelete="CASCADE"),
        nullable=True, index=True,
    )
    ordinal = Column(Integer, nullable=False)
    key = Column(Text, nullable=True)
    value_kind = Column(String(12), nullable=False)
    text_value = Column(Text)
    int_value = Column(Integer)
    float_value = Column(Float)
    bool_value = Column(Boolean)
    document = relationship("HistoryDocument", back_populates="nodes")
    parent = relationship(
        "HistoryNode", remote_side=[id], back_populates="children",
    )
    children = relationship("HistoryNode", back_populates="parent")
    __table_args__ = (
        CheckConstraint(
            "value_kind IN ('object','array','null','bool','int','float','str')",
            name="ck_bridge_history_node_kind",
        ),
        CheckConstraint("ordinal >= 0", name="ck_bridge_history_node_ordinal"),
    )


class ConfigurationRevision(Base):
    __tablename__ = "bridge_configuration_revisions_v2"
    revision = Column(Integer, primary_key=True)
    action = Column(String(128), nullable=False)
    created_at = Column(Text, nullable=False)
    document_id = Column(
        Integer, ForeignKey("bridge_history_documents_v2.id", ondelete="RESTRICT"),
        unique=True, nullable=False,
    )
    document = relationship("HistoryDocument")


class ConfigurationDraft(Base):
    __tablename__ = "bridge_configuration_drafts_v2"
    id = Column(Integer, primary_key=True)
    base_revision = Column(Integer, nullable=False)
    status = Column(String(16), nullable=False)
    created_at = Column(Text, nullable=False)
    document_id = Column(
        Integer, ForeignKey("bridge_history_documents_v2.id", ondelete="RESTRICT"),
        unique=True, nullable=False,
    )
    document = relationship("HistoryDocument")
    __table_args__ = (
        CheckConstraint("status IN ('draft','applied','discarded')",
                        name="ck_bridge_config_draft_status"),
    )


class RecipeRevision(Base):
    __tablename__ = "bridge_recipe_revisions_v2"
    recipe_id = Column(String(180), primary_key=True)
    revision = Column(Integer, primary_key=True)
    created_at = Column(Text, nullable=False)
    document_id = Column(
        Integer, ForeignKey("bridge_history_documents_v2.id", ondelete="RESTRICT"),
        unique=True, nullable=False,
    )
    document = relationship("HistoryDocument")


class AuditEvent(Base):
    __tablename__ = "bridge_audit_events_v2"
    id = Column(Integer, primary_key=True)
    event_type = Column(String(128), nullable=False, index=True)
    entity_id = Column(String(180))
    created_at = Column(Text, nullable=False)
    document_id = Column(
        Integer, ForeignKey("bridge_history_documents_v2.id", ondelete="RESTRICT"),
        unique=True, nullable=False,
    )
    document = relationship("HistoryDocument")


class LegacyImport(Base):
    __tablename__ = "bridge_legacy_imports_v2"
    source_sha256 = Column(String(64), primary_key=True)
    created_at = Column(Text, nullable=False)
    document_id = Column(
        Integer, ForeignKey("bridge_history_documents_v2.id", ondelete="RESTRICT"),
        unique=True, nullable=False,
    )
    document = relationship("HistoryDocument")


class LegacySchemaMigration(Base):
    """Historical migrations of the pre-Alembic SQLite schema, not Alembic itself."""
    __tablename__ = "bridge_legacy_schema_migrations_v2"
    version = Column(Integer, primary_key=True)
    filename = Column(Text, nullable=False)
    sha256 = Column(String(64), nullable=False)
    applied_at = Column(Text, nullable=False)
