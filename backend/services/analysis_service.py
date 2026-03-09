import json
import uuid
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
from sqlalchemy.orm import Session

from backend.db.models import (
    Analysis, Document, Obligation, Cluster, ClusterMember,
    Comparison, ComparisonMatch, ComparisonIssue
)
from backend.ingestion.chunking import chunk_pages, chunk_text_direct
from backend.ingestion.pdf_extract import extract_pdf_bytes
from backend.ingestion.docx_extract import extract_docx_bytes
from backend.ingestion.url_extract import extract_url
from backend.llm.extract_obligations import extract_from_chunks
from backend.embed.embeddings import embed_texts, vec_to_json, json_to_vec
from backend.embed.clustering import cluster_obligations
from backend.compare.match_clusters import match_clusters
from backend.compare.diff import compute_diff
from backend.compare.propose_unified import propose_unified

logger = logging.getLogger(__name__)


def create_analysis(db: Session, name: str, set_type: str, notes: str = "") -> Analysis:
    analysis = Analysis(
        id=str(uuid.uuid4()),
        name=name,
        set_type=set_type,
        notes=notes,
        taxonomy_version="v1.0",
        created_at=datetime.utcnow()
    )
    db.add(analysis)
    db.commit()
    db.refresh(analysis)
    return analysis


def add_document_paste(db: Session, analysis_id: str, title: str, text: str) -> Document:
    doc = Document(
        id=str(uuid.uuid4()),
        analysis_id=analysis_id,
        source_type="paste",
        source_name=title,
        source_url=None,
        uploaded_at=datetime.utcnow()
    )
    db.add(doc)
    db.commit()
    # Store text in metadata for retrieval
    doc.metadata_json = json.dumps({"raw_text": text})
    db.commit()
    return doc


def add_document_url(db: Session, analysis_id: str, url: str) -> Document:
    doc = Document(
        id=str(uuid.uuid4()),
        analysis_id=analysis_id,
        source_type="url",
        source_name=url,
        source_url=url,
        uploaded_at=datetime.utcnow()
    )
    db.add(doc)
    db.commit()
    return doc


def add_document_upload(db: Session, analysis_id: str, filename: str, file_bytes: bytes, source_type: str) -> Document:
    doc = Document(
        id=str(uuid.uuid4()),
        analysis_id=analysis_id,
        source_type=source_type,
        source_name=filename,
        source_url=None,
        uploaded_at=datetime.utcnow(),
        metadata_json=json.dumps({"file_bytes_b64": __import__("base64").b64encode(file_bytes).decode()})
    )
    db.add(doc)
    db.commit()
    return doc


def _get_document_content(doc: Document) -> List[Dict]:
    """Extract pages/sections from a document."""
    meta = json.loads(doc.metadata_json) if doc.metadata_json else {}

    if doc.source_type == "paste":
        text = meta.get("raw_text", "")
        return [{"text": text, "page": None, "section": "Pasted Text", "paragraph_index": 0}]

    elif doc.source_type == "url":
        return extract_url(doc.source_url)

    elif doc.source_type in ("pdf", "docx"):
        import base64
        b64 = meta.get("file_bytes_b64", "")
        if not b64:
            return []
        file_bytes = base64.b64decode(b64)
        if doc.source_type == "pdf":
            return extract_pdf_bytes(file_bytes, doc.source_name)
        else:
            return extract_docx_bytes(file_bytes, doc.source_name)

    return []


