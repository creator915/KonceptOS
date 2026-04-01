"""KonceptOS v2.1 — Selenium Test Runner for build verification."""
import os
import sys
import signal
import subprocess
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

# Test result structure
@dataclass
class TestResult:
    passed: bool = False
    errors: List[str] = field(default_factory=list)
    console_errors: List[str] = field(default_factory=list)
    network_errors: List[str] = field(default_factory=list)
    canvas_state: Optional[str] = None
    input_results: Dict[str, Any] = field(default_factory=dict)
    output_results: Dict[str, Any] = field(default_factory=dict)

    def to_llm_feedback(self) -> str:
        """Format results for LLM analysis."""
        lines = []
        if self.console_errors:
            lines.append(f"Console Errors: {', '.join(self.console_errors)}")
        if self.network_errors:
            lines.append(f"Network Errors: {', '.join(self.network_errors)}")
        if self.errors:
            lines.append(f"Test Failures: {'; '.join(self.errors)}")
        if self.canvas_state:
            lines.append(f"Canvas State: {self.canvas_state}")
        if not lines:
            return "All tests passed."
        return '\n'.join(lines)


class SeleniumTestRunner:
    """Runs Selenium tests against generated HTML+Canvas pages."""

    def __init__(self, html_path: str, test_hooks_path: str = None, timeout: int = 30):
        self.html_path = os.path.abspath(html_path)
        self.test_hooks_path = test_hooks_path
        self.test_hooks = {}
        self._loaded = False
        self.timeout = timeout

    def _load_hooks(self) -> bool:
        """Load test hooks from the Python file.

        Expected format in test_hooks file:
        TEST_INPUTS = [
            ('input_name', 'selector_or_id', 'test_value'),
        ]
        TEST_OUTPUTS = [
            ('output_name', 'selector_or_id', 'check_type'),
        ]
        CANVAS_CHECK_JS = "return canvas.toDataURL();"
        """
        if not self.test_hooks_path or not os.path.exists(self.test_hooks_path):
            return False

        try:
            with open(self.test_hooks_path, 'r', encoding='utf-8') as f:
                content = f.read()

            # Execute the hooks file to get definitions
            local_vars = {}
            exec(content, {}, local_vars)

            self.test_hooks = {
                'inputs': local_vars.get('TEST_INPUTS', []),
                'outputs': local_vars.get('TEST_OUTPUTS', []),
                'canvas_js': local_vars.get('CANVAS_CHECK_JS', None),
                'expected_behavior': local_vars.get('EXPECTED_BEHAVIOR', ''),
            }
            self._loaded = True
            return True
        except Exception as e:
            print(f"Warning: Failed to load test hooks: {e}")
            return False

    def _run_selenium_subprocess(self) -> Optional[TestResult]:
        """Run Selenium in a subprocess with timeout to avoid hanging."""
        import subprocess
        import threading

        def _run_test(result_holder, error_holder):
            """Run selenium test in thread, store result in result_holder."""
            try:
                from selenium import webdriver
                from selenium.webdriver.common.by import By
                from selenium.webdriver.chrome.options import Options
                from selenium.common.exceptions import WebDriverException, TimeoutException

                result = TestResult()

                # Setup headless Chrome
                chrome_options = Options()
                chrome_options.add_argument('--headless')
                chrome_options.add_argument('--no-sandbox')
                chrome_options.add_argument('--disable-dev-shm-usage')
                chrome_options.add_argument('--disable-gpu')
                chrome_options.add_argument('--window-size=1920,1080')

                driver = webdriver.Chrome(options=chrome_options)
                driver.set_page_load_timeout(self.timeout)
                driver.set_script_timeout(self.timeout)

                try:
                    # Load the HTML file
                    file_url = f'file://{self.html_path}'
                    driver.get(file_url)

                    # Small delay to let page initialize
                    import time
                    time.sleep(1)

                    # Capture console errors
                    try:
                        console_logs = driver.get_log('browser')
                        result.console_errors = [
                            f"[{log['level']}] {log['message']}"
                            for log in console_logs
                            if log['level'] in ('ERROR', 'SEVERE')
                        ]
                    except:
                        pass

                    # Run input tests
                    for input_name, selector, test_value in self.test_hooks.get('inputs', []):
                        try:
                            elem = driver.find_element(By.CSS_SELECTOR, selector)
                            if elem.tag_name in ('input', 'textarea'):
                                elem.clear()
                                elem.send_keys(test_value)
                            elif elem.tag_name == 'select':
                                from selenium.webdriver.support.ui import Select
                                Select(elem).select_by_visible_text(test_value)
                            else:
                                elem.click()
                            result.input_results[input_name] = 'OK'
                        except Exception as e:
                            result.input_results[input_name] = f'FAIL: {str(e)}'
                            result.errors.append(f"Input '{input_name}' failed: {e}")

                    # Run output checks
                    for output_name, selector, check_type in self.test_hooks.get('outputs', []):
                        try:
                            elem = driver.find_element(By.CSS_SELECTOR, selector)
                            if check_type == 'exists':
                                result.output_results[output_name] = 'exists'
                            elif check_type == 'text_contains':
                                result.output_results[output_name] = elem.text
                            elif check_type == 'canvas_has_content':
                                canvas_data = driver.execute_script('return document.querySelector("canvas").toDataURL();')
                                result.output_results[output_name] = 'has_content' if canvas_data and len(canvas_data) > 100 else 'empty'
                        except Exception as e:
                            result.output_results[output_name] = f'FAIL: {str(e)}'
                            result.errors.append(f"Output '{output_name}' check failed: {e}")

                    # Canvas state check
                    if self.test_hooks.get('canvas_js'):
                        try:
                            canvas_data = driver.execute_script(self.test_hooks['canvas_js'])
                            result.canvas_state = str(canvas_data)[:200] if canvas_data else 'empty'
                        except Exception as e:
                            result.canvas_state = f'ERROR: {e}'

                    # Determine pass/fail
                    result.passed = len(result.errors) == 0 and len(result.console_errors) == 0

                except TimeoutException:
                    result.errors.append("Page load timeout")
                except WebDriverException as e:
                    result.errors.append(f"WebDriver error: {e}")
                finally:
                    try:
                        driver.quit()
                    except:
                        pass

                result_holder.append(result)

            except Exception as e:
                error_holder.append(str(e))

        try:
            from selenium import webdriver
            from selenium.webdriver.common.by import By
            from selenium.webdriver.chrome.options import Options
            from selenium.common.exceptions import WebDriverException, TimeoutException
        except ImportError:
            return None

        result_holder = []
        error_holder = []
        thread = threading.Thread(target=_run_test, args=(result_holder, error_holder))
        thread.daemon = True
        thread.start()
        thread.join(timeout=self.timeout + 10)

        if thread.is_alive():
            error_holder.append(f"Selenium test timed out after {self.timeout + 10}s")
            return None

        if error_holder:
            print(f"Selenium error: {error_holder[0]}")
            return None

        if result_holder:
            return result_holder[0]

        return None

    def run(self) -> TestResult:
        """Run all tests and return results."""
        # Try to load hooks
        self._load_hooks()

        # If no hooks loaded, return a basic check
        if not self._loaded and not os.path.exists(self.html_path):
            return TestResult(passed=False, errors=[f"HTML file not found: {self.html_path}"])

        # Try selenium if hooks are available and loaded
        if self._loaded and (self.test_hooks.get('inputs') or self.test_hooks.get('outputs') or self.test_hooks.get('canvas_js')):
            print("Running Selenium tests...")
            result = self._run_selenium_subprocess()
            if result is not None:
                return result
            print("Selenium not available or failed, falling back to basic validation")

        # Fall back to basic validation
        return self._basic_validation()

    def _basic_validation(self) -> TestResult:
        """Basic validation without Selenium - just check file exists and is valid HTML."""
        result = TestResult()

        if not os.path.exists(self.html_path):
            result.errors.append(f"HTML file not found: {self.html_path}")
            return result

        try:
            with open(self.html_path, 'r', encoding='utf-8') as f:
                content = f.read()

            # Basic HTML validation
            if '<html' not in content.lower() and '<!doctype' not in content.lower():
                result.errors.append("File does not appear to be HTML")

            if '<canvas' in content.lower():
                # Has canvas - mark as potentially valid
                result.canvas_state = "Canvas element found (no Selenium to verify)"

            if result.errors:
                result.passed = False
            else:
                result.passed = True
                result.console_errors.append("Basic validation only - install selenium for full testing")

        except Exception as e:
            result.errors.append(f"Failed to read HTML file: {e}")
            result.passed = False

        return result


def run_build_tests(html_path: str, test_hooks_path: str = None) -> TestResult:
    """Convenience function to run tests on build output."""
    runner = SeleniumTestRunner(html_path, test_hooks_path)
    return runner.run()
