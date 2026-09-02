# RFC 0042: Salesforce integration v2

CONFIDENTIAL. INTERNAL. Do not share outside Ferrowave.

Author: Deepak Nair (Integrations)
Status: Accepted
Date: 3 June 2026

## Summary

Rewrite the Salesforce integration on the Salesforce Bulk API 2.0 and add support for
Person Accounts, multiple orgs per workspace, and bidirectional sync of survey responses to
a custom `Pulse_Response__c` object.

## Motivation

The current integration (v1) polls the REST API every 15 minutes and breaks on orgs with
more than 500,000 contacts. Three Enterprise renewals in Q3 depend on this (Meridian,
Larkspur, Tolland Health).

## Plan

- Phase 1 (July to August 2026): Bulk API ingestion, feature-flagged for design partners.
- Phase 2 (September 2026): bidirectional sync, Person Accounts.
- Phase 3: general availability targeted for **Q4 2026**, tentatively the 3.7 release.

## Plan availability

v2 remains Enterprise only at launch. Product is considering a Scale tier version in
2027 but nothing is committed. Do not communicate dates to customers until the launch
plan is approved by Product Marketing.

## Risks

Salesforce API limits on customer orgs; Person Account edge cases; migration of existing
v1 field mappings.
