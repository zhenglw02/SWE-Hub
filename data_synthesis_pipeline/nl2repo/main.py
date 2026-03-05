#!/usr/bin/env python3
"""
nl2repo 流水线入口

使用方法：
    # 作为模块运行
    python -m nl2repo.main --input /path/to/input.jsonl --output /path/to/output
    
    # 或直接运行
    python nl2repo/main.py --input /path/to/input.jsonl --output /path/to/output
    
    # 只运行特定步骤
    python -m nl2repo.main --input input.jsonl --output output --steps extract,meta,relationship
    
    # 使用并行模式运行覆盖率收集
    python -m nl2repo.main --input input.jsonl --output output --parallel
"""

import argparse
import os
import sys
import time
from pathlib import Path
from typing import List, Optional

# 自动设置路径，确保能找到 nl2repo 包
_SCRIPT_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SCRIPT_DIR.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


def parse_args() -> argparse.Namespace:
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description="nl2repo - Code Repository to Documentation Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
  # 运行完整流水线
  python -m nl2repo.main --input meta.jsonl --output ./output
  
  # 只运行代码分析步骤（跳过覆盖率收集）
  python -m nl2repo.main --input meta.jsonl --output ./output --steps extract,meta,relationship,doc
  
  # 使用并行模式
  python -m nl2repo.main --input meta.jsonl --output ./output --parallel --workers 64
        """,
    )
    
    # 必需参数
    parser.add_argument(
        "--input", "-i",
        required=True,
        help="输入的 JSONL 文件路径（每行包含 repo, image_name, base_commit）",
    )
    parser.add_argument(
        "--output", "-o",
        required=True,
        help="输出目录路径",
    )
    
    # 可选参数
    parser.add_argument(
        "--steps",
        default="all",
        help="要执行的步骤，逗号分隔。可选：extract,coverage,meta,relationship,doc 或 all（默认）",
    )
    parser.add_argument(
        "--parallel",
        default=True,
        action="store_true",
        help="使用并行模式运行覆盖率收集（需要 K8s 环境）",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=3,
        help="并行工作线程数（默认 128）",
    )
    parser.add_argument(
        "--num-runs",
        type=int,
        default=10,
        help="每个仓库的覆盖率收集次数（默认 10）",
    )
    parser.add_argument(
        "--skip-completed",
        action="store_true",
        default=True,
        help="跳过已完成的任务（默认启用）",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="显示详细输出",
    )

    # LLM 参数（用于 doc_part1/doc_part2）
    parser.add_argument(
        "--llm-base-url",
        default=os.environ.get("LLM_BASE_URL", ""),
        help="LLM API base URL (or set LLM_BASE_URL env var)",
    )
    parser.add_argument(
        "--llm-model",
        default="deepseek-v3.2",
        help="LLM model",
    )
    parser.add_argument(
        "--llm-auth-token",
        default=os.environ.get("QIANFAN_BEARER_TOKEN", ""),
        help="LLM auth token (or env QIANFAN_BEARER_TOKEN)",
    )
    
    return parser.parse_args()


def get_steps_to_run(steps_arg: str) -> List[str]:
    """解析要运行的步骤"""
    all_steps = ["extract", "coverage", "meta", "relationship", "doc_part1", "doc_part2", "doc"]
    
    if steps_arg.lower() == "all":
        return all_steps
    
    requested = [s.strip().lower() for s in steps_arg.split(",")]
    valid_steps = []
    
    for step in requested:
        if step in all_steps:
            valid_steps.append(step)
        else:
            print(f"警告：未知步骤 '{step}'，已忽略")
    
    return valid_steps


def run_pipeline(
    input_path: str,
    output_root: str,
    steps: List[str],
    parallel: bool = False,
    workers: int = 128,
    num_runs: int = 10,
    verbose: bool = False,
    llm_base_url: str = "",
    llm_model: str = "deepseek-v3.2",
    llm_auth_token: str = "",
) -> bool:
    """运行流水线
    
    Args:
        input_path: 输入 JSONL 文件路径
        output_root: 输出目录
        steps: 要执行的步骤列表
        parallel: 是否使用并行模式
        workers: 并行工作线程数
        num_runs: 覆盖率收集次数
        verbose: 是否显示详细输出
        
    Returns:
        是否成功完成
    """
    from nl2repo.pipeline.context import PipelineContext
    
    print("=" * 60)
    print("nl2repo 流水线")
    print("=" * 60)
    print(f"输入文件: {input_path}")
    print(f"输出目录: {output_root}")
    print(f"执行步骤: {', '.join(steps)}")
    print(f"并行模式: {'是' if parallel else '否'}")
    print("=" * 60)
    
    start_time = time.time()
    
    # 创建上下文
    context = PipelineContext(
        input_path=input_path,
        output_root=output_root,
    )
    context.ensure_directories()
    
    # 加载输入元数据
    print("\n📂 加载输入元数据...")
    meta_list = context.load_input_meta()
    print(f"   加载了 {len(meta_list)} 个仓库")
    
    # 执行各步骤
    try:
        # Step 1: 提取代码
        if "extract" in steps:
            print("\n🚀 Step 1: 从 Docker 镜像提取代码...")
            from nl2repo.pipeline.steps import RepoExtractStep
            RepoExtractStep().run(context)
        
        # Step 2: 收集覆盖率
        if "coverage" in steps:
            print("\n🧪 Step 2: 收集代码覆盖率...")
            from nl2repo.pipeline.steps import CoverageStep
            step = CoverageStep(num_runs=num_runs, parallel_workers=workers)
            if parallel:
                step.run_parallel(context)
            else:
                step.run(context)
        
        # Step 3: 聚合元数据
        if "meta" in steps:
            print("\n📊 Step 3: 聚合测试结果元数据...")
            from nl2repo.pipeline.steps import MetaCollectStep
            MetaCollectStep(num_runs=num_runs).run(context)
        
        # Step 4: 分析关系
        if "relationship" in steps:
            print("\n🔗 Step 4: 分析代码依赖关系...")
            from nl2repo.pipeline.steps import RelationshipStep
            RelationshipStep(
                worker_concurrency=workers,
                container_concurrency=min(workers, 8),
            ).run(context)
        
        # Step 5a: 生成 Part 1 文档（项目级）
        if "doc_part1" in steps:
            print("\n📝 Step 5a: 生成 Part 1 文档（项目级）...")
            from nl2repo.pipeline.steps import DocPart1Step
            DocPart1Step(
                num_workers=workers,
                llm_model=llm_model,
                llm_base_url=llm_base_url,
                llm_auth_token=llm_auth_token,
            ).run(context)
        
        # Step 5b: 生成 Part 2 文档（函数级）
        if "doc_part2" in steps:
            print("\n📝 Step 5b: 生成 Part 2 文档（函数级）...")
            from nl2repo.pipeline.steps import DocPart2Step
            DocPart2Step(
                num_workers=workers,
                llm_model=llm_model,
                llm_base_url=llm_base_url,
                llm_auth_token=llm_auth_token,
            ).run(context)
        
        # Step 6: 组装最终文档
        if "doc" in steps:
            print("\n📝 Step 6: 组装最终文档...")
            from nl2repo.pipeline.steps import DocGenerateStep
            DocGenerateStep().run(context)
        
        elapsed = time.time() - start_time
        print("\n" + "=" * 60)
        print(f"✅ 流水线完成！耗时: {elapsed:.1f} 秒")
        print("=" * 60)
        
        # 打印错误摘要
        if context.errors:
            print(f"\n⚠️ 执行过程中有 {len(context.errors)} 个错误：")
            
            # 保存完整错误到文件
            error_log_path = os.path.join(context.output_root, "errors.log")
            with open(error_log_path, "w", encoding="utf-8") as f:
                for i, err in enumerate(context.errors, 1):
                    f.write(f"{'='*60}\n")
                    f.write(f"Error #{i}\n")
                    f.write(f"{'='*60}\n")
                    f.write(f"{err}\n\n")
            print(f"   📄 详细错误日志已保存到: {error_log_path}")
            
            # 在控制台只显示简短摘要（取错误信息的第一行）
            print(f"\n   错误摘要：")
            for err in context.errors[:10]:
                # 只显示错误的第一行（不含堆栈）
                first_line = err.split('\n')[0]
                print(f"   - {first_line}")
            if len(context.errors) > 10:
                print(f"   ... 还有 {len(context.errors) - 10} 个错误，请查看 errors.log")
        
        return True
        
    except Exception as e:
        print(f"\n❌ 流水线执行失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def _validate_runtime_config(steps: List[str], args: argparse.Namespace) -> None:
    """_validate_runtime_config."""
    if "doc_part1" in steps or "doc_part2" in steps:
        if not args.llm_base_url:
            print("错误：doc_part1/doc_part2 需要 --llm-base-url 或 LLM_BASE_URL 环境变量")
            sys.exit(1)
        if not args.llm_auth_token:
            print("错误：doc_part1/doc_part2 需要 --llm-auth-token 或 QIANFAN_BEARER_TOKEN")
            sys.exit(1)

    if "coverage" in steps or "relationship" in steps:
        from nl2repo.config import get_settings
        settings = get_settings()
        if "coverage" in steps and not settings.coverage_rcfile:
            print("错误：coverage 步骤需要 NL2REPO_COVERAGE_RCFILE")
            sys.exit(1)
        if "relationship" in steps and not settings.language_config_paths:
            print("错误：relationship 步骤需要 NL2REPO_LANGUAGE_CONFIG_PATHS")
            sys.exit(1)


def main():
    """主入口"""
    args = parse_args()
    
    # 验证输入文件
    if not Path(args.input).exists():
        print(f"错误：输入文件不存在: {args.input}")
        sys.exit(1)
    
    # 解析步骤
    steps = get_steps_to_run(args.steps)
    if not steps:
        print("错误：没有有效的步骤可执行")
        sys.exit(1)

    _validate_runtime_config(steps, args)
    
    # 运行流水线
    success = run_pipeline(
        input_path=args.input,
        output_root=args.output,
        steps=steps,
        parallel=args.parallel,
        workers=args.workers,
        num_runs=args.num_runs,
        verbose=args.verbose,
        llm_base_url=args.llm_base_url,
        llm_model=args.llm_model,
        llm_auth_token=args.llm_auth_token,
    )
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
