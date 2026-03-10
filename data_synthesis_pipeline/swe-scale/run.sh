# stage 1: set config
# step1.1 download repo
./config_list/repo_list/django__asgiref__796b9f14
# step1.2: get docker image
iregistry.baidu-int.com/acg-airec/r2e_gym/my_swe_smith/swesmith.x86_64.django__asgiref.796b9f14:latest
# step1.3: set config
./config_list/django__asgiref__796b9f14.py

# stage 2 get ground truch
# step2.1: run evaluation with empty patch
python ./stage_2_validation/step_1_evalution_ground_truth.py --config_name django__asgiref__796b9f14
# step2.2: parse test log
python ./stage_3_report_parser/step_0_parse_gound_truth_cross_repo_python_xml.py --config_name django__asgiref__796b9f14

# stage 3: generate singe bug patch
# step3.1: gen bug patch with procedural
python ./stage_1_swe_smith/step_1_procedural_gen_bug.py --config_name django__asgiref__796b9f14
# step3.2: gen bug patch with llm modify
python ./stage_1_swe_smith/step_2_llm_gen_bug.py --config_name django__asgiref__796b9f14 --bug_type modify
# step3.3: gen bug patch with llm rewrite
python ./stage_1_swe_smith/step_2_llm_gen_bug.py --config_name django__asgiref__796b9f14 --bug_type rewrite

# stage 4: evaluate single bug patch
# step4.1: run evaluation with single bug patch
python ./stage_2_validation/step_1_evalution_cross_repo_script.py --config_name django__asgiref__796b9f14 --bug_mode single 
# step4.2: parse test log
python ./stage_3_report_parser/step_1_parse_report_cross_repo_python_xml.py --config_name django__asgiref__796b9f14 --bug_mode single 
# step4.3: export patch which has P2F
python ./stage_3_report_parser/step_2_export_instance.py --config_name django__asgiref__796b9f14 --bug_mode single 

# stage 5: combine bug patch
python ./stage_1_swe_smith/step_3_combine_bug.py --config_name django__asgiref__796b9f14

# stage 6: evaluate combine bug patch
# step6.1: run evaluation with combine bug patch
python ./stage_2_validation/step_1_evalution_cross_repo_script.py --config_name django__asgiref__796b9f14 --bug_mode combine 
# step6.2: parse test log
python ./stage_3_report_parser/step_1_parse_report_cross_repo_python_xml.py --config_name django__asgiref__796b9f14 --bug_mode combine 
# step6.3: export patch which has P2F
python ./stage_3_report_parser/step_2_export_instance.py --config_name django__asgiref__796b9f14 --bug_mode combine 

# stage 7: gen issue
python ./stage_4_gen_issue/step_1_generate_issue.py --config_name django__asgiref__796b9f14

# staeg 8: export final data
python ./stage_4_gen_issue/step_2_export_final_data.py --config_name django__asgiref__796b9f14