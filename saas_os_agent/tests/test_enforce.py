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
