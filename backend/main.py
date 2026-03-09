import json
import csv
import io
import logging
from typing import Optional, List
from datetime import datetime

from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Form, BackgroundTasks
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.db.session import get_db, init_db
from backend.db.models import (
    Analysis, Document, Obligation, Cluster, ClusterMember,
    Comparison, ComparisonMatch, ComparisonIssue
)
from backend.services.analysis_service import (
    create_analysis, add_document_paste, add_document_url,
    add_document_upload, run_analysis, create_comparison, decide_issue
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="IOEC - Infosec Obligations Extractor & Comparator", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    init_db()
    logger.info("Database initialized")


# ─── Pydantic Schemas ────────────────────────────────────────────────────────

class CreateAnalysisRequest(BaseModel):
    name: str
    set_type: str
    notes: Optional[str] = ""


class AnalysisResponse(BaseModel):
    id: str
    name: str
    set_type: str
    notes: Optional[str]
    taxonomy_version: str
    created_at: datetime

    class Config:
        from_attributes = True


class AnalysisDetailResponse(AnalysisResponse):
    document_count: int
    obligation_count: int


class AddPasteRequest(BaseModel):
    title: str
    text: str


class AddUrlRequest(BaseModel):
    url: str


class DocumentResponse(BaseModel):
    id: str
    analysis_id: str
    source_type: str
    source_name: str
    source_url: Optional[str]
    uploaded_at: datetime
    doc_summary: Optional[str]

    class Config:
        from_attributes = True


class RunAnalysisRequest(BaseModel):
    use_clustering: bool = True


class RunAnalysisResponse(BaseModel):
    obligations_extracted: int
    documents_processed: int
    error: Optional[str] = None


class ObligationResponse(BaseModel):
    id: str
    analysis_id: str
    document_id: str
    primary_category: str
    secondary_categories: Optional[str]
    normalized_statement: str
    modality: str
    action: Optional[str]
    object_field: Optional[str]
    scope_system: Optional[str]
    frequency_timing: Optional[str]
    retention_duration: Optional[str]
    owner_role: Optional[str]
    evidence_hint: Optional[str]
    quote_snippet: str
    source_locator: str
    confidence: float
    created_at: datetime

    class Config:
        from_attributes = True


class ClusterResponse(BaseModel):
    id: str
    analysis_id: str
    primary_category: str
    representative_statement: str
    obligation_count: int
    created_at: datetime

    class Config:
        from_attributes = True


class CreateComparisonRequest(BaseModel):
    analysis_a_id: str
    analysis_b_id: str


class ComparisonResponse(BaseModel):
    id: str
    analysis_a_id: str
    analysis_b_id: str
    created_at: datetime

    class Config:
        from_attributes = True


class ComparisonDetailResponse(ComparisonResponse):
    match_count: int
    issue_count: int
    pending_issue_count: int


class ComparisonMatchResponse(BaseModel):
    id: str
    comparison_id: str
    primary_category: str
    cluster_a_id: Optional[str]
    cluster_b_id: Optional[str]
    similarity: Optional[float]
    diff_json: Optional[str]
    conflict_level: Optional[str]

    class Config:
        from_attributes = True


class ComparisonIssueResponse(BaseModel):
    id: str
    comparison_id: str
    primary_category: str
    issue_type: str
    description: str
    proposed_unified_obligation: Optional[str]
    status: str
    decision: Optional[str]
    notes: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class DecideIssueRequest(BaseModel):
    decision: str
    notes: Optional[str] = ""


# ─── Health Check ─────────────────────────────────────────────────────────────

@app.get("/")
def health_check():
    return {"status": "ok"}


# ─── Analyses ─────────────────────────────────────────────────────────────────

@app.post("/analyses", response_model=AnalysisResponse, status_code=201)
def api_create_analysis(body: CreateAnalysisRequest, db: Session = Depends(get_db)):
    try:
        analysis = create_analysis(db, name=body.name, set_type=body.set_type, notes=body.notes or "")
        return analysis
    except Exception as e:
        logger.error(f"Create analysis error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/analyses", response_model=List[AnalysisResponse])
def api_list_analyses(db: Session = Depends(get_db)):
    analyses = db.query(Analysis).order_by(Analysis.created_at.desc()).all()
    return analyses


@app.get("/analyses/{analysis_id}", response_model=AnalysisDetailResponse)
def api_get_analysis(analysis_id: str, db: Session = Depends(get_db)):
    analysis = db.query(Analysis).filter(Analysis.id == analysis_id).first()
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")
    doc_count = db.query(Document).filter(Document.analysis_id == analysis_id).count()
    obs_count = db.query(Obligation).filter(Obligation.analysis_id == analysis_id).count()
    return AnalysisDetailResponse(
        id=analysis.id,
        name=analysis.name,
        set_type=analysis.set_type,
        notes=analysis.notes,
        taxonomy_version=analysis.taxonomy_version,
        created_at=analysis.created_at,
        document_count=doc_count,
        obligation_count=obs_count
    )


# ─── Documents ────────────────────────────────────────────────────────────────

@app.post("/analyses/{analysis_id}/documents/paste", response_model=DocumentResponse, status_code=201)
def api_add_paste(analysis_id: str, body: AddPasteRequest, db: Session = Depends(get_db)):
    analysis = db.query(Analysis).filter(Analysis.id == analysis_id).first()
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")
    try:
        doc = add_document_paste(db, analysis_id=analysis_id, title=body.title, text=body.text)
        return doc
    except Exception as e:
        logger.error(f"Add paste error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/analyses/{analysis_id}/documents/url", response_model=DocumentResponse, status_code=201)
def api_add_url(analysis_id: str, body: AddUrlRequest, db: Session = Depends(get_db)):
    analysis = db.query(Analysis).filter(Analysis.id == analysis_id).first()
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")
    try:
        doc = add_document_url(db, analysis_id=analysis_id, url=body.url)
        return doc
    except Exception as e:
        logger.error(f"Add URL error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/analyses/{analysis_id}/documents/upload", response_model=DocumentResponse, status_code=201)
async def api_upload_document(
    analysis_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    analysis = db.query(Analysis).filter(Analysis.id == analysis_id).first()
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")

    filename = file.filename or "uploaded_file"
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext == "pdf":
        source_type = "pdf"
    elif ext in ("docx", "doc"):
        source_type = "docx"
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {ext}. Use pdf or docx.")

    try:
        file_bytes = await file.read()
        doc = add_document_upload(db, analysis_id=analysis_id, filename=filename, file_bytes=file_bytes, source_type=source_type)
        return doc
    except Exception as e:
        logger.error(f"Upload error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/analyses/{analysis_id}/documents", response_model=List[DocumentResponse])
def api_list_documents(analysis_id: str, db: Session = Depends(get_db)):
    analysis = db.query(Analysis).filter(Analysis.id == analysis_id).first()
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")
    docs = db.query(Document).filter(Document.analysis_id == analysis_id).order_by(Document.uploaded_at.desc()).all()
    return docs


# ─── Run Analysis ─────────────────────────────────────────────────────────────

@app.post("/analyses/{analysis_id}/run", response_model=RunAnalysisResponse)
def api_run_analysis(analysis_id: str, body: RunAnalysisRequest = None, db: Session = Depends(get_db)):
    analysis = db.query(Analysis).filter(Analysis.id == analysis_id).first()
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")
    use_clustering = body.use_clustering if body else True
    try:
        result = run_analysis(db, analysis_id=analysis_id, use_clustering=use_clustering)
        return RunAnalysisResponse(
            obligations_extracted=result.get("obligations_extracted", 0),
            documents_processed=result.get("documents_processed", 0),
            error=result.get("error")
        )
    except Exception as e:
        logger.error(f"Run analysis error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ─── Obligations ──────────────────────────────────────────────────────────────

@app.get("/analyses/{analysis_id}/obligations", response_model=List[ObligationResponse])
def api_list_obligations(
    analysis_id: str,
    category: Optional[str] = None,
    modality: Optional[str] = None,
    q: Optional[str] = None,
    db: Session = Depends(get_db)
):
    analysis = db.query(Analysis).filter(Analysis.id == analysis_id).first()
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")

    query = db.query(Obligation).filter(Obligation.analysis_id == analysis_id)

    if category:
        query = query.filter(Obligation.primary_category == category.upper())
    if modality:
        query = query.filter(Obligation.modality == modality.lower())
    if q:
        search_term = f"%{q}%"
        query = query.filter(Obligation.normalized_statement.ilike(search_term))

    obligations = query.order_by(Obligation.primary_category, Obligation.confidence.desc()).all()
    return obligations


# ─── Clusters ─────────────────────────────────────────────────────────────────

@app.get("/analyses/{analysis_id}/clusters", response_model=List[ClusterResponse])
def api_list_clusters(analysis_id: str, db: Session = Depends(get_db)):
    analysis = db.query(Analysis).filter(Analysis.id == analysis_id).first()
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")
    clusters = db.query(Cluster).filter(Cluster.analysis_id == analysis_id).order_by(
        Cluster.primary_category, Cluster.obligation_count.desc()
    ).all()
    return clusters


# ─── Export ───────────────────────────────────────────────────────────────────

@app.get("/analyses/{analysis_id}/export.json")
def api_export_json(analysis_id: str, db: Session = Depends(get_db)):
    analysis = db.query(Analysis).filter(Analysis.id == analysis_id).first()
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")

    documents = db.query(Document).filter(Document.analysis_id == analysis_id).all()
    obligations = db.query(Obligation).filter(Obligation.analysis_id == analysis_id).all()
    clusters = db.query(Cluster).filter(Cluster.analysis_id == analysis_id).all()

    def obs_to_dict(o):
        return {
            "id": o.id,
            "document_id": o.document_id,
            "primary_category": o.primary_category,
            "secondary_categories": json.loads(o.secondary_categories) if o.secondary_categories else [],
            "normalized_statement": o.normalized_statement,
            "modality": o.modality,
            "action": o.action,
            "object_field": o.object_field,
            "scope_system": o.scope_system,
            "frequency_timing": o.frequency_timing,
            "retention_duration": o.retention_duration,
            "owner_role": o.owner_role,
            "evidence_hint": o.evidence_hint,
            "quote_snippet": o.quote_snippet,
            "source_locator": json.loads(o.source_locator) if o.source_locator else {},
            "confidence": o.confidence,
            "created_at": o.created_at.isoformat()
        }

    export_data = {
        "analysis": {
            "id": analysis.id,
            "name": analysis.name,
            "set_type": analysis.set_type,
            "notes": analysis.notes,
            "taxonomy_version": analysis.taxonomy_version,
            "created_at": analysis.created_at.isoformat()
        },
        "documents": [
            {
                "id": d.id,
                "source_type": d.source_type,
                "source_name": d.source_name,
                "source_url": d.source_url,
                "uploaded_at": d.uploaded_at.isoformat()
            }
            for d in documents
        ],
        "obligations": [obs_to_dict(o) for o in obligations],
        "clusters": [
            {
                "id": c.id,
                "primary_category": c.primary_category,
                "representative_statement": c.representative_statement,
                "obligation_count": c.obligation_count
            }
            for c in clusters
        ]
    }

    return JSONResponse(content=export_data)


@app.get("/analyses/{analysis_id}/export.csv")
def api_export_csv(analysis_id: str, db: Session = Depends(get_db)):
    analysis = db.query(Analysis).filter(Analysis.id == analysis_id).first()
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")

    obligations = db.query(Obligation).filter(Obligation.analysis_id == analysis_id).order_by(
        Obligation.primary_category
    ).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "id", "document_id", "primary_category", "secondary_categories",
        "normalized_statement", "modality", "action", "object_field",
        "scope_system", "frequency_timing", "retention_duration",
        "owner_role", "evidence_hint", "quote_snippet", "confidence", "created_at"
    ])
    for o in obligations:
        writer.writerow([
            o.id, o.document_id, o.primary_category,
            o.secondary_categories or "[]",
            o.normalized_statement, o.modality,
            o.action or "", o.object_field or "",
            o.scope_system or "", o.frequency_timing or "",
            o.retention_duration or "", o.owner_role or "",
            o.evidence_hint or "", o.quote_snippet,
            o.confidence, o.created_at.isoformat()
        ])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=analysis_{analysis_id[:8]}_obligations.csv"}
    )


