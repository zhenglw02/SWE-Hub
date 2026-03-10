import os
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import json
import yaml
import time
import jinja2
import random
import litellm
import logging
import argparse
from tqdm import tqdm
from rich import print
from pathlib import Path
from dotenv import load_dotenv
from datasets import load_dataset
from multiprocessing import Pool, cpu_count
from litellm import completion, completion_cost
from concurrent.futures import ThreadPoolExecutor, as_completed
from stage_0_register_config.register_config import get_all_config, get_config
from utils_list.test_func_tracker.gen_issue_utils import get_test_function_script, get_test_function_python
from utils_list.data_structure.constants import FAIL_TO_PASS, TESTS_OUTPUT_START, TESTS_OUTPUT_END
from utils_list.common_utils.common_tools import search_files, load_unfinished_instances
logging.getLogger("LiteLLM").setLevel(logging.WARNING)
litellm.suppress_debug_info = True



def format_prompt_from_template(template_obj, base_ctx: dict) -> str:
    """
    使用已编译的 Jinja2 Template 渲染字符串；如果模板为空则返回空串。
    """
    if not template_obj:
        return ""
    return template_obj.render(**base_ctx)


def maybe_shorten(text_str: str, max_tokens: int, model: str) -> str:
    """Shorten text if it exceeds the max_tokens limit.
    If shortening, return a string with the first and last max_tokens//2 tokens.
    """
    # get_token_count 期望消息格式，这里给最小消息结构
    if len(text_str.split(' ')) < max_tokens:
        return text_str
    text_list = text_str.split('\n')
    new_text_str = '\n'.join(text_list[: 50] + ["\n\n(...)\n\n"] + text_list[-100 :])
    if len(new_text_str.split(' ')) < max_tokens:
        return new_text_str
    return '\n'.join(text_list[: 10] + ["\n\n(...)\n\n"] + text_list[-20 :])


def get_demo_issues(model, swebv) -> list[str]:
    """
    Get a list of demonstration issues from the config file / dataset.
    仅做一次：截断后打乱顺序。
    """
    problem_statements = [
        maybe_shorten(instance["problem_statement"], 5000, model)
        for instance in swebv
    ]
    random.shuffle(problem_statements)
    return problem_statements


def get_test_function_list(instance: dict, base_path: Path, language: str) -> list[str]:
    """
    Returns:
        list of test functions
    """
    test_funcs = []
    test_idxs = list(range(len(instance[FAIL_TO_PASS])))
    random.shuffle(test_idxs)
    for test_idx in test_idxs:
        if language.lower() == 'python':
            test_func = get_test_function_python(instance, test_idx, base_path)
            test_funcs.append(test_func["test_src"])
        elif language.lower() in ['javascript', 'typescript']:
            test_func = get_test_function_script(instance, test_idx, base_path)
            test_funcs.append(test_func["test_src"])
    return test_funcs


def get_test_output(instance: dict, max_var_tokens: int, model: str) -> str:
    # Get execution output from running pytest for this instance (from validation step)
    test_output = instance['meta']['test_output']
    segment = test_output

    # get_token_count 期望消息格式，这里给最小消息结构
    if len(segment.split(' ')) < max_var_tokens:
        return segment
    text_list = segment.split('\n')
    new_text_str = '\n'.join(text_list[: 50] + ["\n\n(...)\n\n"] + text_list[-100 :])
    if len(new_text_str.split(' ')) < max_var_tokens:
        return new_text_str
    return '\n'.join(text_list[: 5] + ["\n\n(...)\n\n"] + text_list[-5 :])


def gen_issue_from_code_lm(
    messages: list[dict],
    model: str,
    api_base: str,
    api_key: str,
    input_cost_per_token: float,
    output_cost_per_token: float,
):
    
    for _ in range(0, 5):
        try:
            response = completion(
                model=model,
                messages=messages,
                n=1,
                temperature=0.7,
                api_base=api_base,
                api_key=api_key,
                timeout=360,
                input_cost_per_token=input_cost_per_token,
                output_cost_per_token=output_cost_per_token,
            )
            choice = response.choices[0]
            return choice.message.content, 0.1
        except Exception as e:
            print(model, e)
            if 'TPM' in str(e):
                time.sleep(random.randint(30, 60))
                continue
            else:
                break
    return None, 0.0
                


def jinja_shuffle(seq):
    result = list(seq)
    random.shuffle(result)
    return result


