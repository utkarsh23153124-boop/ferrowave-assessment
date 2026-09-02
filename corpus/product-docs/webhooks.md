# Webhooks

Last updated 22 July 2026

Webhooks push events from Pulse to your systems as they happen. Webhooks are available on
Scale and Enterprise plans.

## Events

- `response.created`: a new response was submitted
- `response.updated`: a respondent edited their comment within the edit window
- `alert.fired`: a Pulse Alert rule triggered
- `export.completed`: a scheduled export finished
- `signals.themes_updated`: Pulse Signals recomputed themes (Enterprise and Scale with
  the add-on)

## Delivery and retries

Pulse sends a POST request to your endpoint with a JSON body. Your endpoint must respond
with a 2xx status within 10 seconds. If it does not, Pulse retries with exponential
backoff: 1 minute, 5 minutes, 30 minutes, 2 hours, 6 hours, 12 hours, and 24 hours, for
a total of 8 attempts over roughly 46 hours. After the final failure the event is marked
as failed and can be replayed manually from the dashboard.

## Delivery logs

Every delivery attempt is recorded with the request, response status, and timing. Delivery
logs are retained for **7 days** on Scale and **90 days** on Enterprise. Events older
than the log retention period cannot be replayed.

## Signatures

Every webhook request is signed so you can verify it came from Pulse.

### Version 2 signatures (current)

Introduced in release 3.4 (May 2026). The `Pulse-Signature` header contains
`t=<unix timestamp>,v2=<hex HMAC-SHA256>`. Compute HMAC-SHA256 over the string
`<timestamp>.<raw body>` using your endpoint secret and compare with `v2` using a
constant-time comparison. Reject requests whose timestamp is more than 5 minutes old to
prevent replay.

### Version 1 signatures (deprecated)

Version 1 used the `X-Pulse-Signature` header with an HMAC-SHA1 of the body and no
timestamp. Version 1 is deprecated as of release 3.4 and is still sent alongside version 2
for endpoints created before 19 May 2026. It will be removed in release 3.6. See the release
notes for the removal date. Migrate to version 2 before then.

## Testing

Use the "Send test event" button on the webhook settings page. Test events are delivered
with the same signatures as real events.
