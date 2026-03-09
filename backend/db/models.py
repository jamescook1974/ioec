import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import (
    String, Text, Float, Integer, ForeignKey, DateTime, PrimaryKeyConstraint
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Analysis(Base):
    __tablename__ = "analyses"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String, nullable=False)
    set_type: Mapped[str] = mapped_column(String, nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    taxonomy_version: Mapped[str] = mapped_column(String, nullable=False, default="v1.0")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    documents: Mapped[list["Document"]] = relationship("Document", back_populates="analysis", cascade="all, delete-orphan")
    obligations: Mapped[list["Obligation"]] = relationship("Obligation", back_populates="analysis", cascade="all, delete-orphan")
    clusters: Mapped[list["Cluster"]] = relationship("Cluster", back_populates="analysis", cascade="all, delete-orphan")


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    analysis_id: Mapped[str] = mapped_column(String, ForeignKey("analyses.id"), nullable=False)
    source_type: Mapped[str] = mapped_column(String, nullable=False)  # pdf|docx|url|paste
    source_name: Mapped[str] = mapped_column(String, nullable=False)
    source_url: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    doc_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON string

    analysis: Mapped["Analysis"] = relationship("Analysis", back_populates="documents")
    obligations: Mapped[list["Obligation"]] = relationship("Obligation", back_populates="document", cascade="all, delete-orphan")


class Obligation(Base):
    __tablename__ = "obligations"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    analysis_id: Mapped[str] = mapped_column(String, ForeignKey("analyses.id"), nullable=False)
    document_id: Mapped[str] = mapped_column(String, ForeignKey("documents.id"), nullable=False)
    primary_category: Mapped[str] = mapped_column(String, nullable=False)
    secondary_categories: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON array string
    normalized_statement: Mapped[str] = mapped_column(Text, nullable=False)
    modality: Mapped[str] = mapped_column(String, nullable=False)
    action: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    object_field: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    scope_system: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    frequency_timing: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    retention_duration: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    owner_role: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    evidence_hint: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    quote_snippet: Mapped[str] = mapped_column(Text, nullable=False)
    source_locator: Mapped[str] = mapped_column(Text, nullable=False)  # JSON string
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    embedding_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON array of floats
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    analysis: Mapped["Analysis"] = relationship("Analysis", back_populates="obligations")
    document: Mapped["Document"] = relationship("Document", back_populates="obligations")
    cluster_memberships: Mapped[list["ClusterMember"]] = relationship("ClusterMember", back_populates="obligation", cascade="all, delete-orphan")


class Cluster(Base):
    __tablename__ = "clusters"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    analysis_id: Mapped[str] = mapped_column(String, ForeignKey("analyses.id"), nullable=False)
    primary_category: Mapped[str] = mapped_column(String, nullable=False)
    representative_statement: Mapped[str] = mapped_column(Text, nullable=False)
    obligation_count: Mapped[int] = mapped_column(Integer, nullable=False)
    cluster_embedding_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    analysis: Mapped["Analysis"] = relationship("Analysis", back_populates="clusters")
    members: Mapped[list["ClusterMember"]] = relationship("ClusterMember", back_populates="cluster", cascade="all, delete-orphan")


class ClusterMember(Base):
    __tablename__ = "cluster_members"

    cluster_id: Mapped[str] = mapped_column(String, ForeignKey("clusters.id"), nullable=False)
    obligation_id: Mapped[str] = mapped_column(String, ForeignKey("obligations.id"), nullable=False)

    __table_args__ = (
        PrimaryKeyConstraint("cluster_id", "obligation_id"),
    )

    cluster: Mapped["Cluster"] = relationship("Cluster", back_populates="members")
    obligation: Mapped["Obligation"] = relationship("Obligation", back_populates="cluster_memberships")


class Comparison(Base):
    __tablename__ = "comparisons"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    analysis_a_id: Mapped[str] = mapped_column(String, ForeignKey("analyses.id"), nullable=False)
    analysis_b_id: Mapped[str] = mapped_column(String, ForeignKey("analyses.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    matches: Mapped[list["ComparisonMatch"]] = relationship("ComparisonMatch", back_populates="comparison", cascade="all, delete-orphan")
    issues: Mapped[list["ComparisonIssue"]] = relationship("ComparisonIssue", back_populates="comparison", cascade="all, delete-orphan")


class ComparisonMatch(Base):
    __tablename__ = "comparison_matches"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    comparison_id: Mapped[str] = mapped_column(String, ForeignKey("comparisons.id"), nullable=False)
    primary_category: Mapped[str] = mapped_column(String, nullable=False)
    cluster_a_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    cluster_b_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    similarity: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    diff_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    conflict_level: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    comparison: Mapped["Comparison"] = relationship("Comparison", back_populates="matches")


class ComparisonIssue(Base):
    __tablename__ = "comparison_issues"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    comparison_id: Mapped[str] = mapped_column(String, ForeignKey("comparisons.id"), nullable=False)
    primary_category: Mapped[str] = mapped_column(String, nullable=False)
    issue_type: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    proposed_unified_obligation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending")
    decision: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    comparison: Mapped["Comparison"] = relationship("Comparison", back_populates="issues")
