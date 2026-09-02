# Ferrowave Pulse API reference

Last updated 12 May 2026. API version 2026-03-01.

The Pulse API lets you read surveys and responses, create respondents, and trigger survey
sends. API access is included on Growth, Scale, and Enterprise. Starter workspaces do not
have API access.

Base URL: https://api.ferrowave.example/v1

## Authentication

Send an API key in the Authorization header as a bearer token. Keys are created by
workspace Owners in Settings, API. Each key is scoped to one workspace.

## Rate limits

Rate limits depend on your plan. See the Rate limits page for the current table. When you
exceed your limit the API returns HTTP 429 with a Retry-After header.

## Pagination

List endpoints return up to 100 items per page and a `next_cursor` field. Pass it back as
the `cursor` query parameter to fetch the next page. When `next_cursor` is null there are
no more pages.

## Endpoints

### GET /surveys

Returns surveys in the workspace.

### GET /surveys/{id}/responses

Returns responses for a survey. Supports `since` and `until` (ISO 8601) and `cursor`.
Each response includes `id`, `score`, `comment`, `respondent`, `channel`, `submitted_at`,
and `metadata`.

### POST /respondents

Creates or updates a respondent by email. Attributes you pass are available as segments.

### POST /surveys/{id}/send

Queues a survey send to a list of respondent ids. Sends are asynchronous; use webhooks
(Scale and above) or poll the responses endpoint.

### GET /metrics/nps

Returns NPS for a survey or the workspace over a date range, with the promoter, passive,
and detractor counts used to calculate it.

## Errors

Errors return a JSON body with `error.code` and `error.message`. Common codes: 400
validation_error, 401 unauthorized, 403 plan_restriction, 404 not_found, 429
rate_limited, 500 internal.

## SDKs

Official SDKs are available for JavaScript and Python. Community SDKs exist for Ruby and
Go but are not supported by Ferrowave.
