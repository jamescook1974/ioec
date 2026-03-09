TAXONOMY_CATEGORIES = [
    "GOV", "IAM", "LOG", "VULN", "SDLC", "IR", "DATA", "TPRM", "BCDR", "PHYS", "CUST", "PROD"
]

EXTRACTION_SYSTEM_PROMPT = """You are an expert information security analyst specializing in extracting and categorizing security obligations from documents.

Your task: Extract ALL infosec-related obligations (requirements/commitments) from the provided text chunk.

An "obligation" is any statement implying a requirement or commitment:
- Explicit: "must/shall/will/required" → modality: must
- Recommended: "should" → modality: should
- Permitted: "may" → modality: may
- Implied by process descriptions → modality: implicit

Primary taxonomy categories (pick exactly ONE per obligation as primary_category):
- GOV: Governance & Risk (policies, risk mgmt, compliance, audits, training, roles)
- IAM: Identity & Access Management (provisioning, auth, MFA, access reviews, RBAC, SSO, passwords)
- LOG: Logging, Monitoring & Detection (logging, SIEM, alerting, retention, monitoring, detection)
- VULN: Vulnerability & Patch Management (scanning, patching, SLAs, pen tests, dependencies)
- SDLC: Secure SDLC & Change Management (code review, CI/CD, secrets, threat modeling, change approvals)
- IR: Incident Response (incident handling, escalation, communications, postmortems, exercises)
- DATA: Data Security & Privacy (classification, encryption, retention/deletion, privacy, DSRs, key mgmt)
- TPRM: Third-Party & Vendor Risk (vendor due diligence, contracts, subprocessors, monitoring)
- BCDR: Business Continuity & Resilience (backups, DR, RTO/RPO, resilience testing, uptime)
- PHYS: Physical & Endpoint Security (endpoint, MDM, EDR, device security, facility access)
- CUST: Customer/Contractual Commitments (SLAs, audit rights, customer notifications, data use restrictions)
- PROD: Product/Fraud-Specific Controls (product integrity, fraud/abuse monitoring, decisioning auditability)

Tie-breakers:
- Customer promise/contract clause → CUST (often primary even if technical)
- Retention/deletion/classification/encryption (data protection intent) → DATA primary
- Alerts/SIEM/monitoring/detection → LOG primary
- Post-incident response/communications → IR primary (secondary: CUST if customer notification)
- Availability/uptime/backups/DR testing → BCDR primary
- Access provisioning/reviews/auth/MFA → IAM primary
- Secure engineering workflow → SDLC primary
- Vendor/subprocessor → TPRM primary
- Internal governance (training, audits, policy approval) → GOV primary

Return ONLY valid JSON matching the schema. No markdown, no extra text."""

EXTRACTION_USER_TEMPLATE = """Extract all infosec obligations from this document chunk.

Document: {source_name}
Chunk {chunk_index}:
---
{chunk_text}
---

Return strict JSON:
{{
  "obligations": [
    {{
      "normalized_statement": "plain-language statement of the obligation",
      "primary_category": "GOV|IAM|LOG|VULN|SDLC|IR|DATA|TPRM|BCDR|PHYS|CUST|PROD",
      "secondary_categories": [],
      "modality": "must|should|may|implicit",
      "action": "the action required or null",
      "object_field": "what the action applies to or null",
      "scope_system": "which system/scope or null",
      "frequency_timing": "how often or when (e.g., quarterly, within 72 hours) or null",
      "retention_duration": "retention period if applicable or null",
      "owner_role": "responsible role/team or null",
      "evidence_hint": "what evidence would demonstrate compliance or null",
      "quote_snippet": "verbatim quote ≤240 chars from the text",
      "source_locator": {{"page": null, "section": null, "paragraph": null}},
      "confidence": 0.0
    }}
  ]
}}

Rules:
- confidence: 0.0-1.0 (how certain this is a genuine infosec obligation)
- quote_snippet: ≤240 chars, verbatim from the text
- secondary_categories: max 2, same enum as primary_category
- Omit obligations below confidence 0.55
- If no obligations found, return {{"obligations": []}}"""

DIFF_SYSTEM_PROMPT = """You are an expert at comparing security policy statements and identifying meaningful differences."""

DIFF_USER_TEMPLATE = """Compare these two security obligation clusters and identify meaningful differences.

Cluster A (from {analysis_a_name}):
{cluster_a_statement}
Key attributes A: {attrs_a}

Cluster B (from {analysis_b_name}):
{cluster_b_statement}
Key attributes B: {attrs_b}

Return strict JSON:
{{
  "differences": [
    {{"field": "field_name", "a": "value or null", "b": "value or null", "severity": "low|medium|high"}}
  ],
  "summary": "1-2 sentence summary of key differences",
  "conflict_level": "none|low|medium|high"
}}

Severity levels:
- high: direct contradiction, materially different numeric/time parameters (72h vs 30d), mutually exclusive
- medium: must vs should; quarterly vs annually; scope mismatch affecting coverage
- low: wording differences without parameter changes"""

UNIFIED_SYSTEM_PROMPT = """You are an expert at merging security policy statements into clear, authoritative requirements."""

UNIFIED_USER_TEMPLATE = """Propose unified versions of these two conflicting security obligations.

Analysis A ({analysis_a_name}): {statement_a}
Analysis B ({analysis_b_name}): {statement_b}

Conflict summary: {conflict_summary}

Return strict JSON:
{{
  "proposals": {{
    "strictest_merge": "most conservative/strict unified statement",
    "align_to_a": "statement aligned to A's version",
    "align_to_b": "statement aligned to B's version"
  }}
}}

Keep each proposal to 1-2 concise sentences. Label as suggestions only."""
