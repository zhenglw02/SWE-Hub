from enum import Enum

class Backend:
    LOCAL = "local"
    KODO = "kodo"

class TestStatus(Enum):
    FAILED = "FAILED"
    PASSED = "PASSED"
    SKIPPED = "SKIPPED"
    ERROR = "ERROR"
    XFAIL = "XFAIL"
    XPASS = "XPASS"

UTF8 = "utf-8"
DOCKER_PATCH = "/tmp/patch.diff"
LOG_TEST_OUTPUT = "test_output.txt"
LOG_XML_REPORT_OUTPUT = "test_report.xml"
LOG_JSON_REPORT_OUTPUT = "test_report.json"
LOG_REPORT = 'report.json'
LOG_INSTANCE = "run_instance.log"
INSTANCE_PATH = "instance.json"
LOG_EVAL_SH = "eval.sh"

KEY_INSTANCE_ID = "instance_id"
KEY_PATCH = "patch"
KEY_IMAGE_NAME = "image_name"
KEY_TIMED_OUT = "timed_out"

FAIL_TO_PASS = "FAIL_TO_PASS"
FAIL_TO_FAIL = "FAIL_TO_FAIL"
PASS_TO_PASS = "PASS_TO_PASS"
PASS_TO_FAIL = "PASS_TO_FAIL"

APPLY_PATCH_FAIL = ">>>>> Patch Apply Failed"
APPLY_PATCH_PASS = ">>>>> Applied Patch"
INSTALL_FAIL = ">>>>> Init Failed"
INSTALL_PASS = ">>>>> Init Succeeded"
INSTALL_TIMEOUT = ">>>>> Init Timed Out"
RESET_FAILED = ">>>>> Reset Failed"
TESTS_ERROR = ">>>>> Tests Errored"
TESTS_FAILED = ">>>>> Some Tests Failed"
TESTS_PASSED = ">>>>> All Tests Passed"
TESTS_TIMEOUT = ">>>>> Tests Timed Out"
TESTS_OUTPUT_START = ">>>>> Start Test Output"
TESTS_OUTPUT_END = ">>>>> End Test Output"
GROUND_TRUTH = "ground_truth"

LM_REWRITE = "lm_rewrite"
LM_MODIFY = "lm_modify"
COMBINE_FILE = "combine_file"
EXCLUDED_BUG_TYPES = ["func_basic", "combine_file", "combine_module", "pr_mirror"]
COMBINE_MODULE = "combine_module"
EXCLUDED_BUG_TYPES = ["func_basic", "combine_file", "combine_module", "pr_mirror"]