def run_analysis(db: Session, analysis_id: str, use_clustering: bool = True, progress_callback=None) -> Dict[str, Any]:
    """
    Run the full pipeline: ingest all documents, extract obligations, embed, cluster.
    Clears prior obligations/clusters for this analysis first.

    progress_callback(fraction: float, message: str) is called at key stages.
    """
    def _progress(fraction, message):
        if progress_callback:
            progress_callback(fraction, message)

    _progress(0.02, "Clearing previous results...")

    # Clear prior data
    db.query(ClusterMember).filter(
        ClusterMember.cluster_id.in_(
            db.query(Cluster.id).filter(Cluster.analysis_id == analysis_id)
        )
    ).delete(synchronize_session=False)
    db.query(Cluster).filter(Cluster.analysis_id == analysis_id).delete()
    db.query(Obligation).filter(Obligation.analysis_id == analysis_id).delete()
    db.commit()

    documents = db.query(Document).filter(Document.analysis_id == analysis_id).all()
    if not documents:
        return {"error": "No documents found", "obligations_extracted": 0}

    all_obligations = []
    n_docs = len(documents)

    for i, doc in enumerate(documents):
        # Progress spans 5% → 70% across all documents
        doc_progress = 0.05 + (i / n_docs) * 0.65
        _progress(doc_progress, f"Extracting obligations from '{doc.source_name}' ({i + 1}/{n_docs})...")
        logger.info(f"Processing document: {doc.source_name}")

        pages = _get_document_content(doc)
        if not pages:
            logger.warning(f"No content extracted from {doc.source_name}")
            continue

        chunks = chunk_pages(pages, doc.id)
        if not chunks:
            logger.warning(f"No chunks generated from {doc.source_name}")
            continue

        chunks_done = [0]
        n_chunks = len(chunks)

        def chunk_callback(i=i, doc=doc, n_chunks=n_chunks, chunks_done=chunks_done):
            chunks_done[0] += 1
            frac = doc_progress + (chunks_done[0] / n_chunks) * (0.65 / n_docs)
            _progress(min(frac, 0.70), f"Extracting '{doc.source_name}' ({i + 1}/{n_docs}) — chunk {chunks_done[0]}/{n_chunks}...")

        raw_obligations = extract_from_chunks(chunks, doc.source_name, chunk_callback=chunk_callback)

        for obs_data in raw_obligations:
            obs = Obligation(
                id=str(uuid.uuid4()),
                analysis_id=analysis_id,
                document_id=doc.id,
                primary_category=obs_data["primary_category"],
                secondary_categories=json.dumps(obs_data.get("secondary_categories", [])),
                normalized_statement=obs_data["normalized_statement"],
                modality=obs_data.get("modality", "implicit"),
                action=obs_data.get("action"),
                object_field=obs_data.get("object_field"),
                scope_system=obs_data.get("scope_system"),
                frequency_timing=obs_data.get("frequency_timing"),
                retention_duration=obs_data.get("retention_duration"),
                owner_role=obs_data.get("owner_role"),
                evidence_hint=obs_data.get("evidence_hint"),
                quote_snippet=obs_data.get("quote_snippet", ""),
                source_locator=json.dumps(obs_data.get("source_locator", {})),
                confidence=obs_data.get("confidence", 0.0),
                created_at=datetime.utcnow()
            )
            db.add(obs)
            all_obligations.append(obs)

        db.commit()

    _progress(0.72, f"Computing embeddings for {len(all_obligations)} obligations...")

    # Compute embeddings
    logger.info(f"Computing embeddings for {len(all_obligations)} obligations")
    statements = [o.normalized_statement for o in all_obligations]
    if statements:
        try:
            vecs = embed_texts(statements)
            for obs, vec in zip(all_obligations, vecs):
                obs.embedding_json = vec_to_json(vec)
            db.commit()
        except Exception as e:
            logger.error(f"Embedding failed: {e}")

    # Clustering
    if use_clustering and all_obligations:
        _progress(0.88, "Clustering obligations...")
        logger.info("Running clustering")
        obs_dicts = []
        for obs in all_obligations:
            obs_dicts.append({
                "id": obs.id,
                "primary_category": obs.primary_category,
                "normalized_statement": obs.normalized_statement,
                "confidence": obs.confidence,
                "embedding_json": obs.embedding_json or ""
            })

        clusters = cluster_obligations(obs_dicts)

        for cl_data in clusters:
            cl = Cluster(
                id=str(uuid.uuid4()),
                analysis_id=analysis_id,
                primary_category=cl_data["primary_category"],
                representative_statement=cl_data["representative_statement"],
                obligation_count=cl_data["obligation_count"],
                cluster_embedding_json=vec_to_json(cl_data["cluster_embedding"]) if cl_data.get("cluster_embedding") else None,
                created_at=datetime.utcnow()
            )
            db.add(cl)
            db.flush()

            for member_idx in cl_data["member_indices"]:
                obs_id = obs_dicts[member_idx]["id"]
                cm = ClusterMember(cluster_id=cl.id, obligation_id=obs_id)
                db.add(cm)

        db.commit()

    _progress(1.0, "Done!")

    return {
        "obligations_extracted": len(all_obligations),
        "documents_processed": len(documents)
    }


