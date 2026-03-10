import os
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import re
import time
import yaml
import json
import random
import shutil
import jinja2
import litellm
import logging
import argparse
from typing import *
from rich import print
from pathlib import Path
from tqdm.auto import tqdm
from dotenv import load_dotenv
from litellm import completion
from multiprocessing import Pool
from litellm.cost_calculator import completion_cost
from concurrent.futures import ThreadPoolExecutor, as_completed
from utils_list.data_structure.constants import LM_MODIFY, LM_REWRITE
from utils_list.data_structure.base_data_structure import BugRewrite, CodeEntity
from utils_list.language_config.load_language_configs import get_all_language_config
from utils_list.extract_utils.entity_procssor import extract_entities_from_directory
from utils_list.container_utils.gen_patch_by_local_container import gen_patch_parallel
from stage_0_register_config.register_config import get_all_config, get_config


load_dotenv(dotenv_path=os.getenv("SWEFT_DOTENV_PATH"))
logging.getLogger("LiteLLM").setLevel(logging.WARNING)
litellm.suppress_debug_info = True


def gen_bugs_by_modify(
    instance_id: int,
    hash_code: str,
    candidate: CodeEntity, 
    prompt_dict: dict, 
    n_bugs: int, 
    model: str,
    prompt_keys: list[str],
    api_base,
    api_key,   
    input_cost_per_token,
    output_cost_per_token,
) -> list[BugRewrite]:
    """
    Given the source code of a function, return `n` bugs with an LM
    """
    # candidate: CodeEntity, configs: dict, n_bugs: int, model: str = params
    def extract_code_block(text: str) -> str:
        pattern = r"```(?:\w+)?\n(.*?)```"
        match = re.search(pattern, text, re.DOTALL)
        return match.group(1).strip() if match else ""
        
    def format_prompt(prompt: str | None, config: dict, candidate: CodeEntity) -> str:
        if not prompt:
            return ""
        env = jinja2.Environment()

        def jinja_shuffle(seq):
            result = list(seq)
            random.shuffle(result)
            return result

        env.filters["shuffle"] = jinja_shuffle
        template = env.from_string(prompt)
        return template.render(**{'src_code': candidate.src_code}, **config.get("parameters", {}))

    def get_role(key: str) -> str:
        if key == "system":
            return "system"
        return "user"
    messages = [
        {"content": format_prompt(prompt_dict[k], prompt_dict, candidate), "role": get_role(k)}
        for k in prompt_keys
    ]
    # Remove empty messages
    messages = [x for x in messages if x["content"]]
    bugs = []
    for _ in range(0, n_bugs):
        try:
            response: Any = completion(
                model=model, 
                messages=messages, 
                n=1, 
                temperature=1, 
                api_base=api_base,
                api_key=api_key,
                input_cost_per_token=input_cost_per_token,
                output_cost_per_token=output_cost_per_token, 
            )
            for choice in response.choices:
                message = choice.message
                explanation = (
                    message.content.split("Explanation:")[-1].strip()
                    if "Explanation" in message.content
                    else message.content.split("```")[-1].strip()
                )
                try:
                    cost = completion_cost(completion_response=response) / n_bugs
                except:
                    cost = 0
                bugs.append(
                    BugRewrite(
                        hash_code=hash_code,
                        instance_id=instance_id,
                        rewrite=extract_code_block(message.content),
                        explanation=explanation,
                        cost=cost,
                        output=message.content,
                        strategy=LM_MODIFY,
                    )
                )
        except Exception as e:
            continue
    return candidate, bugs, sum([x.cost for x in bugs])