# ─── Comparisons ──────────────────────────────────────────────────────────────

@app.post("/comparisons", response_model=ComparisonResponse, status_code=201)
def api_create_comparison(body: CreateComparisonRequest, db: Session = Depends(get_db)):
    # Validate both analyses exist
    analysis_a = db.query(Analysis).filter(Analysis.id == body.analysis_a_id).first()
    analysis_b = db.query(Analysis).filter(Analysis.id == body.analysis_b_id).first()
    if not analysis_a:
        raise HTTPException(status_code=404, detail=f"Analysis A not found: {body.analysis_a_id}")
    if not analysis_b:
        raise HTTPException(status_code=404, detail=f"Analysis B not found: {body.analysis_b_id}")
    if body.analysis_a_id == body.analysis_b_id:
        raise HTTPException(status_code=400, detail="Cannot compare an analysis with itself")

    try:
        comparison = create_comparison(db, analysis_a_id=body.analysis_a_id, analysis_b_id=body.analysis_b_id)
        return comparison
    except Exception as e:
        logger.error(f"Create comparison error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/comparisons/{comparison_id}", response_model=ComparisonDetailResponse)
def api_get_comparison(comparison_id: str, db: Session = Depends(get_db)):
    comparison = db.query(Comparison).filter(Comparison.id == comparison_id).first()
    if not comparison:
        raise HTTPException(status_code=404, detail="Comparison not found")

    match_count = db.query(ComparisonMatch).filter(ComparisonMatch.comparison_id == comparison_id).count()
    issue_count = db.query(ComparisonIssue).filter(ComparisonIssue.comparison_id == comparison_id).count()
    pending_count = db.query(ComparisonIssue).filter(
        ComparisonIssue.comparison_id == comparison_id,
        ComparisonIssue.status == "pending"
    ).count()

    return ComparisonDetailResponse(
        id=comparison.id,
        analysis_a_id=comparison.analysis_a_id,
        analysis_b_id=comparison.analysis_b_id,
        created_at=comparison.created_at,
        match_count=match_count,
        issue_count=issue_count,
        pending_issue_count=pending_count
    )


