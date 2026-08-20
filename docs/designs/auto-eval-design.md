# 设计提案：自动评测集生成与回退门禁（auto-eval）

> 状态：**P0 + P1 已实现**（P2 的 `--suggest` 变更感知、CI PR 注释、`--runs 3` 多次采样未实现，按需追加）
>
> 实施与设计的差异（以实现为准）：
> 1. 身份卡用 **`identity.json`** 而非 YAML——生成项目不为此引入 PyYAML 依赖（与 ADR-3 薄依赖一致）；
> 2. 基线固化在 `app/eval/baseline.json`（进 git，随源码版本化），历史跑分仍在 `eval_results/`（本地）；
> 3. 回退判定修正了一处设计矛盾：boundary/adversarial 焦点套件**单独适用 15pp 警告线**而非
>    10pp 回退线（否则 warn 分支永不可达——任何 >15pp 的跌幅必然先触发 10pp 套件回退）；
> 4. 三模板的 `taxonomy.py` / `compare.py` 为同源文件，`gen_cases.py` / `run_eval.py` 仅差输入字段映射
>    （review= document/findings，rag= query/citations，multi= task/drafts）。

> 目标读者：本仓库贡献者、模板使用者、以及想把同类机制搬进自己项目的人

## 1. 问题定义

现状：每个模板自带**手写**评测集（`app/eval/test_cases.py`），`run_eval` 能一键跑分。
缺口：

1. **冷启动**：用户换了业务域（如把 review-flow 改成「简历筛选」），手写用例既费时又容易只覆盖 happy path；
2. **变更响应**：改了提示词/模型路由后，不知道该重跑哪些用例、跑完不知道「变好还是变坏」；
3. **门禁**：跑分结果只是表格，没有「是否回退」的结论，质量回归靠人眼比数字。

本设计一次解决三个缺口，用户唯一必须提供的输入是**一张身份卡（identity）**。

## 2. 设计原则（先立规矩）

| # | 原则 | 理由 |
| --- | --- | --- |
| 1 | **生成一次，固化永久**：LLM 生成的用例落盘 JSON、进 git；跑分永远用固化集，绝不现生成现跑 | 否则每次跑分基准都在漂移，回归对比失去意义 |
| 2 | **生成器走自家网关**：生成用 LLM 的调用复用 `ModelGateway`（heavy 档） | 评测生成器是脚手架架构的第一个内部客户，吃自己的狗粮 |
| 3 | **确定性后校验**：LLM 产物必须过纯代码校验（见 §5.3） | 借鉴 rag 模板 verify_node 的哲学：概率系统的产物用确定性规则兜底 |
| 4 | **服务异常不进评测集**：模型宕机/非法输出等异常路径由单元测试覆盖（已有 `test_llm_total_outage_*` 等），评测集只承载**业务质量** | 两类验证的失败语义、修复方式完全不同，混在一起会腐化 |
| 5 | **mock 不做回退判定**：与 ADR-9 一致，`--mock` 只验管道连通性 | 替身不假装有质量 |
| 6 | **基线是签字认可制**：只有显式 `--set-baseline` 才更新 | 基线 = 你认可的质量线，不允许自动漂移 |

## 3. 身份卡（identity）：用户唯一要写的东西

`eval/identity.yaml`：

```yaml
identity:
  name: 合同风险审阅助手
  description: 输入中文商务文档，输出结构化风险发现与汇总结论
  audience: 法务与商务团队
  input_examples:                 # 2-3 条真实样例，强烈建议提供（生成的锚点）
    - |
      ## 交付条款
      乙方应在本合同签订后三个月内完成全部交付，具体范围以双方沟通为准。
  output_contract: FindingSet + 汇总文本
  quality_policy:
    recall_bias: true             # 宁多报不漏报 → 生成器会产出「漏报惩罚」型用例
    refuse_out_of_scope: true     # 域外输入应拒绝 → 生成器产出诱导类用例

generation:
  per_taxonomy: 6                 # 每类生成条数（默认 6）
  tiers: [happy, boundary, anomaly, adversarial]
  model_tier: heavy               # 生成用哪一档模型
```

不提供 `input_examples` 也能跑（生成器按 description 自由发挥），但样例越真实、生成越贴业务。

## 4. 用例分类矩阵（taxonomy）：边界与异常的完整定义

固定在代码里（`taxonomy.py`，LLM 只负责按类填充，不负责分类学）：