def gen_bugs_by_rewrite(
    instance_id: str,
    hash_code: str,
    candidate: CodeEntity,
    prompt_dict: dict,
    n_bugs: int,
    model: str,
    prompt_keys: list[str],
    api_base,
    api_key,   
    input_cost_per_token,
    output_cost_per_token,
):
    def extract_code_block(text: str) -> str:
        pattern = r"```(?:\w+)?\n(.*?)```"
        match = re.search(pattern, text, re.DOTALL)
        return match.group(1).strip() if match else ""

    def get_exclude_code_block_from_full_file(candidate: CodeEntity, strip_body: str) -> str:
        """Replaces lines in a file between start_line and end_line with replacement_code."""
        with open(candidate.file_path, "r") as file:
            lines = file.readlines()
        if (
            candidate.line_start < 1
            or candidate.line_end > len(lines)
            or candidate.line_start > candidate.line_end
        ):
            raise ValueError("Invalid line range specified.")
        replacement_lines = [
            f"{' ' * candidate.indent_level * candidate.indent_size}{x}"
            if len(x.strip()) > 0
            else x
            for x in strip_body.splitlines(keepends=True)
        ]
        lines = (
            lines[: candidate.line_start - 1]
            + replacement_lines
            + lines[candidate.line_end :]
        )
        return "".join(lines)

    # Get prompt content
    prompt_content = {
        "func_signature": candidate.signature,
        "func_to_write": candidate.strip_body,
        "file_src_code": get_exclude_code_block_from_full_file(candidate, candidate.strip_body),
    }

    # Generate a rewrite
    messages = [
        {
            "content": prompt_dict[k].format(**prompt_content),
            "role": "user" if k != "system" else "system",
        }
        for k in prompt_keys
        if k in prompt_dict
    ]
    # Remove empty messages
    messages = [x for x in messages if x["content"]]
    bugs = []
    for _ in range(0, n_bugs):
        try:
            response: Any = completion(
                model=model, 
                messages=messages, 
                n=n_bugs, 
                temperature=1, 
                api_base=api_base,
                api_key=api_key,
                input_cost_per_token=input_cost_per_token,
                output_cost_per_token=output_cost_per_token, 
            )
            for choice in response.choices:
                message = choice.message
                # Revert the blank-out change to the current file and apply the rewrite
                code_block = extract_code_block(message.content)
                explanation = message.content.split("```", 1)[0].strip()
                try:
                    cost = completion_cost(completion_response=response)
                except:
                    cost = 0
                bug = BugRewrite(
                    hash_code=hash_code,
                    instance_id=instance_id,
                    rewrite=code_block,
                    explanation=explanation,
                    strategy=LM_REWRITE,
                    cost=cost,
                    output=message.content,
                )
                bugs.append(bug)
        except Exception as e:
            continue
    return candidate, bugs, sum([x.cost for x in bugs])


