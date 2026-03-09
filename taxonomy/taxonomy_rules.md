# Taxonomy v1 — Categorization Rules

## Multi-Label Policy

Every obligation must have:
- **Exactly 1** `primary_category` from Taxonomy v1
- **0–2** optional `secondary_categories` from the same taxonomy

## Tie-Breakers

When an obligation could fit multiple categories, apply these rules in order:

1. **CUST first** — If the obligation is explicitly a customer promise or contract clause, tag CUST as primary, even if technically specific (e.g., "we will notify customers within 72 hours").

2. **DATA for data protection intent** — If the core intent is protecting data (retention, deletion, classification, encryption of data), DATA is primary. Secondary might include LOG or TPRM.

3. **LOG for detection/monitoring** — If core intent is detecting events, SIEM, alerting, or monitoring, LOG is primary.

4. **IR for post-incident** — If the obligation is about responding to or communicating after an incident, IR is primary. Add CUST as secondary if customer notification is involved.

5. **BCDR for availability** — If about uptime, backups, DR testing, RTO/RPO, BCDR is primary.

6. **IAM for access** — If about access provisioning, reviews, authentication, MFA, IAM is primary.

7. **SDLC for engineering workflow** — If about code review, CI/CD, secure development, SDLC is primary.

8. **TPRM for vendors** — If about vendor/subprocessor obligations, TPRM is primary. Add CUST as secondary if contract-driven.

9. **GOV for governance** — If about training, audits, policy approval, risk management, GOV is primary.

10. **VULN for patching** — If about vulnerability scanning, patching, pen tests, VULN is primary.

11. **PHYS for endpoints** — If about device security, MDM, EDR, physical access, PHYS is primary.

12. **PROD for product-specific** — If about product integrity controls, fraud monitoring, decisioning auditability specific to the product, PROD is primary.

## Examples

| Obligation | Primary | Secondary |
|---|---|---|
| "Customer must be notified within 72 hours of a security incident" | CUST | IR |
| "Logs are retained for 12 months" | LOG | DATA |
| "Access must be reviewed quarterly" | IAM | GOV |
| "Critical vulnerabilities must be remediated within 30 days" | VULN | |
| "Backups are tested quarterly" | BCDR | |
| "Vendors must undergo security review before onboarding" | TPRM | GOV |
| "MFA is required for all admin access" | IAM | |
| "Code review is required before merge" | SDLC | |
| "Customer data is encrypted at rest" | DATA | CUST |
