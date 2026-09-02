# Data retention in Ferrowave Pulse

Last updated 22 March 2026

This article explains how long Ferrowave Pulse keeps the data you collect while your
workspace is active. For what happens to your data after you cancel or your contract
ends, see the Data Processing Addendum, which governs return and deletion after
termination.

## Survey responses

Raw survey responses, including scores, free-text comments, and respondent metadata, are
retained for as long as your workspace is active, up to the retention window of your plan:

- Starter: 12 months from the date the response was received
- Growth: 24 months
- Scale: 36 months
- Enterprise: custom, agreed in the order form (default 36 months)

When a response passes the retention window it is deleted from the live database and its
values are removed from dashboards. Aggregate metrics that were already computed (for
example, monthly NPS trend lines) are kept, because they do not contain individual
responses.

## Exports

Files created by the export feature are stored for 7 days and then deleted. Download them
promptly.

## Backups

Encrypted backups are kept for 35 days on a rolling basis. Data deleted from the live
database will therefore persist in backups for up to 35 days before it is purged.

## Deleting a respondent

Workspace Owners can delete all responses associated with a respondent email address from
Settings, Privacy, Delete respondent. Deletion from the live database is immediate;
backups purge within 35 days.

## Logs

Application and access logs are retained for 90 days. Webhook delivery logs are retained
according to your plan, as described in the Webhooks article.
