"""Quota enforcement that has to run inside the tenant site.

The control plane cannot intercept a user created inside a tenant's own site --
it is a different site in a different process. So the one rule that must bite at
the moment of creation lives here, and reads its limit from the tenant's
site_config, which the control plane maintains.
"""

from __future__ import annotations

import frappe

#: site_config keys the control plane writes from the tenant's plan.
MAX_USERS_KEY = "saas_os_max_users"
MAX_STORAGE_MB_KEY = "saas_os_max_storage_mb"

#: The tenant's database size in MB, as of the control plane's last daily
#: measurement. The agent cannot measure this cheaply from inside the site --
#: it would be an information_schema scan on every upload -- and the control
#: plane already walks it once a day, so the figure is pushed here instead.
DB_MB_KEY = "saas_os_database_mb"

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


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------
#
# A plan's `max_storage_mb` covers database *and* files. Only one of those two
# can honestly be blocked: a file upload is a discrete event with a known size,
# while database growth is a thousand small writes and cannot be refused at the
# byte without breaking the site. So this stops the half that is gateable and
# says so, rather than pretending to enforce the whole limit.
#
# The database figure is whatever the control plane last measured. That makes
# the headroom slightly stale -- stated in the message, so nobody reads the
# number as live.


def bytes_to_mb(size) -> float:
	try:
		return max(0.0, float(size or 0)) / (1024 * 1024)
	except (TypeError, ValueError):
		return 0.0


def storage_would_exceed(*, limit_mb, database_mb, files_mb: float,
                         incoming_mb: float) -> bool:
	"""Pure decision: would storing this file break the plan's storage limit?

	Separated from all frappe access so every boundary can be tested without a
	site. A limit that is absent, unparseable or <= 0 means no enforcement --
	the same rule seats use, so an unlimited plan never locks a site out.
	"""
	limit = normalise_limit(limit_mb)
	if limit is None:
		return False
	used = float(database_mb or 0) + max(0.0, files_mb)
	# The file being inserted is not on disk yet, so it is added explicitly.
	return (used + max(0.0, incoming_mb)) > limit


def _files_mb() -> float:
	"""Live size of everything the site's File records account for.

	`File.file_size` is what Frappe already records per upload, so this is a
	single SUM rather than a directory walk on every insert.
	"""
	rows = frappe.db.sql("SELECT COALESCE(SUM(file_size), 0) FROM `tabFile`")
	return bytes_to_mb(rows[0][0] if rows else 0)


def enforce_storage_quota(doc, method=None) -> None:
	"""before_insert hook on File. Throws when the plan's storage is used up."""
	limit_mb = normalise_limit(frappe.conf.get(MAX_STORAGE_MB_KEY))
	if limit_mb is None:
		return

	# A folder is a File row with no content; refusing one would block the
	# ordinary act of organising files without freeing a byte.
	if getattr(doc, "is_folder", 0):
		return

	database_mb = float(frappe.conf.get(DB_MB_KEY) or 0)
	files_mb = _files_mb()
	incoming_mb = bytes_to_mb(getattr(doc, "file_size", 0))

	if storage_would_exceed(limit_mb=limit_mb, database_mb=database_mb,
	                        files_mb=files_mb, incoming_mb=incoming_mb):
		used = database_mb + files_mb
		frappe.throw(
			f"Your plan allows {limit_mb} MB of storage and about {used:.0f} MB is "
			f"already in use ({files_mb:.0f} MB of files plus {database_mb:.0f} MB "
			"of database at the last measurement). Delete something or upgrade "
			"the plan.",
			title="Storage limit reached",
		)
