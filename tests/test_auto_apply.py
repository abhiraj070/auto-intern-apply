import contextlib
import io
import unittest
from unittest.mock import Mock, patch

import auto_apply
from selenium.common.exceptions import TimeoutException


class ApplicationTests(unittest.TestCase):
    def test_lever_does_not_answer_unrelated_radio_questions(self):
        driver = Mock()
        with patch.object(auto_apply.time, "sleep"), patch.object(auto_apply, "fill_input", return_value=True), \
                patch.object(auto_apply, "upload_file", return_value=True):
            auto_apply.apply_lever(driver, {"work_authorization": {"requires_sponsorship": False}}, "unused.pdf")
        driver.find_elements.assert_not_called()
        driver.execute_script.assert_not_called()

    def test_failed_resume_upload_prevents_auto_submission(self):
        for handler in [auto_apply.apply_lever, auto_apply.apply_greenhouse]:
            with self.subTest(handler=handler.__name__), patch.object(auto_apply.time, "sleep"), \
                    patch.object(auto_apply, "fill_input", return_value=True), \
                    patch.object(auto_apply, "upload_file", return_value=False), \
                    patch.object(auto_apply, "submit_application") as submit:
                driver = Mock()
                driver.find_elements.return_value = []
                self.assertFalse(handler(driver, {}, "unused.pdf", auto_submit=True))
                submit.assert_not_called()

    def test_submission_requires_receipt(self):
        driver = Mock()
        driver.execute_script.return_value = True
        driver.find_element.return_value.text = "Application form"
        for confirmed in [True, False]:
            with self.subTest(confirmed=confirmed), patch.object(auto_apply, "WebDriverWait") as wait:
                button = Mock()
                wait.return_value.until.side_effect = [button, True if confirmed else TimeoutException("no receipt")]
                self.assertEqual(auto_apply.submit_application(driver, ("id", "submit")), confirmed)
                button.click.assert_called_once_with()
                receipt_check = wait.return_value.until.call_args_list[1][0][0]
                driver.find_element.return_value.text = "Please answer all required questions"
                self.assertFalse(receipt_check(driver))
                driver.find_element.return_value.text = "Thank you for applying"
                self.assertTrue(receipt_check(driver))
                driver.find_element.return_value.text = "Application form"

    def test_invalid_required_answers_prevent_click(self):
        driver = Mock()
        driver.execute_script.return_value = False
        with patch.object(auto_apply, "WebDriverWait") as wait:
            self.assertFalse(auto_apply.submit_application(driver, ("id", "submit")))
        wait.assert_not_called()

    def test_preexisting_receipt_prevents_new_submission(self):
        driver = Mock()
        driver.execute_script.return_value = True
        driver.find_element.return_value.text = "Your application has been submitted"
        with patch.object(auto_apply, "WebDriverWait") as wait:
            self.assertFalse(auto_apply.submit_application(driver, ("id", "submit")))
        wait.assert_not_called()

    def run_application(self, url, mode, confirmed=False):
        with contextlib.ExitStack() as stack:
            stack.enter_context(patch.object(auto_apply, "load_profile", return_value={}))
            stack.enter_context(patch.object(auto_apply.os.path, "exists", return_value=True))
            stack.enter_context(patch.object(auto_apply.time, "sleep"))
            stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
            driver = Mock()
            driver.current_url = url
            stack.enter_context(patch.object(auto_apply, "get_driver", return_value=driver))
            handlers = {name: stack.enter_context(patch.object(auto_apply, name, return_value=confirmed))
                        for name in ["apply_lever", "apply_greenhouse", "apply_ashby", "apply_generic"]}
            prompt = stack.enter_context(patch("builtins.input", return_value=""))
            result = auto_apply.apply_to_job(url, mode=mode)
            return result, driver, handlers, prompt

    def test_unsupported_auto_mode_hands_off_to_manual_review(self):
        for url, handler in [("https://jobs.ashbyhq.com/acme/1", "apply_ashby"),
                             ("https://example.com/jobs/1", "apply_generic")]:
            with self.subTest(url=url):
                result, driver, handlers, prompt = self.run_application(url, "auto")
                self.assertFalse(result)  # No confirmed automatic submission.
                self.assertFalse(handlers[handler].call_args[1]["auto_submit"])
                prompt.assert_called_once()
                driver.quit.assert_called_once()

    def test_unsupported_headless_mode_fails_before_upload(self):
        result, driver, handlers, prompt = self.run_application("https://jobs.ashbyhq.com/acme/1", "headless")
        self.assertFalse(result)
        for handler in handlers.values():
            handler.assert_not_called()
        prompt.assert_not_called()
        driver.quit.assert_called_once()

    def test_supported_mode_only_succeeds_after_confirmation(self):
        for confirmed in [False, True]:
            with self.subTest(confirmed=confirmed):
                result, _, handlers, prompt = self.run_application(
                    "https://jobs.lever.co/acme/1/apply", "auto", confirmed=confirmed)
                self.assertEqual(result, confirmed)
                self.assertTrue(handlers["apply_lever"].call_args[1]["auto_submit"])
                self.assertEqual(prompt.call_count, 0 if confirmed else 1)

    def test_host_routing_does_not_match_query_strings(self):
        _, _, handlers, _ = self.run_application("https://example.com/apply?next=lever.co", "assist")
        handlers["apply_generic"].assert_called_once()
        handlers["apply_lever"].assert_not_called()


if __name__ == "__main__":
    unittest.main()