def gen_issues(params):
    try:
        config, dataset_path = params
        if os.path.exists(dataset_path + '__COMPLETE__'):
            return
        load_dotenv()

        datasets = load_unfinished_instances(
            dataset_path=dataset_path,
            log_dir_issue_gen=Path(config.LOG_DIR_ISSUE_GEN),
            show_progress=True,
            limit=8000
        )

        if len(datasets) == 0:
            open(dataset_path + '__COMPLETE__', 'w')
            return
        # ---- 基础配置 ----
        swe_bench_verified_path = config.SWE_BENCH_VERIFIED_PATH
        swe_bench_verified = load_dataset(swe_bench_verified_path, split="test")

        issue_gen_yaml = Path(config.ISSUE_GEN_YAML)
        issue_gen_dict = yaml.safe_load(issue_gen_yaml.read_text())

        settings = issue_gen_dict.get("settings", {})
        max_var_tokens = 10_000

        base_path = Path(config.BASE_PATH)
        log_dir_issue_gen = Path(config.LOG_DIR_ISSUE_GEN)
        model = config.ISSUE_GEN_MODEL_NAME
        # worker_concurrency = min(250, config.WORKER_CONCURRENCY)
        # worker_concurrency = min(50, config.WORKER_CONCURRENCY)
        worker_concurrency = 50
        # worker_concurrency = 1

        env = jinja2.Environment()

        env.filters["shuffle"] = jinja_shuffle

        tmpl_system = issue_gen_dict["system"]
        tmpl_demo = issue_gen_dict.get("demonstration") or ""
        tmpl_instance = issue_gen_dict["instance"]

        template_demo = env.from_string(tmpl_demo) if tmpl_demo else None
        template_instance = env.from_string(tmpl_instance)

        demo_message_content = None
        if template_demo:
            demo_problem_statements = get_demo_issues(model, swe_bench_verified)
            base_demo_ctx = {
                **issue_gen_dict,
                **issue_gen_dict.get("parameters", {}),
                "demo_problem_statements": demo_problem_statements,
            }
            demo_message_content = format_prompt_from_template(template_demo, base_demo_ctx)

        todo_instances: list[tuple[dict, Path]] = []
        for instance in tqdm(datasets, ncols=70, desc="Loading instances"):
            output_dir = log_dir_issue_gen / instance['instance_id']
            os.makedirs(output_dir, exist_ok=True)
            todo_instances.append((instance, output_dir))

        print(f"Total {len(datasets)}. Found {len(datasets) - len(todo_instances)} completed. Remaining: {len(todo_instances)}")

        # ---- 线程任务：构建 messages + 调用 LLM ----
        stats = {"💰": 0.0, "⏭️": 0, "❌": 0, "✅": 0}

        def build_messages(instance: dict) -> list[dict]:
            test_funcs = get_test_function_list(instance, base_path, config.LANGUAGE)
            inst_ctx = {
                **issue_gen_dict,
                **issue_gen_dict.get("parameters", {}),
                **instance,
                "test_output": get_test_output(instance, max_var_tokens, model),
                "test_funcs": test_funcs,
            }
            inst_msg = format_prompt_from_template(template_instance, inst_ctx)
            msgs = [{"content": tmpl_system, "role": "system"}]
            if demo_message_content:
                msgs.append({"content": demo_message_content, "role": "user"})
            msgs.append({"content": inst_msg, "role": "user"})
            return msgs

        def worker(instance: dict, output_dir: Path):
            try:
                messages = build_messages(instance)
                content, cost = gen_issue_from_code_lm(
                    messages=messages,
                    model=model,
                    api_base=config.API_BASE,
                    api_key=config.API_KEY,
                    input_cost_per_token=config.INPUT_COST_PER_TOKEN / 1000,
                    output_cost_per_token=config.OUTPUT_COST_PER_TOKEN / 1000,
                )
                # 仅在成功时写 metadata，以降低 I/O
                if content is not None:
                    metadata = {
                        'instance_id': instance['instance_id'],
                        'messages': messages,
                        "responses": content,
                        "cost": cost,
                    }
                    with open(output_dir / "metadata.json", "w", encoding="utf-8") as wf:
                        json.dump(metadata, wf, indent=4, ensure_ascii=False)
                    (output_dir / "metadata.json__SUCCESS__").touch()
                return content is not None, cost
            except Exception as e:
                print(f"\n[ERROR] Task for {instance['instance_id']} was terminated due to timeout: {e}")
                return False, 0
        desc = "Generating issues {}".format(config.REPO_NAME)
        with ThreadPoolExecutor(max_workers=worker_concurrency) as ex, \
            tqdm(total=len(todo_instances), desc=desc, unit="issue", leave=False, ncols=150) as pbar:

            futures = {ex.submit(worker, inst, outdir): (inst, outdir) for inst, outdir in todo_instances}

            for i, fut in enumerate(as_completed(futures), start=1):
                try:
                    ok, cost = fut.result()
                    if ok:
                        stats["✅"] += 1
                    else:
                        stats["❌"] += 1
                    stats["💰"] += cost
                except Exception as e:
                    stats["❌"] += 1
                    tqdm.write(f"[red]Error generating issues[/red]: {e}")
                finally:
                    pbar.update(1)
                    if i % 20 == 0 or i == len(futures):
                        pbar.set_postfix(stats, refresh=False)

        print(f"Generated {len(datasets)} ISSUES. SUCCESS {stats['✅']}, FAIL {stats['❌']}, Cost ${stats['💰']:.2f}")
    except Exception as e:
        print(str(e))
        return


def gen_issues_parallel(config):
    params_list = []
    dataset_dir = os.path.join(str(config.LOG_DIR), 'export_insts')
    file_path_list = search_files(dataset_dir)
    for file_path in file_path_list:
        if not file_path.endswith('.jsonl'):
            continue
        if file_path + '__SUCCESS__' not in file_path_list:
            continue
        params_list.append([config, file_path])
    random.shuffle(params_list)
    print('params size', len(params_list))
    with Pool(8) as p:
        p.map(gen_issues, params_list)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Gen issues parallel"
    )
    parser.add_argument(
        "--config_name", type=str, help="Configuration name", 
        default='django__asgiref__796b9f14'
    )
    args = parser.parse_args()
    config = get_config(args.config_name)
    gen_issues_parallel(config)