@app.get("/comparisons/{comparison_id}/issues", response_model=List[ComparisonIssueResponse])
def api_list_issues(
    comparison_id: str,
    category: Optional[str] = None,
    conflict_level: Optional[str] = None,
    status: Optional[str] = None,
    db: Session = Depends(get_db)
):
    comparison = db.query(Comparison).filter(Comparison.id == comparison_id).first()
    if not comparison:
        raise HTTPException(status_code=404, detail="Comparison not found")

    query = db.query(ComparisonIssue).filter(ComparisonIssue.comparison_id == comparison_id)

    if category:
        query = query.filter(ComparisonIssue.primary_category == category.upper())
    if status:
        query = query.filter(ComparisonIssue.status == status.lower())

    # conflict_level filter: join with matches
    if conflict_level:
        matching_match_ids = [
            m.id for m in db.query(ComparisonMatch).filter(
                ComparisonMatch.comparison_id == comparison_id,
                ComparisonMatch.conflict_level == conflict_level.lower()
            ).all()
        ]
        # For issues that don't join directly with matches, filter by issue_type approximation
        # Issues with issue_type="conflict" come from matches; missing_in_A/B are always "high"
        if conflict_level.lower() == "high":
            query = query.filter(
                (ComparisonIssue.issue_type.in_(["missing_in_A", "missing_in_B"])) |
                (ComparisonIssue.issue_type == "conflict")
            )
        else:
            query = query.filter(ComparisonIssue.issue_type == "conflict")

    issues = query.order_by(ComparisonIssue.primary_category, ComparisonIssue.created_at).all()
    return issues


