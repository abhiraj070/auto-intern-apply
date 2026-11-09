import contextlib
import io
import json
import os
import tempfile
import unittest
from datetime import date, datetime, timezone
from unittest.mock import Mock, patch

import tracker


def response(data=None, status=204):
    result = Mock()
    result.status = status
    result.read.return_value = json.dumps(data).encode("utf-8")
    result.__enter__ = Mock(return_value=result)
    result.__exit__ = Mock(return_value=False)
    return result


def job(index, **overrides):
    item = {"id": str(index), "company_name": "Acme", "title": "Software Engineer Intern",
            "url": "https://example.com/jobs/{}".format(index), "locations": ["India"], "active": True,
            "date_posted": "2026-11-09"}
    item.update(overrides)
    return item


class StipendTests(unittest.TestCase):
    def test_common_description_formats_and_ranges(self):
        cases = [
            ("Stipend: INR 5,000/month", False),
            ("Stipend: INR 20,000/month", True),
            ("Stipend: Rs. 5,000 per month", False),
            ("Stipend: ₹5,000/month", False),
            ("Stipend: INR 2.5k per month", False),
            ("Stipend: INR 5-15k/month", False),
            ("Salary: INR 1.2 lakh per annum", True),
            ("Salary: INR 1 lakh per annum", False),
            ("Stipend: INR 0 per month", False),
            ("<p>Stipend: INR&nbsp;5,000/month</p>", False),
            ("This is an unpaid internship", False),
            ("Competitive salary with 2 years of experience", True),
            ("Salary, competitive and undisclosed", True),
            ("Competitive / Disclosed on Apply", True),
        ]
        for description, expected in cases:
            with self.subTest(description=description):
                self.assertEqual(tracker.parse_and_filter_stipend(
                    None, None, None, description)[0], expected)

    def test_structured_minimum_controls_range_and_zero_is_unpaid(self):
        self.assertFalse(tracker.parse_and_filter_stipend(5000, 20000, "MONTH", "", currency="INR")[0])
        self.assertFalse(tracker.parse_and_filter_stipend(0, 20000, "MONTH", "", currency="INR")[0])
        self.assertTrue(tracker.parse_and_filter_stipend("120,000", None, "YEAR", "", currency="INR")[0])
        self.assertFalse(tracker.parse_and_filter_stipend(50, None, "HOUR", "", currency="INR")[0])

    def test_explicit_unpaid_overrides_structured_pay(self):
        self.assertFalse(tracker.parse_and_filter_stipend(20000, None, "MONTH", "Unpaid", currency="INR")[0])

    def test_foreign_currency_is_not_treated_as_inr(self):
        passed, label = tracker.parse_and_filter_stipend(1000, None, "MONTH", "", currency="USD")
        self.assertTrue(passed)
        self.assertIn("USD", label)
        self.assertIn("unverified", label)
        passed, label = tracker.parse_and_filter_stipend(
            1000, None, "MONTH", "", currency="USD", currency_to_inr={"USD": 80})
        self.assertTrue(passed)
        self.assertNotIn("unverified", label)
        self.assertFalse(tracker.parse_and_filter_stipend(
            100, None, "MONTH", "", currency="USD", currency_to_inr={"USD": 80})[0])

    def test_foreign_description_overrides_indian_location_default(self):
        passed, label = tracker.parse_and_filter_stipend(
            None, None, None, "Stipend: USD 500/month", default_currency="INR")
        self.assertTrue(passed)
        self.assertIn("USD", label)

    def test_unknown_currency_and_period_are_not_invented(self):
        for currency, period in [(None, "MONTH"), ("INR", None)]:
            with self.subTest(currency=currency, period=period):
                self.assertIn("unverified", tracker.parse_and_filter_stipend(
                    1000, None, period, "", currency=currency)[1])

    def test_structured_currency_applies_to_bare_description_amounts(self):
        passed, label = tracker.parse_and_filter_stipend(
            500, None, "MONTH", "Stipend: 500/month", currency="USD", default_currency="INR")
        self.assertTrue(passed)
        self.assertIn("USD", label)

    def test_custom_stipend_threshold_is_enforced(self):
        self.assertFalse(tracker.parse_and_filter_stipend(
            None, None, None, "Stipend: INR 12k/month", min_stipend=15000)[0])


