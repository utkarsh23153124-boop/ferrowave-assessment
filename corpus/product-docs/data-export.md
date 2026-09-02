# Exporting your data

Last updated 30 June 2026

## One-off exports

Every plan can export responses as CSV from the dashboard. Filter the dashboard, then
click Export. Exports of more than 50,000 responses are generated in the background and
you receive an email with a download link when the file is ready. Export files are
available for 7 days.

## API export

Growth, Scale, and Enterprise workspaces can pull responses through the API using the
responses endpoint with `since` and `until` parameters. This is the recommended approach
for keeping a data warehouse in sync.

## Scheduled exports

Scale and Enterprise workspaces can schedule a daily or weekly export to an S3 bucket, a
Google Cloud Storage bucket, or an SFTP server. Set this up in Settings, Exports. Each
scheduled export triggers an `export.completed` webhook event.

## Export format

Exports contain one row per response with columns: response_id, survey_id, survey_name,
submitted_at (UTC, ISO 8601), score, comment, respondent_email, respondent_id, channel,
language, and one column per respondent attribute.

Comments are exported verbatim. If you have enabled comment redaction in Settings,
Privacy, exported comments have email addresses and phone numbers replaced with
placeholders.
