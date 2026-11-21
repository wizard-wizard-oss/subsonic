"""Réindexation Subsonic : autorisations, cycles ordonnés et confirmation bornée sans réseau."""
import threading
import unittest
from collections import deque
from types import SimpleNamespace

from pimedia.webapp.library_scan import LibraryScan
from pimedia.webapp.subsonic import SubsonicError, SubsonicUnreachable


def account(identity, admin=False):
    return SimpleNamespace(id=identity, username="user" + str(identity), is_admin=admin,
                           subsonic_salt="salt", subsonic_token="token")


class Clock:
    def __init__(self):
        self.now, self.sleeps = 0, []

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


class Subsonic:
    def __init__(self, statuses=(), refusals=None, status_refusals=None):
        self.statuses = deque(statuses)
        self.refusals = refusals or {}
        self.status_refusals = status_refusals or {}
        self.calls = []

    def call(self, credentials, endpoint):
        self.calls.append((endpoint, credentials.username))
        if endpoint == "startScan":
            error = self.refusals.get(credentials.username)
            if error:
                raise error
            return {"scanStatus": {"scanning": True}}
        if endpoint != "getScanStatus":
            raise AssertionError("Unexpected endpoint: " + endpoint)
        if credentials.username in self.status_refusals:
            raise self.status_refusals[credentials.username]
        if not self.statuses:
            raise AssertionError("Unexpected scan-status poll")
        response = self.statuses.popleft()
        if isinstance(response, Exception):
            raise response
        return {"scanStatus": {"scanning": response}} if type(response) is bool else response