class RoleAndDedupTests(unittest.TestCase):
    def test_internships_only(self):
        self.assertTrue(tracker.is_target_role("Backend Developer Intern"))
        self.assertTrue(tracker.is_target_role("Software Engineer", ["INTERN"]))
        for title in ["Senior Software Engineer", "Junior Backend Developer", "Software Engineer",
                      "International Software Engineer", "Senior Software Engineer Intern"]:
            with self.subTest(title=title):
                self.assertFalse(tracker.is_target_role(title))

    def test_same_title_distinct_requisitions(self):
        a = tracker.get_canonical_keys("Acme", "Software Engineer Intern", "https://example.com/one", "one")
        b = tracker.get_canonical_keys("Acme", "Software Engineer Intern", "https://example.com/two", "two")
        self.assertFalse(a & b)

    def test_tracking_query_removal_preserves_job_ids_and_path_case(self):
        a = tracker.get_canonical_keys("", "", "https://EXAMPLE.com/Jobs/A?utm_source=a&job=123&ref=abc")
        b = tracker.get_canonical_keys("", "", "https://example.com/Jobs/A?job=123")
        self.assertEqual(a, b)
        self.assertFalse(a & tracker.get_canonical_keys("", "", "https://example.com/Jobs/a?job=123"))
        self.assertFalse(a & tracker.get_canonical_keys("", "", "https://example.com/Jobs/A?job=456"))


class PipelineTests(unittest.TestCase):
    def run_tracker(self, simplify=None, arbeitnow=None, jsearch=None, webhook=True, seen=None, effects=None):
        snapshots = []
        with contextlib.ExitStack() as stack:
            stack.enter_context(patch.object(tracker, "posting_window", return_value=(date(2026, 9, 9), date(2026, 11, 9))))
            stack.enter_context(patch.object(tracker.os.path, "exists", return_value=False))
            stack.enter_context(patch.dict(tracker.os.environ, {
                "DISCORD_WEBHOOK_URL": "https://discord.com/api/webhooks/mock" if webhook else "",
                "RAPIDAPI_KEY": ""}))
            stack.enter_context(patch.object(tracker, "load_seen", return_value=set(seen or [])))
            stack.enter_context(patch.object(tracker, "save_seen", side_effect=lambda ids: snapshots.append(set(ids))))
            stack.enter_context(patch.object(tracker, "fetch_simplify_listings", side_effect=[simplify or [], []]))
            stack.enter_context(patch.object(tracker, "fetch_arbeitnow_listings", return_value=arbeitnow or []))
            stack.enter_context(patch.object(tracker, "fetch_jsearch_listings", return_value=jsearch or []))
            stack.enter_context(patch.object(tracker.time, "sleep"))
            sender = stack.enter_context(patch.object(tracker.urllib.request, "urlopen"))
            sender.side_effect = effects
            sender.return_value = response()
            output = stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
            result = tracker.main()
            payloads = [json.loads(call[0][0].data.decode("utf-8")) for call in sender.call_args_list]
            return result, snapshots, payloads, output.getvalue()

    def test_preview_does_not_consume_jobs(self):
        result, snapshots, payloads, _ = self.run_tracker(simplify=[job(1)], webhook=False)
        self.assertTrue(result)
        self.assertEqual(snapshots, [])
        self.assertEqual(payloads, [])

    def test_posting_age_filter_applies_to_every_source_before_marking_seen(self):
        result, snapshots, payloads, output = self.run_tracker(
            simplify=[job(1, date_posted="2026-09-08", date_updated="2026-11-09"),
                      job(2, date_posted="2026-09-09")],
            arbeitnow=[job(3, date_posted=None, posted_at="2026-08-01"),
                       job(4, date_posted=None, posted_at="2026-11-09")],
            jsearch=[job(5, date_posted=None, posted_at="2026-09-08T00:00:00Z"),
                     job(6, date_posted=None, posted_at="2026-10-01T00:00:00Z")])
        self.assertTrue(result)
        self.assertEqual(len(payloads[0]["embeds"]), 3)
        self.assertTrue({"2", "4", "6"} <= snapshots[-1])
        self.assertFalse({"1", "3", "5"} & snapshots[-1])
        self.assertIn("Skipped 3 listings", output)
        for embed in payloads[0]["embeds"]:
            self.assertTrue(any(field["name"] == "Posted (IST)" for field in embed["fields"]))

    def test_missing_invalid_and_future_dates_are_skipped(self):
        result, snapshots, payloads, output = self.run_tracker(simplify=[
            job(1, date_posted=None), job(2, date_posted="invalid"),
            job(3, date_posted="2026-11-10"), job(4, date_posted=None, date_updated="2026-11-09")])
        self.assertTrue(result)
        self.assertEqual(snapshots, [])
        self.assertEqual(payloads, [])
        self.assertIn("Skipped 4 listings", output)

    def test_old_copy_does_not_suppress_a_recent_copy(self):
        result, snapshots, payloads, _ = self.run_tracker(
            simplify=[job(1, date_posted="2026-07-01")], jsearch=[job(1)])
        self.assertTrue(result)
        self.assertEqual(len(payloads[0]["embeds"]), 1)
        self.assertIn("1", snapshots[-1])

    def test_failed_delivery_stays_unseen_and_returns_failure(self):
        result, snapshots, _, output = self.run_tracker(simplify=[job(1)], effects=OSError("offline"))
        self.assertFalse(result)
        self.assertEqual(snapshots, [])
        self.assertNotIn("sent successfully", output)

    def test_partial_delivery_checkpoints_only_successful_batches(self):
        result, snapshots, payloads, _ = self.run_tracker(
            simplify=[job(i) for i in range(25)],
            effects=[response(), OSError("offline"), response()])
        self.assertFalse(result)
        self.assertEqual(len(payloads), 3)
        self.assertEqual(len(snapshots), 2)
        final = snapshots[-1]
        for i in range(25):
            self.assertEqual(str(i) in final, i < 10 or i >= 20)
        retry_result, _, retry_payloads, _ = self.run_tracker(
            simplify=[job(i) for i in range(25)], seen=final)
        self.assertTrue(retry_result)
        self.assertEqual(sum(len(p["embeds"]) for p in retry_payloads), 10)

    def test_http_rejection_stays_unseen(self):
        error = tracker.urllib.error.HTTPError("https://example.com", 429, "rate limited", {}, io.BytesIO(b"retry later"))
        result, snapshots, _, _ = self.run_tracker(simplify=[job(1)], effects=error)
        self.assertFalse(result)
        self.assertEqual(snapshots, [])

    def test_pay_filter_applies_to_every_source(self):
        result, snapshots, payloads, _ = self.run_tracker(
            simplify=[job(1, description="Unpaid internship"), job(2, stipend="INR 5,000/month")],
            arbeitnow=[job(3, description="<p>Stipend: INR 5k per month</p>")],
            jsearch=[job(4, salary_min=5000, salary_period="MONTH", salary_currency="INR"), job(5)])
        self.assertTrue(result)
        self.assertEqual(len(payloads[0]["embeds"]), 1)
        self.assertIn("5", snapshots[-1])
        self.assertFalse({"1", "2", "3", "4"} & snapshots[-1])

    def test_same_requisition_across_sources_is_sent_once(self):
        result, _, payloads, _ = self.run_tracker(simplify=[job(1)], jsearch=[job("alternate", url=job(1)["url"])])
        self.assertTrue(result)
        self.assertEqual(len(payloads[0]["embeds"]), 1)

    def test_old_title_signature_does_not_hide_new_job(self):
        result, _, payloads, _ = self.run_tracker(simplify=[job(1), job(2)],
            seen={"sig:acme:softwareengineerintern", "1", "https://example.com/jobs/1"})
        self.assertTrue(result)
        self.assertEqual(len(payloads[0]["embeds"]), 1)
        self.assertTrue(payloads[0]["embeds"][0]["url"].endswith("/2"))

    def test_senior_and_full_time_results_are_rejected(self):
        result, _, payloads, _ = self.run_tracker(jsearch=[
            job(1, title="Senior Software Engineer"), job(2, title="Software Engineer"), job(3)])
        self.assertTrue(result)
        self.assertEqual(len(payloads[0]["embeds"]), 1)

    def test_long_embeds_are_split_within_discord_limits(self):
        _, _, payloads, _ = self.run_tracker(simplify=[job(i, company_name="x" * 2000) for i in range(12)])
        self.assertGreater(len(payloads), 1)
        for payload in payloads:
            count = 0
            for embed in payload["embeds"]:
                count += len(embed["title"]) + len(embed["description"]) + len(embed["footer"]["text"])
                for field in embed["fields"]:
                    self.assertLessEqual(len(field["value"]), 1024)
                    count += len(field["name"]) + len(field["value"])
            self.assertLessEqual(count, 6000)


