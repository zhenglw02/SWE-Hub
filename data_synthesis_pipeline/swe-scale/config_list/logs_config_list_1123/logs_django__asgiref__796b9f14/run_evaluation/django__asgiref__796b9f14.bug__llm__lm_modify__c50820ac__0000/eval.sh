#!/bin/sh
set -u
cd /testbed
if [ -f "/opt/miniconda3/bin/activate" ]; then . /opt/miniconda3/bin/activate || true; fi
if command -v conda >/dev/null 2>&1; then conda activate testbed || true; fi
echo '>>>>> Start Test Output'
if command -v bash >/dev/null 2>&1; then RUN_SHELL="bash -lc"; else RUN_SHELL="sh -lc"; fi
RC=0
if command -v timeout >/dev/null 2>&1; then
  set +e
  timeout 1200s $RUN_SHELL 'pytest --junitxml=/testbed/test_report.xml -n 10 --disable-warnings --color=no --tb=no --verbose -v --dist=loadscope --junitxml=/mnt/cfs_bj_mt/workspace/zhengliwei/code/baidu/qianfan/code-data-agent-sdk/data_synthesis_pipeline/swe-smith/qianfan_coder_smith/config_list/logs_config_list_1123/logs_django__asgiref__796b9f14/run_evaluation/django__asgiref__796b9f14.bug__llm__lm_modify__c50820ac__0000/test_report.xml> /mnt/cfs_bj_mt/workspace/zhengliwei/code/baidu/qianfan/code-data-agent-sdk/data_synthesis_pipeline/swe-smith/qianfan_coder_smith/config_list/logs_config_list_1123/logs_django__asgiref__796b9f14/run_evaluation/django__asgiref__796b9f14.bug__llm__lm_modify__c50820ac__0000/test_output.txt'
  RC=$?
  set -e || true
else
  echo "[warn] timeout not found; running without time limit" >&2
  set +e
  $RUN_SHELL 'pytest --junitxml=/testbed/test_report.xml -n 10 --disable-warnings --color=no --tb=no --verbose -v --dist=loadscope --junitxml=/mnt/cfs_bj_mt/workspace/zhengliwei/code/baidu/qianfan/code-data-agent-sdk/data_synthesis_pipeline/swe-smith/qianfan_coder_smith/config_list/logs_config_list_1123/logs_django__asgiref__796b9f14/run_evaluation/django__asgiref__796b9f14.bug__llm__lm_modify__c50820ac__0000/test_report.xml> /mnt/cfs_bj_mt/workspace/zhengliwei/code/baidu/qianfan/code-data-agent-sdk/data_synthesis_pipeline/swe-smith/qianfan_coder_smith/config_list/logs_config_list_1123/logs_django__asgiref__796b9f14/run_evaluation/django__asgiref__796b9f14.bug__llm__lm_modify__c50820ac__0000/test_output.txt'
  RC=$?
  set -e || true
fi
echo '>>>>> End Test Output'
echo "RC=${RC}"
exit 0