def create_comparison(db: Session, analysis_a_id: str, analysis_b_id: str) -> Comparison:
    """Create and compute a comparison between two analyses."""
    # Delete prior comparison between same pair if exists
    existing = db.query(Comparison).filter(
        ((Comparison.analysis_a_id == analysis_a_id) & (Comparison.analysis_b_id == analysis_b_id)) |
        ((Comparison.analysis_a_id == analysis_b_id) & (Comparison.analysis_b_id == analysis_a_id))
    ).first()
    if existing:
        db.query(ComparisonIssue).filter(ComparisonIssue.comparison_id == existing.id).delete()
        db.query(ComparisonMatch).filter(ComparisonMatch.comparison_id == existing.id).delete()
        db.delete(existing)
        db.commit()

    comparison = Comparison(
        id=str(uuid.uuid4()),
        analysis_a_id=analysis_a_id,
        analysis_b_id=analysis_b_id,
        created_at=datetime.utcnow()
    )
    db.add(comparison)
    db.commit()

    analysis_a = db.query(Analysis).filter(Analysis.id == analysis_a_id).first()
    analysis_b = db.query(Analysis).filter(Analysis.id == analysis_b_id).first()

    clusters_a = db.query(Cluster).filter(Cluster.analysis_id == analysis_a_id).all()
    clusters_b = db.query(Cluster).filter(Cluster.analysis_id == analysis_b_id).all()

    def cluster_to_dict(c):
        return {
            "id": c.id,
            "primary_category": c.primary_category,
            "representative_statement": c.representative_statement,
            "cluster_embedding_json": c.cluster_embedding_json
        }

    ca_dicts = [cluster_to_dict(c) for c in clusters_a]
    cb_dicts = [cluster_to_dict(c) for c in clusters_b]

    result = match_clusters(ca_dicts, cb_dicts)

    # Create matches
    for ca_id, cb_id, sim, category in result["matched"]:
        ca = next(c for c in clusters_a if c.id == ca_id)
        cb = next(c for c in clusters_b if c.id == cb_id)

        # Get member obligations
        obs_a_ids = [cm.obligation_id for cm in db.query(ClusterMember).filter(ClusterMember.cluster_id == ca_id).all()]
        obs_b_ids = [cm.obligation_id for cm in db.query(ClusterMember).filter(ClusterMember.cluster_id == cb_id).all()]
        obs_a = db.query(Obligation).filter(Obligation.id.in_(obs_a_ids)).all()
        obs_b = db.query(Obligation).filter(Obligation.id.in_(obs_b_ids)).all()

        def obs_to_dict(o):
            return {k: getattr(o, k) for k in ["modality", "frequency_timing", "retention_duration", "scope_system", "owner_role"]}

        diff = compute_diff(
            cluster_to_dict(ca), cluster_to_dict(cb),
            analysis_a.name, analysis_b.name,
            [obs_to_dict(o) for o in obs_a],
            [obs_to_dict(o) for o in obs_b]
        )

        match = ComparisonMatch(
            id=str(uuid.uuid4()),
            comparison_id=comparison.id,
            primary_category=category,
            cluster_a_id=ca_id,
            cluster_b_id=cb_id,
            similarity=sim,
            diff_json=diff["diff_json"],
            conflict_level=diff["conflict_level"]
        )
        db.add(match)

        # Create issue if conflict
        if diff["conflict_level"] in ("medium", "high"):
            proposals = propose_unified(
                ca.representative_statement,
                cb.representative_statement,
                diff.get("summary", ""),
                analysis_a.name,
                analysis_b.name
            )
            import json as _json
            issue = ComparisonIssue(
                id=str(uuid.uuid4()),
                comparison_id=comparison.id,
                primary_category=category,
                issue_type="conflict",
                description=diff.get("summary", "Conflict detected"),
                proposed_unified_obligation=_json.dumps(proposals),
                status="pending",
                created_at=datetime.utcnow()
            )
            db.add(issue)

    # A-only issues
    for ca_id in result["a_only"]:
        ca = next(c for c in clusters_a if c.id == ca_id)
        issue = ComparisonIssue(
            id=str(uuid.uuid4()),
            comparison_id=comparison.id,
            primary_category=ca.primary_category,
            issue_type="missing_in_B",
            description=f"Obligation present in {analysis_a.name} but not in {analysis_b.name}: {ca.representative_statement[:200]}",
            status="pending",
            created_at=datetime.utcnow()
        )
        db.add(issue)
        match = ComparisonMatch(
            id=str(uuid.uuid4()),
            comparison_id=comparison.id,
            primary_category=ca.primary_category,
            cluster_a_id=ca_id,
            cluster_b_id=None,
            similarity=None,
            diff_json=None,
            conflict_level="high"
        )
        db.add(match)

    # B-only issues
    for cb_id in result["b_only"]:
        cb = next(c for c in clusters_b if c.id == cb_id)
        issue = ComparisonIssue(
            id=str(uuid.uuid4()),
            comparison_id=comparison.id,
            primary_category=cb.primary_category,
            issue_type="missing_in_A",
            description=f"Obligation present in {analysis_b.name} but not in {analysis_a.name}: {cb.representative_statement[:200]}",
            status="pending",
            created_at=datetime.utcnow()
        )
        db.add(issue)
        match = ComparisonMatch(
            id=str(uuid.uuid4()),
            comparison_id=comparison.id,
            primary_category=cb.primary_category,
            cluster_a_id=None,
            cluster_b_id=cb_id,
            similarity=None,
            diff_json=None,
            conflict_level="high"
        )
        db.add(match)

    db.commit()
    db.refresh(comparison)
    return comparison


def decide_issue(db: Session, issue_id: str, decision: str, notes: str = "") -> ComparisonIssue:
    issue = db.query(ComparisonIssue).filter(ComparisonIssue.id == issue_id).first()
    if not issue:
        raise ValueError(f"Issue {issue_id} not found")
    issue.status = "decided"
    issue.decision = decision
    issue.notes = notes
    db.commit()
    db.refresh(issue)
    return issue
