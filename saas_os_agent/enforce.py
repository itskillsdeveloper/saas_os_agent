"""Quota enforcement that has to run inside the tenant site.

The control plane cannot intercept a user created inside a tenant's own site --
it is a different site in a different process. So the one rule that must bite at
the moment of creation lives here, and reads its limit from the tenant's
site_config, which the control plane maintains.
"""

from __future__ import annotations

import frappe

#: site_config key the control plane writes from the tenant's plan.
MAX_USERS_KEY = "saas_os_max_users"

#: User types that count against a seat limit. Website users (customers, portal
#: logins) are not seats and are never counted, matching how a plan's "users" is
#: normally sold.
COUNTED_TYPE = "System User"

#: Built-in accounts on every site; never counted or blocked, or the first
#: login would be impossible.
SEED_USERS = frozenset({"Administrator", "Guest"})


def normalise_limit(raw) -> int | None:
	"""The effective seat limit, or None for "do not enforce".

	None (no key), a non-integer, or a value <= 0 all mean no enforcement -- a
	0 must not lock a site out of ever creating a user.
	"""
	try:
		limit = int(raw)
	except (TypeError, ValueError):
		return None
	return limit if limit > 0 else None


def would_exceed(*, limit, current: int, user_type: str, identifier: str) -> bool:
	"""Pure decision: would inserting this user break the seat limit?

	`current` is the count of existing seats; the user being inserted is not in
	it, so `current >= limit` means adding it would exceed the plan. Separated
	from all frappe access so it can be tested exhaustively without a site.
	"""
	limit = normalise_limit(limit)
	if limit is None:
		return False
	if identifier in SEED_USERS:
		return False
	if (user_type or COUNTED_TYPE) != COUNTED_TYPE:
		return False
	return current >= limit


def enforce_user_quota(doc, method=None) -> None:
	"""before_insert hook on User. Throws when the seat limit is reached."""
	identifier = doc.name or doc.email or ""
	# Exclude the built-in accounts from the seat count, not just from being
	# blocked: Administrator holds no customer seat, so "max_users: 10" must
	# mean ten real users, not nine plus Administrator.
	current = frappe.db.count("User", {
		"user_type": COUNTED_TYPE, "enabled": 1,
		"name": ["not in", list(SEED_USERS)]})
	if would_exceed(limit=frappe.conf.get(MAX_USERS_KEY), current=current,
	                user_type=doc.user_type, identifier=identifier):
		frappe.throw(
			f"Your plan allows {normalise_limit(frappe.conf.get(MAX_USERS_KEY))} "
			f"users and you already have {current}. Upgrade the plan to add more.",
			title="User limit reached",
		)
