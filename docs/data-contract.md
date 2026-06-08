# Source Data Contract

This contract is derived from `scheme.sql`, the adjacent ER description, and
`seed_database.py`. A bank implementation can satisfy this contract with
tables, views, APIs, or adapter-specific query logic.

## Required Context For Alert Triage

`get_alert_context(alert_id)` returns:

- `alert`: source alert row.
- `rule`: matched compliance rule.
- `transaction`: triggering transaction.
- `account`: source account.
- `customer`: account owner.
- `destination_country`: optional country record for international transfers.
- `pattern`: latest customer transaction pattern.
- `recent_transactions`: recent customer transactions.
- `prior_alerts`: prior customer alerts.
- `sanctions_matches`: active sanctions screening matches.
- `pep_matches`: active PEP screening matches.

## Required Context For Risk Scoring

`get_customer_context(customer_id)` returns:

- `customer`
- `accounts`
- `latest_pattern`
- `recent_transactions`
- `open_alerts`
- `prior_alerts`
- `sanctions_matches`
- `pep_matches`

## Required Context For SAR Drafting

`get_case_context(case_id)` returns:

- `case`
- `customer`
- `linked_alerts`
- `transactions`
- `comments`

## Reference Source Tables

The reference seed script uses:

- `countries`
- `branches`
- `officer_roles`
- `compliance_officers`
- `currency_rates`
- `customers`
- `accounts`
- `transactions`
- `compliance_rules`
- `alerts`
- `alert_comments`
- `cases`
- `case_alerts`
- `risk_scores`
- `regulatory_reports`
- `sanctions_list`
- `pep_list`
- `transaction_patterns`
- `monthly_reports`
- `audit_log`

The sidecar does not require those names if a custom adapter maps equivalent
data into the expected context dictionaries.
