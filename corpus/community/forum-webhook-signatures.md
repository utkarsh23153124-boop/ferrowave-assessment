# Community forum: Migrating from v1 to v2 webhook signatures

Posted in #developers

---

**jonas.b** (2 July 2026)

We verify `X-Pulse-Signature` today. I see the release notes say v1 is deprecated. How
long do we have?

---

**priya_dev** (2 July 2026)

From what I heard v1 goes away at the end of August. We migrated last week, took an
afternoon. The main gotcha is signing the raw body, not the parsed JSON.

---

**jonas.b** (3 July 2026)

Thanks. Is v2 sent for endpoints created before May, or do we need to recreate the
endpoint?

---

**priya_dev** (3 July 2026)

Both headers are sent on old endpoints, so you can switch verification without
recreating anything. New endpoints only get v2.

---

**hannah.r** (20 July 2026)

Just to add: the timestamp is in seconds, not milliseconds. We lost an hour on that.