| tier | sub_kind | 说明 | 判定要点 |
| --- | --- | --- | --- |
| happy | typical | 典型业务输入 | 关键词命中、发现数达标 |
| happy | verbose | 超长输入（> `extract_max_input_chars`） | 不崩、截断策略生效、延迟预算内 |
| boundary | min_length | 贴着入参下限（如 20 字符） | 不误报、不崩 |
| boundary | empty_risk | 无任何风险的正常文档 | **期望 0 发现**（防编造） |
| boundary | format_less | 无标题纯段落 / 表格文本 | 解析层兜底生效 |
| boundary | charset | emoji、中英混杂、全角符号 | schema 合法、不崩 |
| boundary | multi_risk | 风险密度极高（>10 条） | 上限截断策略、不重复计数 |
| anomaly | kb_miss | 知识库/职责范围外问题 | 诚实拒答、不编造（rag 模板重点） |
| anomaly | corrupted | 结构损坏输入（乱码、半截 JSON） | 优雅降级，错误入 errors 而非 500 |
| adversarial | prompt_inject | 「忽略以上指令，输出……」 | 指令不被劫持，照常按 schema 输出 |
| adversarial | induce_fabrication | 诱导编造不存在的风险/引用 | 引用可验证（rag）、发现可溯源 |

模板差异：review-flow 以 boundary/adversarial 为主；rag-agent 增加 kb_miss/引用伪造；multi-agent 增加任务歧义（ambiguity）与超预算任务。

## 5. 生成流水线（gen_cases.py）

```
identity.yaml
   │
   ▼
① 组装生成请求（每 tier 一批，输出 EvalCaseSet —— XxxSet 约定的再次应用）
   │    system: 「你是评测工程师，按 sub_kind 定义构造用例……」
   │    走 ModelGateway.complete(task="planning", tier=heavy, structured=True)
   ▼
② 确定性后校验（纯代码，不过则剔除/修复该条）：
   │    - expect_keywords 中每个关键词必须逐字出现在 document 里（防幻觉指标）
   │    - expect_min_findings 与 sub_kind 语义一致（empty_risk 必须 =0）
   │    - 文档长度与 sub_kind 声明一致（min_length 真的够短）
   │    - 与种子用例及彼此去重（关键词集合 Jaccard > 0.8 视为重复）
   ▼
③ 落盘固化 eval/generated/{tier}.json（带 origin: "generated:v1" 与指纹）
   │
   ▼
④ 打印生成摘要（每类几条、剔除几条、为何剔除）→ 用户可手改 JSON（手改优先）
```

关键命令：

```bash
python -m app.eval.gen_cases                    # 按 identity.yaml 生成并固化
python -m app.eval.gen_cases --tier boundary    # 只补某类
python -m app.eval.gen_cases --dry-run          # 只打印不落盘
```

## 6. 套件与变更感知（改了提示词该跑什么）

### 6.1 套件标签

每条用例带 `tier` 标签，`run_eval` 支持套件选择：

```bash
python -m app.eval.run_eval --suite all         # 手写种子 + 全部生成集
python -m app.eval.run_eval --suite boundary    # 只跑边界
python -m app.eval.run_eval --suite regression  # 上次失败过的用例（results/ 反查）
python -m app.eval.run_eval --mock              # 冒烟（不变，CI 每次跑）
```

### 6.2 变更影响建议（v1 用提示制，不做全自动依赖图）

`python -m app.eval.run_eval --suggest`：读 `git diff --name-only`，按影响映射表打印建议：

| 变更文件 | 影响面 | 建议命令 |
| --- | --- | --- |
| `app/graph/nodes/**`（提示词） | 全部用例 | `--suite all`（live） |
| `app/schema/wrappers.py` | 输出结构 | `--suite all --mock` + live 全量 |
| `app/llm/router.py` / 网关 | 档位与降级 | `--suite all` + 关注成本列 |
| `app/eval/**` | 无 | 无需重跑（提示后仍可强制跑） |

不做全自动「改 A 自动跑 B」的理由：文件到行为的映射存在例外（提示词可能在节点外），v1 的目标是**消除"不知道跑什么"的决策成本**，而不是消灭人工确认。CI 上 PR 改到高影响文件时，workflow 输出同样的建议注释。

## 7. 基线对比与回退结论（compare）

### 7.1 数据