class LibraryScanTest(unittest.TestCase):
    def setUp(self):
        self.reader = account(1)
        self.admins = [account(identity, True) for identity in range(2, 6)]
        self.clock = Clock()

    def scanner(self, subsonic, users=None):
        users = self.admins if users is None else users
        return LibraryScan(subsonic, SimpleNamespace(by_priority=lambda: users), self.clock, self.clock.sleep)

    def test_scan_uses_calling_account_then_known_admins_in_priority_order(self):
        api = Subsonic(refusals={"user1": SubsonicError(50), "user2": SubsonicError(40)})
        self.assertTrue(self.scanner(api).scan(self.reader))
        self.assertEqual(api.calls, [("startScan", "user1"), ("startScan", "user2"), ("startScan", "user3")])

    def test_calling_admin_is_not_attempted_twice(self):
        api = Subsonic(refusals={"user2": SubsonicError(40)})
        self.assertTrue(self.scanner(api).scan(self.admins[0]))
        self.assertEqual(api.calls, [("startScan", "user2"), ("startScan", "user3")])

    def test_background_scan_uses_only_admins_and_stops_after_three(self):
        api = Subsonic(refusals={admin.username: SubsonicError(40) for admin in self.admins})
        self.assertFalse(self.scanner(api, [self.reader, *self.admins]).scan_as_admin())
        self.assertEqual(api.calls, [("startScan", "user2"), ("startScan", "user3"), ("startScan", "user4")])

    def test_background_scan_without_a_known_admin_has_no_network_attempt(self):
        api = Subsonic()
        self.assertFalse(self.scanner(api, [self.reader]).scan_as_admin())
        self.assertEqual(api.calls, [])

    def test_unreachable_server_or_non_authorization_error_does_not_try_every_account(self):
        for error in (SubsonicUnreachable(), SubsonicError(70), SubsonicError(500)):
            with self.subTest(error=type(error).__name__):
                api = Subsonic(refusals={"user1": error})
                self.assertFalse(self.scanner(api).scan(self.reader))
                self.assertEqual(api.calls, [("startScan", "user1")])

    def test_wait_does_not_treat_missing_or_non_boolean_status_as_a_finished_scan(self):
        for response in ({}, {"scanStatus": None}, {"scanStatus": {}},
                         {"scanStatus": {"scanning": "false"}}, {"scanStatus": {"scanning": 0}},
                         SubsonicError(50), SubsonicUnreachable()):
            with self.subTest(response=response):
                api = Subsonic([response])
                self.assertFalse(self.scanner(api).wait(self.reader))
                self.assertEqual(api.calls, [("getScanStatus", "user1")])
                self.assertEqual(self.clock.sleeps, [])

    def test_wait_polls_until_the_server_reports_finished(self):
        api = Subsonic([True, True, False])
        self.assertTrue(self.scanner(api).wait(self.reader))
        self.assertEqual(self.clock.sleeps, [1, 1])
        self.assertEqual(len(api.calls), 3)

    def test_wait_timeout_is_bounded_and_never_reports_success(self):
        api = Subsonic([True] * 4)
        self.assertFalse(self.scanner(api).wait(self.reader, timeout=3))
        self.assertEqual((self.clock.now, len(api.calls)), (3, 3))
        self.assertEqual(self.clock.sleeps, [1, 1, 1])

    def test_zero_timeout_does_not_poll(self):
        api = Subsonic()
        self.assertFalse(self.scanner(api).wait(self.reader, timeout=0))
        self.assertEqual(api.calls, [])

    def test_synchronize_waits_for_existing_scan_then_starts_a_fresh_one(self):
        api = Subsonic([True, True, False, True, False])
        self.assertIs(self.scanner(api).synchronize(self.reader), True)
        self.assertEqual([endpoint for endpoint, _ in api.calls],
                         ["getScanStatus", "getScanStatus", "getScanStatus", "startScan", "getScanStatus", "getScanStatus"])
        self.assertEqual(self.clock.sleeps, [1, 1])

    def test_previous_scan_timeout_does_not_start_another_or_claim_success(self):
        api = Subsonic([True] * 91)
        self.assertIsNone(self.scanner(api).synchronize(self.reader))
        self.assertEqual(self.clock.now, 90)
        self.assertEqual([endpoint for endpoint, _ in api.calls], ["getScanStatus"] * 91)

    def test_previous_scan_status_failure_prevents_an_unconfirmed_new_cycle(self):
        api = Subsonic([True, SubsonicUnreachable()])
        self.assertIsNone(self.scanner(api).synchronize(self.reader))
        self.assertEqual([endpoint for endpoint, _ in api.calls], ["getScanStatus", "getScanStatus"])

    def test_refused_scan_is_distinct_from_an_unconfirmed_scan(self):
        refusals = {user.username: SubsonicError(50) for user in [self.reader, *self.admins]}
        api = Subsonic([False], refusals)
        self.assertIs(self.scanner(api).synchronize(self.reader), False)
        self.assertEqual(api.calls[0], ("getScanStatus", "user1"))
        self.assertEqual(len(api.calls), 5)

    def test_a_missing_status_after_start_never_becomes_a_success(self):
        for response in ({}, {"scanStatus": {}}, SubsonicUnreachable()):
            with self.subTest(response=response):
                api = Subsonic([False, response])
                self.assertIsNone(self.scanner(api).synchronize(self.reader))
                self.assertEqual([endpoint for endpoint, _ in api.calls], ["getScanStatus", "startScan", "getScanStatus"])

    def test_unknown_initial_status_still_requires_a_confirmed_final_status(self):
        api = Subsonic([{}, {}])
        self.assertIsNone(self.scanner(api).synchronize(self.reader))
        self.assertEqual([endpoint for endpoint, _ in api.calls], ["getScanStatus", "startScan", "getScanStatus"])

    def test_non_admin_can_synchronize_through_a_known_admin(self):
        api = Subsonic([False, True, False], refusals={"user1": SubsonicError(50)},
                       status_refusals={"user1": SubsonicError(50)})
        self.assertIs(self.scanner(api).synchronize(self.reader), True)
        self.assertEqual(api.calls, [("getScanStatus", "user1"), ("getScanStatus", "user2"),
                                    ("startScan", "user1"), ("startScan", "user2"),
                                    ("getScanStatus", "user2"), ("getScanStatus", "user2")])

    def test_non_admin_waits_for_previous_scan_using_the_valid_admin(self):
        api = Subsonic([True, True, False, True, False], refusals={"user1": SubsonicError(50)},
                       status_refusals={"user1": SubsonicError(50)})
        self.assertIs(self.scanner(api).synchronize(self.reader), True)
        self.assertEqual(api.calls, [("getScanStatus", "user1"), ("getScanStatus", "user2"),
                                    ("getScanStatus", "user2"), ("getScanStatus", "user2"),
                                    ("startScan", "user1"), ("startScan", "user2"),
                                    ("getScanStatus", "user2"), ("getScanStatus", "user2")])
        self.assertEqual(self.clock.sleeps, [1, 1])

    def test_expired_first_admin_is_not_reused_to_confirm_a_successful_fallback(self):
        refusals = {"user1": SubsonicError(50), "user2": SubsonicError(40)}
        api = Subsonic([False, False], refusals=refusals, status_refusals=refusals)
        self.assertIs(self.scanner(api).synchronize(self.reader), True)
        self.assertEqual(api.calls, [("getScanStatus", "user1"), ("getScanStatus", "user2"),
                                    ("getScanStatus", "user3"), ("startScan", "user1"),
                                    ("startScan", "user2"), ("startScan", "user3"), ("getScanStatus", "user3")])

    def test_final_observer_is_the_account_that_actually_started_the_scan(self):
        api = Subsonic([False, False], status_refusals={"user1": SubsonicError(50)},
                       refusals={"user1": SubsonicError(50), "user2": SubsonicError(40)})
        self.assertIs(self.scanner(api).synchronize(self.reader), True)
        self.assertEqual(api.calls, [("getScanStatus", "user1"), ("getScanStatus", "user2"),
                                    ("startScan", "user1"), ("startScan", "user2"),
                                    ("startScan", "user3"), ("getScanStatus", "user3")])

    def test_observer_and_start_fallbacks_both_stop_after_three_known_admins(self):
        refusals = {user.username: SubsonicError(40) for user in [self.reader, *self.admins[:3]]}
        api = Subsonic(refusals=refusals, status_refusals=refusals)
        self.assertIs(self.scanner(api).synchronize(self.reader), False)
        self.assertNotIn("user5", {username for _, username in api.calls})
        self.assertEqual(len(api.calls), 8)

    def test_non_admin_without_a_known_admin_cannot_claim_scan_completion(self):
        refusals = {"user1": SubsonicError(50)}
        api = Subsonic(refusals=refusals, status_refusals=refusals)
        self.assertIs(self.scanner(api, []).synchronize(self.reader), False)
        self.assertEqual(api.calls, [("getScanStatus", "user1"), ("startScan", "user1")])

    def test_two_synchronize_calls_cannot_interleave_their_scan_cycles(self):
        entered, release, second_started = threading.Event(), threading.Event(), threading.Event()
        calls, results, errors = [], {}, []
        statuses = {"user1": 0, "user2": 0}

        def call(credentials, endpoint):
            user = credentials.username
            calls.append((endpoint, user))
            if endpoint == "getScanStatus":
                statuses[user] += 1
                if user == "user1" and statuses[user] == 2:
                    entered.set()
                    if not release.wait(2):
                        raise AssertionError("First scan was not released")
                return {"scanStatus": {"scanning": False}}
            return {"scanStatus": {"scanning": True}}

        scanner = self.scanner(SimpleNamespace(call=call))

        def run(user, signal=None):
            if signal:
                signal.set()
            try:
                results[user.username] = scanner.synchronize(user)
            except BaseException as error:
                errors.append(error)

        first = threading.Thread(target=run, args=(self.reader,))
        second = threading.Thread(target=run, args=(self.admins[0], second_started))
        first.start()
        try:
            self.assertTrue(entered.wait(2))
            second.start()
            self.assertTrue(second_started.wait(2))
            self.assertEqual({user for _, user in calls}, {"user1"})
        finally:
            release.set()
            first.join(2)
            if second.ident is not None:
                second.join(2)
        self.assertFalse(first.is_alive())
        self.assertFalse(second.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(results, {"user1": True, "user2": True})
        self.assertEqual(calls, [("getScanStatus", "user1"), ("startScan", "user1"), ("getScanStatus", "user1"),
                                 ("getScanStatus", "user2"), ("startScan", "user2"), ("getScanStatus", "user2")])


if __name__ == "__main__":
    unittest.main()