class StateTests(unittest.TestCase):
    def test_atomic_replace_keeps_old_database_on_failure(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(
                tracker, "SEEN_FILE", os.path.join(directory, "seen.json")):
            tracker.save_seen({"old"})
            with patch.object(tracker.os, "replace", side_effect=OSError("disk error")):
                with self.assertRaises(OSError):
                    tracker.save_seen({"new"})
            self.assertEqual(tracker.load_seen(), {"old"})
            tracker.save_seen({"old", "new"})
            self.assertEqual(tracker.load_seen(), {"old", "new"})

    def test_checkpoint_failure_is_not_swallowed_as_network_error(self):
        with patch.object(tracker.urllib.request, "urlopen", return_value=response()), \
                patch.object(tracker.time, "sleep"):
            checkpoint = Mock(side_effect=OSError("disk error"))
            with self.assertRaises(OSError):
                tracker.send_discord_webhook("https://example.com", [{"title": "intern"}], checkpoint)


class PostingDateTests(unittest.TestCase):
    def test_calendar_month_cutoff_and_month_end_clamping(self):
        cases = [
            (date(2026, 11, 9), date(2026, 9, 9)),
            (date(2026, 1, 31), date(2025, 11, 30)),
            (date(2026, 4, 30), date(2026, 2, 28)),
            (date(2024, 4, 30), date(2024, 2, 29)),
        ]
        for today, cutoff in cases:
            with self.subTest(today=today):
                self.assertEqual(tracker.posting_window(today), (cutoff, today))

    def test_runtime_clock_uses_ist(self):
        with patch.object(tracker, "datetime") as clock:
            clock.now.return_value.date.return_value = date(2026, 11, 9)
            self.assertEqual(tracker.posting_window(), (date(2026, 9, 9), date(2026, 11, 9)))
            clock.now.assert_called_once_with(tracker.POSTING_TIMEZONE)

    def test_iso_timestamps_are_converted_to_ist(self):
        for value in ["2026-09-08T20:00:00Z", "2026-09-08T20:00:00+00:00",
                      "2026-09-09T01:30:00+05:30", "2026-09-08T20:00:00"]:
            with self.subTest(value=value):
                self.assertEqual(tracker.parse_posting_date(value), date(2026, 9, 9))
        self.assertEqual(tracker.parse_posting_date("2026-09-09"), date(2026, 9, 9))

    def test_unix_seconds_milliseconds_and_numeric_strings(self):
        seconds = int(datetime(2026, 9, 8, 20, tzinfo=timezone.utc).timestamp())
        for value in [seconds, float(seconds), seconds * 1000, str(seconds), str(seconds * 1000)]:
            with self.subTest(value=value):
                self.assertEqual(tracker.parse_posting_date(value), date(2026, 9, 9))

    def test_malformed_dates_do_not_crash_or_use_update_dates(self):
        for value in [None, "", "not a date", "2026-02-30", "2026-09-09garbage", True,
                      {}, float("inf"), float("nan"), 10 ** 30]:
            with self.subTest(value=value):
                self.assertIsNone(tracker.parse_posting_date(value))
        self.assertIsNone(tracker.get_posting_date({"date_updated": "2026-11-09"}))
        self.assertEqual(tracker.get_posting_date(
            {"date_posted": "2026-07-01", "date_updated": "2026-11-09"}), date(2026, 7, 1))

    def test_invalid_primary_date_can_fall_back_to_timestamp(self):
        seconds = int(datetime(2026, 10, 1, tzinfo=timezone.utc).timestamp())
        self.assertEqual(tracker.get_posting_date(
            {"posted_at": "bad", "posted_at_timestamp": seconds}), date(2026, 10, 1))


class FetchTests(unittest.TestCase):
    def test_all_five_queries_run_and_preserve_currency_and_type(self):
        data = {"data": [{"job_id": "id", "job_title": "Software Engineer", "job_country": "IN",
                          "job_min_salary": 1000, "job_salary_currency": "USD",
                          "job_employment_types": ["INTERN"], "job_description": "Paid",
                          "job_posted_at_datetime_utc": "2026-10-01T00:00:00Z",
                          "job_posted_at_timestamp": 1790812800}]}
        with patch.object(tracker.urllib.request, "urlopen", return_value=response(data)) as sender:
            jobs = tracker.fetch_jsearch_listings("dummy")
        urls = [tracker.urllib.parse.unquote(call[0][0].full_url) for call in sender.call_args_list]
        self.assertEqual(len(urls), 5)
        self.assertTrue(any("Fullstack" in url for url in urls))
        self.assertTrue(any("Remote" in url for url in urls))
        self.assertEqual(jobs[0]["salary_currency"], "USD")
        self.assertEqual(jobs[0]["employment_types"], ["INTERN"])
        self.assertEqual(jobs[0]["locations"], ["India"])
        self.assertEqual(jobs[0]["posted_at"], "2026-10-01T00:00:00Z")
        self.assertEqual(jobs[0]["posted_at_timestamp"], 1790812800)

    def test_arbeitnow_keeps_description_and_excludes_junior(self):
        data = {"data": [{"title": "Backend Intern", "description": "unpaid", "created_at": 1790812800},
                         {"title": "Junior Backend Developer"}]}
        with patch.object(tracker.urllib.request, "urlopen", return_value=response(data)):
            jobs = tracker.fetch_arbeitnow_listings()
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["description"], "unpaid")
        self.assertEqual(jobs[0]["posted_at"], 1790812800)

    def test_simplify_preserves_original_posting_date(self):
        data = [job(1, date_posted=1790812800, date_updated=1794268800)]
        with patch.object(tracker.urllib.request, "urlopen", return_value=response(data)):
            jobs = tracker.fetch_simplify_listings("test-feed")
        self.assertEqual(jobs[0]["date_posted"], 1790812800)


if __name__ == "__main__":
    unittest.main()
