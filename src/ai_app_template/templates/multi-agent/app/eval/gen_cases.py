"""从身份卡自动生成评测用例：生成一次，固化永久。

用法：
    python -m app.eval.gen_cases                  # 按 app/eval/identity.json 生成全部层级
    python -m app.eval.gen_cases --tier boundary  # 只生成某一层
    python -m app.eval.gen_cases --dry-run        # 只打印校验结果，不落盘
    python -m app.eval.gen_cases --force          # 覆盖已有固化文件（会使基线失效，需重签）

三条铁律（docs/designs/auto-eval-design.md §2）：
1. 生成调用走 ModelGateway（与业务同一条重试/降级链路）；
2. LLM 产物必须过确定性校验（关键词逐字在输入中、sub_kind 语义约束、批内去重），
   不过即剔除——剔除原因会打印，可据此调整身份卡后重新生成；
3. 用例只固化到 app/eval/generated/（进 git），跑分永远读固化文件，绝不现生成现跑。
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError

try:
    from app.eval.taxonomy import TIERS, sub_kind_of, sub_kinds_of_tier
    from app.eval.test_cases import SAMPLE_CASES
    from app.llm.gateway import GatewayExhaustedError, LLMRequest, get_gateway
    from app.schema.wrappers import strict_json_schema
except ModuleNotFoundError as exc:
    raise SystemExit(
        f"\n[依赖缺失] 未安装 {exc.name}。请先在项目根目录执行：\n"
        '    pip install -e ".[dev]"\n'
        "（国内网络不畅可加：-i https://pypi.tuna.tsinghua.edu.cn/simple）\n"
    ) from None

IDENTITY_PATH = Path("app/eval/identity.json")
GENERATED_DIR = Path("app/eval/generated")

INPUT_FIELD = "task"  # 本模板喂给应用的输入字段名
COUNT_FIELD = "expect_min_drafts"

MIN_LENGTH_MAX_CHARS = 120  # min_length 用例的输入长度上限

SYSTEM_PROMPT = (
    "你是严苛的评测工程师，擅长构造能暴露 LLM 应用弱点的测试输入。"
    "严格按 schema 输出；每条用例都必须贴合指定的分类定义。"
)


class GeneratedCase(BaseModel):
    tier: str = Field(description="happy | boundary | anomaly | adversarial")
    sub_kind: str = Field(description="分类定义中的子类标识")
    input: str = Field(description="喂给应用的完整输入文本")
    expect_keywords: list[str] = Field(description="应出现在应用输出中的关键词，可为空")
    expect_min_count: int = Field(ge=0, description="期望最少发现数；无风险/域外输入为 0")
    notes: str = Field(description="构造意图一句话")


class GeneratedCaseSet(BaseModel):
    cases: list[GeneratedCase]


def _norm(text: str) -> str:
    return re.sub(r"\s+", "", text)


def seed_inputs() -> set[str]:
    return {_norm(getattr(case, INPUT_FIELD)) for case in SAMPLE_CASES}


def validate_case(case: GeneratedCase, seen_inputs: set[str]) -> tuple[bool, str]:
    """确定性校验：LLM 生成物不过这里就进不了固化集。"""
    sub = sub_kind_of(case.tier, case.sub_kind)
    if sub is None:
        return False, f"未知层级/子类 {case.tier}/{case.sub_kind}"
    if not case.input.strip():
        return False, "输入为空"
    if case.tier == "anomaly" and (case.expect_keywords or case.expect_min_count):
        return False, "anomaly（域外/损坏）应无关键词且 expect_min_count=0"
    if case.sub_kind == "empty_risk" and case.expect_min_count != 0:
        return False, "empty_risk 必须期望 0 发现"
    if case.sub_kind == "min_length" and len(case.input) > MIN_LENGTH_MAX_CHARS:
        return False, f"min_length 输入超长（{len(case.input)} > {MIN_LENGTH_MAX_CHARS} 字符）"
    for keyword in case.expect_keywords:
        if keyword not in case.input:
            return False, f"关键词 {keyword!r} 未出现在输入中（疑似幻觉指标）"
    if _norm(case.input) in seen_inputs:
        return False, "与已有用例输入重复"
    return True, ""


def build_messages(identity: dict, tier: str, per_n: int) -> list[dict]:
    ident = identity["identity"]
    policy = ident.get("quality_policy", {})
    examples = "\n---\n".join(ident.get("input_examples", []))
    defs = "\n".join(
        f"- {s.tier}/{s.key}：{s.description}（判定要点：{s.check_hint}）"
        for s in sub_kinds_of_tier(tier)
    )
    user = f"""应用身份：{ident['name']}——{ident['description']}
