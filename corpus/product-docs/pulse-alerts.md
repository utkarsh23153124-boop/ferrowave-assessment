# Pulse Alerts

Last updated 15 April 2026

Pulse Alerts watch your score and tell you when it moves. They are included on Growth,
Scale, and Enterprise plans.

## How an alert is triggered

An alert fires when your rolling 7-day NPS falls by more than 5 points compared with the
previous 7-day window. Both windows must contain at least 30 responses; if either window
has fewer than 30 responses the comparison is skipped and no alert is sent, to avoid
noisy alerts from small samples.

You can also set an absolute threshold alert (for example, "alert me if NPS is below 20")
and a volume alert ("alert me if fewer than 50 responses arrive in a week").

## Where alerts go

Alerts can be delivered by email to any workspace member and, if the Slack integration
is connected, to a Slack channel. Each alert includes the current score, the previous
score, the number of responses in each window, and a link to the filtered dashboard.

## Configuring alerts

Go to Settings, Alerts. You can create up to 10 alert rules per workspace. Each rule can
be scoped to a survey, a segment, or the whole workspace.

## Frequency

Pulse evaluates alert rules once per hour. A rule that has fired will not fire again for
24 hours unless the score falls a further 5 points.

## Pulse Alerts is not Pulse Signals

Pulse Alerts is about score movement. Pulse Signals is the AI feature that reads
free-text comments and groups them into themes. They are separate features with
different plan availability.
