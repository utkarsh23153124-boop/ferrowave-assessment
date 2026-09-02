# Setting up SAML single sign-on

Last updated 8 January 2026

Single sign-on lets your team log in to Ferrowave Pulse through your identity provider.
Pulse supports SAML 2.0 with any compliant provider, including Okta, Microsoft Entra ID,
Google Workspace, and OneLogin.

## Availability

SAML SSO is available on Scale and Enterprise plans. Starter and Growth workspaces cannot
enable SSO; upgrade to Scale to use it.

SCIM provisioning (automatic creation and removal of users from your identity provider) is
available on Enterprise only.

## Before you begin

You need to be a workspace Owner, and you need admin access to your identity provider.
Decide whether you want to enforce SSO (all members must use it) or allow it alongside
password login.

## Steps

1. In Pulse, go to Settings, Security, Single sign-on.
2. Copy the Service Provider Entity ID and Assertion Consumer Service URL.
3. In your identity provider, create a SAML application with those values. Map the `email`
   attribute to the user's work email.
4. Copy the identity provider's metadata URL or upload its metadata XML into Pulse.
5. Click Test. Pulse opens your identity provider in a new tab and confirms the assertion
   parses correctly.
6. Choose whether to enforce SSO. When enforced, existing password logins stop working
   the next time each member signs in.

## Just-in-time provisioning

On Scale, new members who sign in through SSO for the first time are created
automatically in the Viewer role and count toward your seat allowance. On Enterprise you
can control this with SCIM.

## Troubleshooting

"Audience mismatch" means the Entity ID in your identity provider does not match Pulse.
"Missing email attribute" means the attribute mapping is wrong. Contact support with the
SAML trace if you are stuck; Scale and Enterprise customers receive priority support.