目标用户：{ident.get('audience', '')}
质量倾向：{'宁多报不漏报' if policy.get('recall_bias') else '精确优先'}；{'域外输入应明确拒答' if policy.get('refuse_out_of_scope') else ''}
真实样例（风格参考）：
{examples or '（无）'}

请为以下每一类构造 {per_n} 条评测用例：
{defs}

硬性要求：
1. input 是喂给应用的完整输入文本，必须贴合该类定义；
2. expect_keywords 中每个关键词必须逐字出现在 input 里（它们用于检查输出命中）；
3. 无风险/域外/损坏类输入：expect_keywords 为空列表、expect_min_count=0；
4. 有风险的输入 expect_min_count >= 1；
5. 输入内容具体、多样，不要模板化重复。"""
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]


def generate_tier(
    tier: str, identity: dict, gateway, per_n: int | None = None
) -> tuple[list[dict], list[str]]:
    """生成一个层级的用例，返回 (通过校验的用例, 被剔除的原因列表)。"""
    per_n = per_n or identity.get("generation", {}).get("per_taxonomy", 3)
    request = LLMRequest(
        messages=build_messages(identity, tier, per_n),
        task="planning",
        structured=True,
        response_format=strict_json_schema(GeneratedCaseSet),
        metadata={"node": "gen_cases", "tier": tier},
    )
    response = gateway.complete(request)
    try:
        parsed = GeneratedCaseSet.model_validate_json(response.content)
    except ValidationError as exc:
        raise SystemExit(f"[{tier}] 模型输出不符合 GeneratedCaseSet 结构：\n{exc}") from None

    seen = seed_inputs()
    kept: list[dict] = []
    rejected: list[str] = []
    for case in parsed.cases:
        ok, reason = validate_case(case, seen)
        if not ok:
            rejected.append(f"{case.tier}/{case.sub_kind}: {reason}")
            continue
        seen.add(_norm(case.input))
        sub = sub_kind_of(case.tier, case.sub_kind)
        kept.append(
            {
                "id": f"{case.tier}-{case.sub_kind}-{len(kept) + 1:03d}",
                "tier": case.tier,
                "sub_kind": case.sub_kind,
                INPUT_FIELD: case.input,
                "expect_keywords": case.expect_keywords,
                COUNT_FIELD: case.expect_min_count,
                "notes": f"{case.notes}｜判定：{sub.check_hint if sub else ''}",
            }
        )
    return kept, rejected


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="从身份卡自动生成评测用例（生成一次，固化永久）")
    parser.add_argument("--tier", choices=TIERS, help="只生成某一层级")
    parser.add_argument("--per-taxonomy", type=int, default=0, help="每类生成条数（默认取身份卡）")
    parser.add_argument("--identity", type=str, default=str(IDENTITY_PATH))
    parser.add_argument("--out-dir", type=str, default=str(GENERATED_DIR))
    parser.add_argument("--dry-run", action="store_true", help="只打印校验结果，不落盘")
    parser.add_argument("--force", action="store_true", help="覆盖已有固化文件（基线将失效）")
    args = parser.parse_args(argv)

    identity_path = Path(args.identity)
    if not identity_path.is_file():
        raise SystemExit(f"身份卡不存在：{identity_path}（它是本工具唯一的必填输入）")
    identity = json.loads(identity_path.read_text(encoding="utf-8"))

    tiers = [args.tier] if args.tier else identity.get("generation", {}).get("tiers", TIERS)
    out_dir = Path(args.out_dir)
    gateway = get_gateway()

    for tier in tiers:
        target = out_dir / f"{tier}.json"
        if target.is_file() and not args.force:
            print(f"[{tier}] 已有固化文件（{target}），跳过；覆盖请加 --force")
            continue
        try:
            kept, rejected = generate_tier(tier, identity, gateway, args.per_taxonomy or None)
        except GatewayExhaustedError as exc:
            print(f"[{tier}] 生成失败（降级链全部失败）：{exc}", flush=True)
            return 1
        print(f"[{tier}] 保留 {len(kept)} 条，剔除 {len(rejected)} 条")
        for reason in rejected:
            print(f"    剔除 - {reason}")
        if args.dry_run:
            continue
        out_dir.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps({"tier": tier, "cases": kept}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"    已固化 -> {target}")

    print(
        "\n下一步：python -m app.eval.run_eval --suite all 验证新用例；"
        "满意后 python -m app.eval.run_eval --set-baseline 固化质量线"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
