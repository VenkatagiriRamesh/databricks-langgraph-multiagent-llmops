# ADR-003: Logistic regression risk model, sex excluded, fairness audited

Status: accepted. Date: 2026-10-29.

Context: The system needs an underwriting risk score with reasons per applicant. Insurance practice expects explainability, and EU rules restrict the use of sex in pricing (see GOVERNANCE.md, section 7). Data is a public toy dataset of 1,338 applicants. The plan first said gradient boosting; the implementation uses a simpler model.

Decision:
- Logistic regression on age, bmi, children, smoker and region. Sex is not a feature.
- Label: charges above the 75th percentile. Bands: below 0.35 low, below 0.65 medium, otherwise high.
- Reason codes: the three features with the largest absolute contribution (coefficient times standardised value), with direction.
- Every fifth applicant is held out. Fairness audit on the holdout for sex and region: favourable outcome is "not high risk", four-fifths rule on the lowest-to-highest ratio.
- Register as `insurance_automation.models.risk_classifier` and promote by the `champion` alias.

Measured 2026-10-29: holdout AUC 0.888 on 268 applicants; sex ratio 0.937; region ratio 0.865; both pass. On this data the model produced only low and high bands.

Consequences:
- Contributions are exact for a linear model, so reason codes are faithful without extra tooling.
- A small linear model is likely weaker than boosting; this was not compared.
- Excluding sex does not remove a gap between sexes; the audit shows one remains. Its cause is unverified.
- The label is a cost quantile, not a loss outcome. This is not a validated pricing model.
- The medium band is defined but unused on this data.