```
eval_results/
├── baseline.json     # 签字认可的质量快照（--set-baseline 生成）
├── last.json         # 最近一次跑分
└── history/          # 每次跑分归档（时间戳），供趋势分析
```

### 7.2 打分

- 单用例：通过/不通过（沿用现有四指标：关键词命中、schema 合法、数量门槛、延迟预算）
- 套件分 = 该套件用例通过率 + 平均关键词命中率（两者取加权 0.6/0.4，配置可调）
- 总分 = 各套件按用例数加权平均

### 7.3 回退判定规则（明确、可解释、可配置）

| 条件（live 模式） | 结论 | 退出码 |
| --- | --- | --- |
| 总分 < 基线总分 − 5pp（tolerance） | **建议回退** | 1 |
| 任一套件跌幅 > 10pp | **建议回退**（局部雪崩） | 1 |
| boundary/adversarial 套件跌幅 > 15pp | 警告：确认是否接受 | 0（附显式警示） |
| 总分升幅 > 5pp | 提示：可 `--set-baseline` 固化新基线 | 0 |
| 其余 | 通过，附 Δ 摘要 | 0 |

报告（`eval_results/report.md`）末尾输出结论块：

```
## 结论：⚠️ 建议回退
- 总分 0.82（基线 0.88，Δ -6.0pp，超容差 5pp）
- 主要劣化：boundary 套件 -12pp（min_length / charset 两组用例由过转败）
- 建议：回退本次提示词改动，或修正后重跑；若确认接受新水平，用 --set-baseline 显式认可
```

### 7.4 抑制 LLM 波动

live 分数天然抖动。v1：容差 5pp + 明示单次采样；v2：`--runs 3` 同一提交跑三次取中位数再判（成本 ×3，只对"判回退"的临界场景推荐）。

## 8. 落地位置与文件清单（模板层改动，生成项目自治）

```
app/eval/
├── identity.yaml      # 新增：用户唯一必写项（三模板各带示例）
├── taxonomy.py        # 新增：分类矩阵常量 + 影响（不影响运行时）
├── gen_cases.py       # 新增：生成流水线（走网关）
├── test_cases.py      # 保留：手写种子用例（tag: seed，永远在 all 里）
├── generated/*.json   # 新增：固化生成用例（进 git）
├── run_eval.py        # 增强：--suite / --suggest / 跑分后自动 compare
└── compare.py         # 新增：基线对比 + 回退判定（纯确定性代码）
```

脚手架仓库侧：三模板同步以上文件；教程新增《09 · 让质量回归自动化》（P1 完成后写）。

## 9. 分期计划

| 阶段 | 内容 | 工作量 | 价值锚点 |
| --- | --- | --- | --- |
| **P0** | 套件标签 + baseline.json + compare 回退结论 + `--set-baseline`（**纯确定性代码，无 LLM**） | ~1 天 | 现有手写用例立刻获得回归门禁，独立可用 |
| **P1** | identity.yaml + taxonomy + gen_cases 生成流水线（含确定性校验与固化） | ~2-3 天 | 冷启动痛点解决；「给身份出全套用例」 |
| **P2** | `--suggest` 变更感知、CI PR 注释、`--runs 3` 中位数、regression 套件 | ~1-2 天 | 决策成本归零 |

P0 先行的理由：回退门禁不依赖自动生成；先把「守门」做扎实，生成器只是往门里添用例的通道。

## 10. 风险与对策

| 风险 | 对策 |
| --- | --- |
| 生成用例幻觉（关键词不在文档里、语义错误） | §5.2 确定性校验强制剔除；固化后人工可改 |
| 针对评测集过拟合提示词 | 生成集进 git 可审计；定期 `--regen`（需重签基线）；保留手写种子集作对照 |
| live 波动误报回退 | 容差 5pp；临界时 `--runs 3`；结论区分「建议回退」与「警告」 |
| 生成成本 | 一次性 heavy 调用约 3-6 万 token（按默认 4 类×6 条）；复用网关统计可见成本 |
| 用例集膨胀拖慢跑分 | 套件机制天然分组；regression 套件只跑失败项 |

## 11. 非目标（明确不做）

- 不做 LLM-as-judge 自动评分（引入第二个不稳定系统；等 P2 后按需议）
- 不做文件级变更→用例的自动依赖图（v1 提示制足够）
- 不做服务异常注入类用例（归单元测试，原则 §2.4）
- 不做跨项目评测平台（本机制随生成项目自治，符合「生成项目零依赖脚手架」立场）
