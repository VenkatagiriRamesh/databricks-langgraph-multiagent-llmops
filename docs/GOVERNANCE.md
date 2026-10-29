# Governance

This describes the controls in the project and their limits. Section 7 is a general note, not legal advice.

## 1. PII masking

Masking is enforced in Unity Catalog column masks, not in agent code.

| Column | Mask | Who sees real values |
|---|---|---|
| `curated.claims.adjuster_notes` | `mask_notes` returns `*** masked ***` | Members of `admins` or `claims_role` |
| `curated.applicants.applicant_id` | `mask_applicant_id` returns a SHA-256 hash | Members of `admins` or `claims_role` |

`bootstrap_data` creates the masks and prints the mask list from `information_schema.column_masks`. The data itself is synthetic or a public toy dataset, so the masks demonstrate the mechanism. A test that PII never appears in agent output is a plan target, not something this document claims.

**Known issue: masked identity on the deployed endpoint.** The serving endpoint runs as service principal `216983c9-db86-4ef8-b500-9349e6025f94`, which is not in `admins` or `claims_role`, so it sees masked adjuster notes and hashed applicant ids. On the endpoint the risk lookup by applicant id returns nothing, and the `INCONSISTENT_NOTES` fraud flag and the SIU routing that follows are lost for claims such as C00017. The evaluation ran as the workspace owner, who sees real values, so served behaviour differs from evaluated behaviour. The fix is an explicit mask exception for that one principal: `AGENT_PRINCIPAL=<id> python -m scripts.apply_masks`. It is implemented but not applied, because it grants access to unmasked PII and needs the owner's approval. The endpoint also serves model version 3; the review fixes (SIU referral wording, auto-settle decision lines and audit records, approval locking, SQL guard hardening) are committed and pending redeploy.

## 2. Authority matrix

The required approver is a function of the payable amount (after deductible and limit) and the fraud result. It is code, in `tools/authority.py`, and clause AUTH-01 states it in the policy corpus.

| Payable amount | Required authority |
|---|---|
| Under 2,000 | auto (no human approval) |
| 2,000 to 10,000 | adjuster |
| Over 10,000 up to 25,000 | senior adjuster |
| Over 25,000 | manager |
| Any SIU referral | SIU |

For a covered claim the amount is the payable amount; a claim of 26,000 with a 1,500 deductible pays 24,500 and needs a senior adjuster, not a manager. A claim denied on coverage (exclusion, waiting period, no clause) is authorised on the claimed amount, because a customer-affecting denial needs sign-off at the level for that amount (fraud referral does not apply to a denial); denials under 2,000 stay `auto`. At the gate the proposed decision for a denial is `deny_claim`, `approve` means `confirm_denial`, and the final text reads `Decision: DENIAL CONFIRMED by <role> for claim <id>.` Every other authority pauses the graph at the approval gate with the claim id, required role, proposed decision, payable amount, fraud flag codes and risk reason-code features.

## 3. Fraud screening never auto-denies

The fraud screener returns flags with evidence and a recommendation to refer to SIU. It never sets a denial. A referral changes the required authority to `siu` and the proposed decision to `refer_to_siu`; a person decides. The writer prompt also forbids stating that a claim is approved or paid, and the critic fails a draft that grants a claim when the evidence contains an injected instruction.

## 4. Reason codes

The risk model returns its top three contributing features with direction (raises or lowers risk). The answer text states the applicant's actual value and the direction, for example `smoker status: yes (raises risk)`. Coverage decisions carry clause ids. Fraud flags carry evidence strings. These serve the same purpose as adverse-action style reason codes: a reviewer and the applicant can see why.

## 5. Fairness audit

The risk model is a logistic regression on age, bmi, children, smoker and region. Sex is excluded as a feature (clause UW-01). The label is "charges above the 75th percentile". `scripts/train_register_model.py` audits the holdout set (268 applicants) and logs the report to MLflow.

Method: the favourable outcome is "not classified high risk". The disparate impact ratio is the lowest group's favourable rate divided by the highest. Four-fifths rule: a ratio of 0.80 or above passes.

Measured on the real workspace on 2026-10-29. Holdout AUC 0.888.

| Attribute | Group favourable rates | Ratio | Four-fifths |
|---|---|---|---|
| sex | female 0.839, male 0.786 | 0.937 | pass |
| region | southwest 0.905 (highest); southeast and northeast 0.783 (lowest) | 0.865 | pass |

How to read it:
- Both ratios pass 0.80, but passing a screening rule is not proof of fairness. Groups are small on a 268-row holdout, so the rates are noisy.
- Excluding sex does not make outcomes equal: a 0.053 gap between female and male remains. The cause was not investigated; correlated features are a plausible explanation and this is unverified.
- Region is a model feature, so its gap is expected; whether using region is acceptable is a policy decision, not a statistical one.
- The model produced only low and high bands on this data (no medium), so the audit measures a two-way split.
- The audit covers sex and region only, not age.

## 6. Human oversight and logging

- Approval gate for every non-auto decision; reply options approve, reject, or edit with text.
- Resuming an unknown or already-resolved run id takes no action.
- Every resolved approval is appended to a log record: run id, claim id, required authority, decision, timestamp, payable amount, edit text. The log writes to a Delta table through `SqlApprovalLog`.
- Traces record each node with token counts. Prompts are versioned in the registry; the model is versioned by alias.
- Repeated critic failure escalates to a human instead of answering.

## 7. Regulatory context (general note, not legal advice)

EU gender-neutral pricing: in Test-Achats (Case C-236/09, 2011) the Court of Justice held that insurers may not use sex as a rating factor leading to differences in premiums and benefits. This is why sex is not a model feature here. This project is not a pricing model, and the fairness audit above is a screening check, not a compliance assessment.

EU AI Act: AI systems used for risk assessment and pricing in life and health insurance are generally treated as high-risk. High-risk obligations include risk management, data governance, logging, transparency, human oversight and accuracy documentation. The measures above map loosely to logging, human oversight and documentation. Whether a given system falls in scope, and what it must do, depends on its use and on the Act's details and timelines; check with qualified counsel. This project is a demonstration and makes no compliance claim.

## 8. Honest limits

- All data is synthetic or a public toy dataset (1,338 applicants reused from the author's earlier project). Policies and claims are generated.
- Fraud labels are seeded (about 8 percent), so fraud precision and recall demonstrate the pipeline, not real-world performance. They are also circular (see below).
- The risk model is not a validated pricing model. Its label is a charge quantile.
- On Free Edition the role in an approval reply is not authenticated: anyone who can call the endpoint and knows a run id can reply as any role.
- Pending approvals are held per endpoint process. A restart loses pending runs (decisions already made persist in the log table).
- The approval log table (`eval.approval_decisions`) is created by DDL in the deploy script (`scripts/deploy_agent_endpoint.py`). The endpoint is deployed (model version 5, deployed 2026-10-29 with the review fixes); audit-table writes are best-effort.
- Fraud and authority ground truth in the golden set were produced by the same deterministic code the agent uses, so the evaluation checks pass-through, not detection. Authority is separately checked against a hand-computed 18-row table.
- Judge scores are uncalibrated (no human labels, no kappa).
- PII masking and the access groups were exercised on one workspace only.