@app.post("/comparisons/{comparison_id}/issues/{issue_id}/decide", response_model=ComparisonIssueResponse)
def api_decide_issue(
    comparison_id: str,
    issue_id: str,
    body: DecideIssueRequest,
    db: Session = Depends(get_db)
):
    comparison = db.query(Comparison).filter(Comparison.id == comparison_id).first()
    if not comparison:
        raise HTTPException(status_code=404, detail="Comparison not found")

    try:
        issue = decide_issue(db, issue_id=issue_id, decision=body.decision, notes=body.notes or "")
        return issue
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Decide issue error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/comparisons/{comparison_id}/export.json")
def api_export_comparison_json(comparison_id: str, db: Session = Depends(get_db)):
    comparison = db.query(Comparison).filter(Comparison.id == comparison_id).first()
    if not comparison:
        raise HTTPException(status_code=404, detail="Comparison not found")

    analysis_a = db.query(Analysis).filter(Analysis.id == comparison.analysis_a_id).first()
    analysis_b = db.query(Analysis).filter(Analysis.id == comparison.analysis_b_id).first()
    matches = db.query(ComparisonMatch).filter(ComparisonMatch.comparison_id == comparison_id).all()
    issues = db.query(ComparisonIssue).filter(ComparisonIssue.comparison_id == comparison_id).all()

    export_data = {
        "comparison": {
            "id": comparison.id,
            "created_at": comparison.created_at.isoformat(),
            "analysis_a": {"id": analysis_a.id, "name": analysis_a.name} if analysis_a else None,
            "analysis_b": {"id": analysis_b.id, "name": analysis_b.name} if analysis_b else None,
        },
        "matches": [
            {
                "id": m.id,
                "primary_category": m.primary_category,
                "cluster_a_id": m.cluster_a_id,
                "cluster_b_id": m.cluster_b_id,
                "similarity": m.similarity,
                "conflict_level": m.conflict_level,
                "differences": json.loads(m.diff_json) if m.diff_json else []
            }
            for m in matches
        ],
        "issues": [
            {
                "id": i.id,
                "primary_category": i.primary_category,
                "issue_type": i.issue_type,
                "description": i.description,
                "proposed_unified_obligation": json.loads(i.proposed_unified_obligation) if i.proposed_unified_obligation else None,
                "status": i.status,
                "decision": i.decision,
                "notes": i.notes,
                "created_at": i.created_at.isoformat()
            }
            for i in issues
        ]
    }

    return JSONResponse(content=export_data)
