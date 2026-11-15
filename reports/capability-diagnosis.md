# CommerceLens 能力瓶颈诊断

2026-11-15，研究基线为 PR #11 的 `a0eb357f321305ee5356be76728c906db4fbb4b6`。本报告以整题答案正确数为首要指标。SQL 完成表示工具返回了结果，包含空结果。按照原评分协议，截断结果仍判错。

Olist 优先验证 3B 的日期和配送资格提示。默认路径上 3B 得到 40/45，7B 得到 30/45。加入提示后分别为 45/45 和 39/45。通用单表回归上，两种模型都受益于 Schema Grounding。在相同 grounding 下，3B 为 15/48，7B 为 23/48。加倍生成上限不改变 3B 的准确率。Typed Plan 提升了简单布尔题的正确率，但两个模型的开发集总分均下降。

## 基线与用户入口

| 已核对的 PR | GitHub 实际头提交 | 代码和既有真实实验 |
| --- | --- | --- |
| [#6](https://github.com/re-tourist/commerce-analytics-agent/pull/6) | `c726c7f` | Olist 数据、只读策略、知识检索、分析工具和 Verification。45 题按 SQL、加 RAG、加工具、再加 Verification 得到 28、41、40、40 题正确。 |
| [#9](https://github.com/re-tourist/commerce-analytics-agent/pull/9) | `71040c2` | 增加引号 DDL 提示和定向重试。在原 80 题上正确数 29 → 43，SQL 完成 50 → 76。 |
| [#10](https://github.com/re-tourist/commerce-analytics-agent/pull/10) | `eef8012` | 把 DDL 和重试拆开，并记录可执行但答错的案例。原 80 题为 29/80（基础）、42/80（DDL）、30/80（重试）、43/80（组合）。另一组 48 题的历史分数为 3/48（基础）、15/48（组合）、12/48（再加通用语义指令）。 |
| [#11](https://github.com/re-tourist/commerce-analytics-agent/pull/11) | `a0eb357` | 整理真实界面演示和 Olist 参考审计。35 个参考自动验证，10 个仍待复核。45 个参考的正式人工验收仍待完成。 |

本次检查时四个 PR 均开放。代码审计以其匹配的本地 Git 提交为准，实验记录见 [MVP 验收](acceptance.md)、[Schema Grounding](schema-grounding.md)、[历史消融](semantic-holdout.md)、[历史错误审计](semantic-error-audit.md)、[Olist 复核](portfolio-release.md)。

| 用户入口 | Schema | RAG | 分析工具 | Verification |
| --- | --- | --- | --- | --- |
| Streamlit Natural language、CLI `ask` 默认、HTTP `/ask` 默认 | 实时读取列名和类型，附 Olist 关系说明。引号 DDL、定向绑定重试和通用语义实验开关均关闭。 | 开启。对内置业务定义做词项排序，最多取三段，原文随 prompt 发送。 | 开启。可走 SQL、`investigate`、知识或不可答路由。 | 开启。检查执行失败、输出截断、分组贡献对账。满足条件时两次尝试封顶。 |
| CLI `ask --variant sql` / `sql_rag` / `sql_rag_skills` | 同上 | 依次为关闭、开启、开启 | 依次为关闭、关闭、开启 | 均关闭 |
| Streamlit Preconfigured metric、CLI `metric`、HTTP `/investigate` | 直接调用受约束的 Olist 分析工具 | 无模型调用 | 直接调用 `investigate` | 走工具自身的口径与参数检查，不经过 Agent 图 |
| DataBench `full` / DDL + retry | 基础 schema / 引号 DDL | 两臂都没有 Olist 业务知识 | 两臂都仅有 SQL 和不可答 | 两臂都启用执行检查与有限重试 |

用本地 3B 实际调用 Streamlit 的 AppTest 按钮与 CLI 入口，并记录发送给真实模型的提示结构。Natural language 选择了 `investigate`，有三条检索记录和 `verify: passed`。预配置模式只有工具 trace。两种界面模式都显示 2018 年 6 月 15/917（1.64%）、7 月 30/936（3.21%），相差 +1.57 个百分点。分母为有已知配送状态的合格样本订单，月份按 `purchase_date` 左闭右开。CLI 的四种 `ask` 变体都返回 15,000 样本订单，只有 `full` 记录 Verification。直接运行 `metric` 得到 7 月 30/936，模型调用为零。HTTP 行为由入口代码和工程测试核对。 [Streamlit 入口](../app/streamlit_app.py) · [CLI 入口](../src/commercelens/interfaces/cli.py) · [HTTP 入口](../src/commercelens/interfaces/http.py) · [组装](../src/commercelens/bootstrap.py) · [Agent](../src/commercelens/application/agent/graph.py)

## 实验协议

- **数据范围**。Olist 45 题走生产默认 Agent 及原 grader，使用 15,000 个样本订单，沿用历史独立来源计算，人工验收仍未完成。DataBench 使用官网完整表和原 `databench-eval==4.0.1` 值比较器。开发集 24 题来自 Pokémon 和 Bakery。回归集 48 题来自 COL、Lift、Mortality 和 Books；磁盘目录与旧清单名仍是 `holdout`。24、48 和历史 80 题均已有接触，仅用于开发或回归。
- **数据核验**。DataBench QA 和完整 Parquet 哈希按项目固定版本核对，六张本地 DuckDB 表与源文件核对行数和多重集，每张表差集均为空。依次为 1,072、20,507、121、3,000、400、40 行。Olist 发行 ZIP 的 SHA-256 是 `967e41e04fc306fe604e2a693f488995a8b41e5047418f8a5c8e4abd6deca784`，既有样本订单 ID 摘要是 `93e5d327a4b40f9017d09c0e1648f0142fbc499fac7e2217816d2edde7dce175`。 [DataBench 固定版本](https://huggingface.co/datasets/cardiffnlp/databench/tree/e75d53add267d2f9cfa32efd65ad77f0807adfad) · [Olist 来源与样本](acceptance.md)
- **生成和执行**。llama.cpp b12383 Vulkan，RTX 4060 Laptop 8 GiB，单 slot，4,096 上下文，温度 0，seed 741，JSON object 模式，最多两次尝试。每次最多生成 384 token，预算消融改为 768。沿用 4 秒 SQL 超时、128 MB DuckDB 内存限制、200 行和 100,000 字节输出限制，以及表和函数策略。模型仅获问题和可用 schema／提示，答案和参考类型留在评分侧。
- **模型权重**。Qwen2.5-Coder-3B-Instruct 和 Qwen2.5-Coder-7B-Instruct 均采用发行方 Q4_K_M GGUF。3B 权重 2,104,932,800 字节，SHA-256 为 `724fb256bec1ff062b2f65e4569e871ad2e95ab2a3989723d1769c54294730b7`。7B 权重 4,683,073,536 字节，SHA-256 为 `509287f78cb4d4cf6b3843734733b914b2c158e43e22a7f4bf5e963800894d3c`。 [3B 固定版本](https://huggingface.co/Qwen/Qwen2.5-Coder-3B-Instruct-GGUF/tree/f74adce6aa16316c625447af059dbebe4983757c) · [7B 固定版本](https://huggingface.co/Qwen/Qwen2.5-Coder-7B-Instruct-GGUF/tree/13fb94bfda8c8cf22497dc57b78f391a9acb426a) · [llama.cpp b12383](https://github.com/ggml-org/llama.cpp/releases/tag/b12383)
- **对照**。同一模型内轮换 DataBench 每道题首跑的臂。跨模型可比臂使用相同的 Agent 代码、提示、数据、预算和评分；两种模型分别运行。延迟为本地端到端 P50/P95，包含图、模型和 SQL。计费 API 为 USD 0，未测电耗。
- **诊断边界**。最后一次失败按传输、长度或模型计划、解析或验证、关系或列绑定、执行策略、结果形状、结果类型、值不符分桶。值不符只说明原 grader 不接受结果，再结合问题和 SQL 手工区分统计语义与评分边界。长度另外按每次调用的 `finish_reason` 统计，避免重试后隐藏截断。

## 3B 的生成预算与错误分布

| 3B 对照 | 正确 | SQL 完成 | 模型调用 | 最长单次输出 | 因长度结束 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 开发 24 题，DDL + retry，384 | 9/24 | 24/24 | 24 | 41 token | 0 |
| 开发 24 题，DDL + retry，768 | 9/24 | 24/24 | 24 | 41 token | 0 |
| 回归 48 题，DDL + retry，384 | 15/48 | 33/48 | 65 | 58 token | 0 |
| 回归 48 题，DDL + retry，768 | 15/48 | 33/48 | 65 | 58 token | 0 |

384 和 768 两臂在配对的 72 道题上最终 SQL 相同。回归集基础提示的 82 次调用也全为 `stop`，最长 84 token。这组任务的失败没有呈现生成上限瓶颈。

| 48 道回归题，3B 最终失败 | 基础 | DDL + retry | 诊断 |
| --- | ---: | ---: | --- |
| SQL 解析或验证 | 19 | 13 | 后者 13/13 有未引用的多词列名或反引号。 |
| 关系绑定 | 9 | 0 | 关系名幻觉消失。 |
| 列或类型绑定 | 5 | 2 | 两题把带空格的真实列名输出成下划线版本。 |
| 结果形状 | 3 | 4 | 示例包括标量多行／空结果、排名结果附辅助聚合列。 |
| 结果类型 | 4 | 7 | 典型例子是布尔问题返回计数。 |
| 值不符 | 5 | 7 | 例如把男性解释为姓名首字母 M，或把女性解释为体重级别。 |
| 合计 | 45 | 33 | 3/48 → 15/48，修复 12，回退 0。 |

在 33 个完成 SQL 的 DDL + retry 任务中，有 18 个答案仍错。类型和形状诊断可定位输出合同，性别筛选等值错误需要用业务含义判断。历史 80 题已把 DDL 与 retry 分离，分别显示 +13 和 +1 题净增；本次 48 题只复跑了组合对照。 [历史拆分消融](semantic-holdout.md#development-and-component-ablation)

## 模型与系统的配对对照

| DataBench 回归 48 题，384 token | 正确 | SQL 完成 | P50/P95（秒） | 模型调用 | 输入／输出 token |
| --- | ---: | ---: | ---: | ---: | ---: |
| 3B，基础 | 3/48 | 15/48 | 3.19 / 5.78 | 82 | 15,638 / 2,356 |
| 3B，DDL + retry | 15/48 | 33/48 | 2.36 / 4.46 | 65 | 17,072 / 1,917 |
| 7B，基础 | 8/48 | 18/48 | 4.08 / 7.16 | 74 | 14,074 / 2,704 |
| 7B，DDL + retry | 23/48 | 43/48 | 2.56 / 5.07 | 51 | 13,015 / 1,847 |

**系统效应**。3B 加 grounding 修复 12 题，7B 修复 15 题，两者均零回退。7B 的表名策略失败由 15 降至 0，列／类型绑定由 3 降至 0。即便模型容量更大，它仍依赖明确的表与字段绑定。

**模型效应**。基础提示换 7B 修复 7 题，回退 2 题；grounding 下修复 10 题，回退 2 题。后一组 SQL 解析或验证失败从 13 降至 1，列／类型绑定从 2 降至 0。布尔从 1/12 到 4/12，分类值从 3/8 到 5/8，分类列表都是 3/7，数值标量从 5/14 到 7/14，数值列表从 3/7 到 4/7。模型升级和 grounding 都有收益，模型增益受提示支持影响。

**剩余瓶颈**。7B 加 grounding 后 43 题执行成功，其中 20 题仍错，包括 8 道结果形状、3 道类型和 9 道值不符。另外 5 道没有结果，其中 1 道解析失败、2 道不可答、2 道被既有函数策略拒绝。两个策略失败均由 `EXISTS` 触发。保留模型的同一谓词，用策略已允许的 `COUNT(*) > 0` 人工重放，`074_Lift:001` 和 `075_Mortality:000` 均通过原评分。这两题仍记在实测失败中。7B 两臂 125 次调用都正常停止，最长分别为 82 和 64 token。

**成本**。7B 权重比 3B 多 2.58 GB。3B 和 7B 推理期间观测到的整卡占用分别约 4.4 和 6.7 GiB（总 8 GiB，包含桌面及其他进程）。3B 部分计时与入口审计、另一个 3B 实验或下载并行，跨运行延迟仅作观测值；相同臂的精确速度差仍需隔离测量。Grounding 使 7B 调用次数从 74 次降为 51 次，基础提示的重试开销在本轮比加上额外 schema 的成本更高。

## Typed Analysis Plan 开发实验

原型放在 `benchmarks/`。模型用一次 JSON 响应声明结果类型、目标列、聚合、过滤、分组、排序和限制。编译器按实际列白名单转义标识符，把筛选、聚合和最终投影分别编译成 SQL。布尔支持行存在和聚合后与常量比较。查询依旧走原只读适配器和 Verification。当前只描述单表查询，排序只接受投影或聚合，过滤为简单 AND。无多列答案、跨列比较、`HAVING`、多键排序、联结或复杂日期计算。 [原型](../benchmarks/typed_analysis.py)

| 24 道开发题 | 整题正确 | SQL 完成 | 布尔正确 | 分类值 | 分类列表 | 数值列表 | 数值标量 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 3B，DDL + retry | 9/24 | 24/24 | 0/4 | 3/4 | 1/7 | 2/3 | 3/6 |
| 3B，Typed Plan | 5/24 | 12/24 | 2/4 | 0/4 | 0/7 | 0/3 | 3/6 |
| 7B，DDL + retry | 8/24 | 22/24 | 1/4 | 2/4 | 1/7 | 1/3 | 3/6 |
| 7B，Typed Plan | 7/24 | 12/24 | 2/4 | 0/4 | 2/7 | 0/3 | 3/6 |

- **布尔**。两道 Pokémon 存在性题从计数变成正确布尔值。Bakery 的唯一性题需要对比总数和不同 ID 数，模型生成了无效操作符。另一题问所有商品是否都有工作日记录，模型把全称条件理解为是否有任意工作日交易，输出类型正确而答案仍错。
- **投影**。直接 SQL 有 4 道结果形状错误，主要是排名列附上辅助计数。Typed Plan 已执行的查询均只投影一列，但这 4 道原错题没有改对，其中 3 道拒答，1 道计划无效。另有计划只输出辅助计数，说明单列类型合同无法证明列选对了。
- **统计粒度与覆盖**。直接 SQL 可从最高防御的行投影主类型，Typed Plan 将其写成按类型聚合并尝试按原列排序，校验拒绝。部分排名问题需要按另一个列排序后投影名称，当前语法表达不了；另有最常见类型问题遗漏传说宝可梦资格过滤，并返回各类型计数。编译器测试证实明确的分组与投影能正确编译，真实模型上的粒度改善尚无证据。

3B 原型修复 2 题、回退 6 题，8 个最终计划校验拒绝，4 个主动拒答。33 次调用、14,177/1,535 输入/输出 token、P50/P95 为 1.83/3.99 秒。对照为 24 次、6,262/638 token、1.29/1.61 秒。

7B 原型修复 4 题、回退 5 题。两道存在性题的基础 SQL 已正确理解谓词，被 `EXISTS` 策略拒绝，编译成计数比较后通过。另两题均移除了排名的辅助输出列。其一按主类型统计并排序符合题意，其二 `060_Bakery:013` 漏了下午筛选，恰好仍匹配参考答案，保留原评分。需要按独立字段排序的题及需要聚合后筛选的题依旧回退。7B 原型有 11 个最终计划校验拒绝和 1 个执行类型转换错误。36 次调用、15,406/2,357 token、P50/P95 为 4.40/9.13 秒；对照为 26 次、6,885/956 token、2.13/3.59 秒。

两种模型均未通过整题正确率和覆盖率的总体验证。原型说明编译能控制结果形状和部分可表达的粒度，真实语义仍取决于模型是否识别了正确的列、排序依据与资格过滤。这一版本保留为开发证据。

## Olist 小改动

| 默认完整 Agent 与 SQL 口径候选，45 题 | 正确 | SQL 完成／选择 SQL | P50/P95（秒） | 模型调用 | 输入／输出 token |
| --- | ---: | ---: | ---: | ---: | ---: |
| 3B，默认 | 40/45 | 32/32 | 1.07 / 1.41 | 45 | 38,771 / 2,411 |
| 3B，整月与资格提示 | 45/45 | 32/32 | 2.61 / 3.99 | 45 | 42,776 / 2,462 |
| 7B，默认 | 30/45 | 31/32 | 4.01 / 8.23 | 54 | 46,570 / 3,396 |
| 7B，整月与资格提示 | 39/45 | 30/32 | 4.27 / 8.40 | 53 | 50,378 / 3,385 |

在原提示中追加一段 Olist SQL 口径。它明确整月以次月首日作排他的上界，合格配送行以 `is_late IS NOT NULL` 定义，在订单粒度以 `AVG(CAST(is_late AS INT))` 得到 0–1 比例，并在按配送状态做评论比较前排除未知状态。没有增加工具、模型调用额度或评测特例。实验仅在 Olist 回归 harness 里启用。 [候选实现](../benchmarks/olist_cohort_experiment.py)

3B 默认路径的 5 个错题都通过原 Verification。4 道月度晚到率都用了包含次月首日的 `BETWEEN`。对 2017-05、2017-11、2018-01、2018-05 分别核对到晚到及合格订单数 14/525、139/1,100、50/1,064、54/1,016；其排他上界当天分别有 23、47、26、25 个已交付订单。四个正确窗口内均没有已交付但未知晚到状态的行。第五题按是否晚到比较评论时多出一个 NULL 组，由一条已交付但晚到状态未知的评论记录产生，合格的两组分别为 13,494 和 955 条订单评论记录。小改动修复这 5 个已知回归错误。

3B 候选再次执行得到 45/45，仍为 45 次调用，每题增加约 89 个输入 token。两次候选的 P50/P95 分别为 2.61/3.99 和 2.52/3.98 秒，运行负载不同，延迟差值无法归因于提示本身。

默认路径换 7B 修复 1 题、回退 11 题。10 道输出错误把次月首日算入月度订单数、订单粒度支付金额或晚到率，1 道从 `orders` 读取不存在的卖家字段，4 道未通过现有工具计划解码。7B 修复的唯一一题是排除未知配送状态后的评论分组。7B 加提示修复全部 10 道日界错误，另有 1 道回退，因将卖家字段绑定到 `orders`，合计净增 9 题。7B 的剩余失败是 2 道列绑定和 4 道工具计划解码。Olist 的收益集中在补足业务日期和资格口径，模型替换对这个用户路径的净效应为负。

## 下一阶段优先级

以下人日为单人实施估算，包含最小回归验证。独立题集收集和人工业务验收单独安排。

| 优先 | 方向 | 首个交付与取舍 | 估算 |
| --- | --- | --- | --- |
| 1 | Semantic Grounding | 先验证 Olist 的整月和资格提示候选，将指标单位、总体与订单／商品／卖家订单粒度挂在现有指标定义上。对通用表保留引号 DDL，并在真实问法里单独测枚举值、单位和过滤映射。当前已有 Olist +5 和通用表 +12/+15 的系统收益。历史宽泛语义提示在 48 题里回退 3 题，继续增加整段指令的优先级较低。 | 1–2 人日 |
| 2 | Semantic Verification | 先在能明确识别的整月和配送指标上做影子检查，核对半开区间、分母资格和结果列，不确定时记录原因。数量、金额和比例各自核对粒度与单位，禁止把同一份错误模型计划同时当断言和证明。确认误报后再决定是否重试。 | 2–4 人日 |
| 3 | Query Compiler | 保持小范围，优先评估行存在和简单聚合比较，以及按原字段排序后只投影所求字段。以两道已可重放的 `EXISTS` 为策略边界案例，沿用只读 SQL 策略。明确区分语法不支持、模型生成不合约和语义出错，未覆盖问题保留原 SQL 路径。完整编译器等可表示范围和端到端正确率都提高后再投资。 | 3–5 人日做窄切片 |

泛表场景的模型候选是 7B + DDL/retry。在 8 GiB 设备上可运行，回归收益为 +8 题，仍有 25/48 错误；先按部署设备容量做可选模型基准。保留 384 token 上限。新一轮应从新采集的 Olist 问法建立独立样本，覆盖时窗、分母、排序投影、比例单位与有歧义的业务词。冻结问题、人工参考和评分后再比较，分别报告净增、回退、拒答和延迟。此前的 DataBench 24、48、80 题只能用于开发或回归。

## 复现

从实验实现提交 `3849a0b88fca95ea5077fb85b2fcaf7192aedb0d` 或其报告提交开始。按项目指南安装依赖并重建本地 Olist 库，再准备两个 DataBench 子集。旧的 `holdout` 参数只用于选择已有的 48 道回归题。

```powershell
python -m benchmarks.databench --split dev --fetch
python -m benchmarks.databench --split holdout --fetch
```

分别在两次会话启动本地模型，每次只启动一个服务。使用同一个 llama.cpp 版本和所选设备。

```powershell
llama-server -m data/models/qwen2.5-coder-3b-instruct-q4_k_m.gguf --device Vulkan1 -ngl 99 -c 4096 -np 1 --host 127.0.0.1 --port 8080 --alias commercelens-local
# 停止 3B 后再启动 7B
llama-server -m data/models/qwen2.5-coder-7b-instruct-q4_k_m.gguf --device Vulkan1 -ngl 99 -c 4096 -np 1 --host 127.0.0.1 --port 8081 --alias commercelens-qwen-7b
```

```powershell
$env:COMMERCE_MODEL_URL = 'http://127.0.0.1:8080/v1'
$env:COMMERCE_MODEL = 'commercelens-local'
python -m benchmarks.run olist --variant full --output reports/runs/capability-olist-3b
python -m benchmarks.capability --cohort dev --arm grounded --arm grounded_768 --arm typed --output reports/runs/capability-dev-3b
python -m benchmarks.capability --cohort regression --arm full --arm grounded --arm grounded_768 --output reports/runs/capability-regression-3b
python -m benchmarks.olist_cohort_experiment --output reports/runs/capability-olist-cohort-3b
python -m benchmarks.olist_cohort_experiment --output reports/runs/capability-olist-cohort-3b-repeat

# 切换到 7B 服务后运行
$env:COMMERCE_MODEL_URL = 'http://127.0.0.1:8081/v1'
$env:COMMERCE_MODEL = 'commercelens-qwen-7b'
python -m benchmarks.capability --cohort regression --arm full --arm grounded --output reports/runs/capability-regression-7b
python -m benchmarks.run olist --variant full --output reports/runs/capability-olist-7b
python -m benchmarks.capability --cohort dev --arm grounded --arm typed --output reports/runs/capability-dev-7b
python -m benchmarks.olist_cohort_experiment --output reports/runs/capability-olist-cohort-7b

$env:COMMERCE_VERIFY_OLIST_DB = (Resolve-Path 'data/olist.duckdb').Path
python -m pytest -q --basetemp data/pytest-capability
```

每次用新输出目录保留 `records.jsonl` 和 `summary.json`。JSONL 包含 SQL、结果与模型输出，保存在忽略目录。按题目 ID 对齐各臂的 `success` 即可复算修复和回退。42 项工程测试通过，包含三项真实 Olist 来源对账和七项编译器测试。工程测试单独计数。 [原始配置与构建](../docs/reproduction.md)
