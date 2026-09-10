"""The seat-limit decision, tested exhaustively without a site.

`would_exceed` is pure by design so every branch can be checked here; the
frappe-touching wrapper is exercised end to end by the SaaS OS integration
suite, which provisions a tenant with the agent and tries to exceed its plan.
"""

from __future__ import annotations

import unittest

from saas_os_agent import enforce


class TestSeatLimitDecision(unittest.TestCase):
	def test_no_limit_configured_never_blocks(self):
		self.assertFalse(enforce.would_exceed(
			limit=None, current=9999, user_type="System User", identifier="a@b.c"))

	def test_a_non_integer_limit_is_ignored(self):
		self.assertFalse(enforce.would_exceed(
			limit="lots", current=10, user_type="System User", identifier="a@b.c"))

	def test_zero_or_negative_limit_means_no_enforcement(self):
		for bad in (0, -1, "0"):
			with self.subTest(limit=bad):
				self.assertFalse(enforce.would_exceed(
					limit=bad, current=5, user_type="System User", identifier="a@b.c"))

	def test_under_the_limit_is_allowed(self):
		self.assertFalse(enforce.would_exceed(
			limit=10, current=9, user_type="System User", identifier="a@b.c"))

	def test_at_the_limit_is_blocked(self):
		"""current == limit: adding one more would make it limit+1."""
		self.assertTrue(enforce.would_exceed(
			limit=10, current=10, user_type="System User", identifier="a@b.c"))

	def test_over_the_limit_is_blocked(self):
		self.assertTrue(enforce.would_exceed(
			limit=3, current=5, user_type="System User", identifier="a@b.c"))

	def test_website_users_do_not_count_as_seats(self):
		self.assertFalse(enforce.would_exceed(
			limit=3, current=99, user_type="Website User", identifier="portal@b.c"))

	def test_builtin_users_are_never_blocked(self):
		for seed in ("Administrator", "Guest"):
			with self.subTest(user=seed):
				self.assertFalse(enforce.would_exceed(
					limit=1, current=50, user_type="System User", identifier=seed))

	def test_a_missing_user_type_defaults_to_a_seat(self):
		"""User.user_type unset should be treated as a System User, not skipped."""
		self.assertTrue(enforce.would_exceed(
			limit=2, current=2, user_type=None, identifier="a@b.c"))

	def test_normalise_limit(self):
		self.assertEqual(enforce.normalise_limit("10"), 10)
		self.assertIsNone(enforce.normalise_limit(None))
		self.assertIsNone(enforce.normalise_limit(0))
		self.assertIsNone(enforce.normalise_limit("x"))


class TestStorageLimitDecision(unittest.TestCase):
	"""The storage decision, tested the same way: pure, so every boundary is
	reachable without a site."""

	def _exceeds(self, **kw):
		args = dict(limit_mb=100, database_mb=0, files_mb=0.0, incoming_mb=0.0)
		args.update(kw)
		return enforce.storage_would_exceed(**args)

	def test_no_limit_configured_never_blocks(self):
		for limit in (None, 0, -1, "", "not a number"):
			with self.subTest(limit=limit):
				self.assertFalse(self._exceeds(limit_mb=limit, files_mb=99999.0))

	def test_room_left_is_allowed(self):
		self.assertFalse(self._exceeds(database_mb=40, files_mb=50.0, incoming_mb=9.0))

	def test_exactly_at_the_limit_is_allowed(self):
		"""A plan of 100 MB means 100 MB is usable, not 99."""
		self.assertFalse(self._exceeds(database_mb=40, files_mb=50.0, incoming_mb=10.0))

	def test_one_byte_past_the_limit_is_refused(self):
		self.assertTrue(self._exceeds(database_mb=40, files_mb=50.0, incoming_mb=10.001))

	def test_the_database_counts_toward_the_limit(self):
		"""Files alone fit; with the database they do not. A storage plan
		covers both, so ignoring the database would sell headroom twice."""
		self.assertFalse(self._exceeds(database_mb=0, files_mb=90.0, incoming_mb=5.0))
		self.assertTrue(self._exceeds(database_mb=20, files_mb=90.0, incoming_mb=5.0))

	def test_an_unmeasured_database_is_treated_as_zero_not_as_unknown(self):
		"""Until the daily walk has run there is no figure. Refusing every
		upload until then would be worse than counting files only."""
		self.assertFalse(self._exceeds(database_mb=None, files_mb=10.0, incoming_mb=1.0))

	def test_negative_or_junk_sizes_never_create_headroom(self):
		"""A negative file_size must not subtract from usage."""
		self.assertTrue(self._exceeds(database_mb=100, files_mb=-500.0, incoming_mb=1.0))
		self.assertTrue(self._exceeds(database_mb=101, files_mb=0.0, incoming_mb=-5.0))

	def test_bytes_convert_and_bad_values_are_zero(self):
		self.assertAlmostEqual(enforce.bytes_to_mb(1024 * 1024), 1.0)
		for junk in (None, "", "abc", object()):
			with self.subTest(junk=junk):
				self.assertEqual(enforce.bytes_to_mb(junk), 0.0)
		self.assertEqual(enforce.bytes_to_mb(-1), 0.0,
		                 "a negative size must never read as headroom")

	def test_the_two_quotas_share_the_same_disabled_rule(self):
		"""Seats and storage must agree on what "no limit" means, or an
		operator sets 0 expecting one behaviour and gets the other."""
		for raw in (None, 0, -5, "junk"):
			with self.subTest(raw=raw):
				self.assertIsNone(enforce.normalise_limit(raw))