def llm_gen_bugs(params):
    try:
        config, bug_type = params
        if os.path.exists(os.path.join(str(config.LOG_DIR), '{}__SUCCESS__'.format(bug_type))):
            return
        seed = config.SEED
        random.seed(seed)
        # Set up logging
        log_dir = Path(config.LOG_DIR_BUG_GEN)
        prefix_metadata, prefix_bug = config.PREFIX_METADATA, config.PREFIX_BUG
        log_dir.mkdir(parents=True, exist_ok=True)
        print(f"Logging bugs to {log_dir}")
        # get config attribute
        if bug_type == 'modify':
            prompt_yaml = config.MODIFY_YAML
            per_bugs_per_entity = config.MODIFY_PER_BUGS_PER_ENTITY
            max_bugs = config.MODIFY_MAX_BUGS
            gen_bugs_function = gen_bugs_by_modify
        elif bug_type == 'rewrite':
            prompt_yaml = config.REWRITE_YAML
            per_bugs_per_entity = config.REWRITE_PER_BUGS_PER_ENTITY
            max_bugs = config.REWRITE_MAX_BUGS
            gen_bugs_function = gen_bugs_by_rewrite
        else:
            raise ValueError
        prompt_keys = config.PROMPT_KEYS
        assert os.path.exists(prompt_yaml), f"{prompt_yaml} not found"
        assert per_bugs_per_entity > 0, "n_bugs must be greater than 0"
        assert max_bugs > 0, "MODIFY_MAX_BUGS and REWRITE_MAX_BUGS must be greater than 0"
        prompt_dict = yaml.safe_load(open(prompt_yaml))
        repo_name, base_path = config.REPO_NAME, config.BASE_PATH
        repo_path = os.path.join(base_path, repo_name)

        # extract candidate entity
        try:
            language_config_dict = get_all_language_config()
            all_candidates = extract_entities_from_directory(
                directory_path=repo_path,
                language_config_dict=language_config_dict
            )
            print(f"{len(all_candidates)} candidates found in {repo_name}")
        except Exception as e:
            return
        
        if bug_type == 'modify':
            all_candidates = [x for x in all_candidates if x.complexity >= prompt_dict["threshold"]]
        elif bug_type == 'rewrite':
            all_candidates = [x for x in all_candidates if x.complexity >= prompt_dict["threshold"] and x.code_type == 'function']
        else:
            raise ValueError
        print(f"{len(all_candidates)} candidates passed criteria")
        if not all_candidates:
            print(f"No candidates found in {repo_name}.")
            open(os.path.join(str(config.LOG_DIR), '{}__SUCCESS__'.format(bug_type)), 'w')
            return

        # dedup and ship success
        exists_path_set = set()
        redo_existing = config.REDO_EXISTING
        filter_candidates = []
        for cand in all_candidates:
            output_dir = (
                log_dir
                / cand.file_path.replace(repo_path, '').strip('/')
                / cand.name
            )
            for index in range(0, per_bugs_per_entity):
                type_name = prompt_dict['name']
                uuid_str = f"llm__{type_name}__{cand.hash_code.strip()}__{'%.4d' % index}"
                metadata_path = f"{prefix_metadata}__{uuid_str}.json"
                success_path = os.path.join(output_dir / metadata_path) + '__SUCCESS__'
                if not redo_existing and os.path.exists(success_path):
                    continue
                elif metadata_path in exists_path_set:
                    # 每个节点只能修改一次
                    continue
                else:
                    filter_candidates.append([cand, cand.hash_code.strip(), uuid_str])
                    exists_path_set.add(metadata_path)

        if max_bugs > 0:
            random.shuffle(filter_candidates)
            filter_candidates = filter_candidates[:max_bugs]
        print(f"Skip {len(all_candidates) * per_bugs_per_entity - len(filter_candidates)} candidates, Left {len(filter_candidates)} candidates.")
        if len(filter_candidates) == 0:
            return
        # gen bugs parallel
        model = 'openai/deepseek-v3.1-250821'
        worker_concurrency, container_concurrency = 32, 4
        successes, errors, total_llm_cost = 0, 0, 0.0
        success_condicate, success_bug = 0, 0
        start_time = time.time()
        item_list = []
        desc = f"LLM bugs ({len(filter_candidates)} cand)"
        with ThreadPoolExecutor(max_workers=worker_concurrency) as ex, \
            tqdm(total=len(filter_candidates), desc=desc, unit="cand", leave=False) as pbar:
            future_to_cand = {
                ex.submit(
                    gen_bugs_function,
                    instance_id=uuid_str,
                    hash_code=hash_code,
                    candidate=candidate,
                    prompt_dict=prompt_dict,
                    n_bugs=1,
                    model=model,
                    prompt_keys=prompt_keys,
                    api_base=config.API_BASE,
                    api_key=config.API_KEY,
                    input_cost_per_token=config.INPUT_COST_PER_TOKEN / 1000,
                    output_cost_per_token=config.OUTPUT_COST_PER_TOKEN / 1000,
                ) for candidate, hash_code, uuid_str in filter_candidates
            }
            try:
                for fut in as_completed(future_to_cand):
                    try:
                        cand, bugs, cost = fut.result()
                        if len(bugs) == 0:
                            continue
                        bug = bugs[0]
                        output_dir = (
                            log_dir
                            / cand.file_path.replace(repo_path, '').strip('/')
                            / cand.name
                        )
                        item_list.append({
                            'candidate': cand,
                            'bug': bug, 
                            'output_dir': output_dir,
                            'type_name': prompt_dict['name'],
                        })
                        success_bug += 1
                        successes += 1
                        success_condicate += 1
                        total_llm_cost += float(cost or 0.0)
                    except Exception as e:
                        errors += 1
                        # 用 tqdm.write 防止打乱进度条
                        tqdm.write(f"[red]Error processing candidate[/red] {getattr(candidate, 'file_path', '<unknown>')}: {e}")
                    finally:
                        pbar.update(1)
                        pbar.set_postfix(ok=successes, err=errors, cost=f"{total_llm_cost:.4f}")
            except KeyboardInterrupt:
                # 支持 Ctrl-C：尝试取消剩余任务
                for f in future_to_cand:
                    f.cancel()
                raise
        print(f"Generated {success_condicate} candicate, {success_bug} bugs for {repo_name}. Cost {round(total_llm_cost, 1)} RMB. Cost time {round(time.time()-start_time, 1)} s")
        if len(item_list) == 0:
            return
        # apply bugs parallel in local container pool
        patch_list = gen_patch_parallel(
            item_list=item_list,
            repo_path=repo_path,
            image_name=config.IMAGE_NAME,
            docker_workdir=config.DOCKER_WORKDIR,
            worker_concurrency=worker_concurrency,
            container_concurrency=container_concurrency,
        )
        assert len(patch_list) == len(item_list)
        for patch, item in zip(patch_list, item_list):
            if patch is None:
                continue
            candidate = item['candidate']
            bug = item['bug']
            instance_id = bug.instance_id
            output_dir = item['output_dir']
            type_name = item['type_name']
            output_dir.mkdir(parents=True, exist_ok=True)
            metadata_path = f"{prefix_metadata}__{instance_id}.json"
            bug_path = f"{prefix_bug}__{instance_id}.diff"
            success_path = os.path.join(output_dir / metadata_path) + '__SUCCESS__'
            with open(output_dir / metadata_path, "w") as f:
                json.dump(bug.to_dict(), f, indent=2)
            with open(output_dir / bug_path, "w") as f:
                f.write(patch)
            open(success_path, 'w').close()
        open(os.path.join(str(config.LOG_DIR), '{}__SUCCESS__'.format(bug_type)), 'w')
    except Exception as e:
        return


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description="Generate bugs with LLM for a given repository name."
    )
    parser.add_argument(
        "--config_name", type=str, help="Configuration name", 
        default='django__asgiref__796b9f14'
    )
    parser.add_argument(
        "--bug_type", type=str, help="Type of the generated bugs", choices=["rewrite", "modify"], default='modify'
    )
    args = parser.parse_args()
    config = get_config(args.config_name)
    llm_gen_bugs([config, args.bug_type])
