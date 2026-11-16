---
name: chinese-legal-academic-writing
description: 协助中文民法与人工智能法论文的文献分析、选题、框架、正文、深度修改、审稿和引注核验；按证据分别使用王利明论文的写作观察、程啸与林洹民的教义学方法及AI侵权争议资料，也支持其他中文法学论文。
---

# 中文法学学术写作

围绕具体法律问题形成可审查的原创论证。三库分别承担不同任务：王利明（中国人民大学法学院）的独立署名样本支持写作观察；程啸、林洹民支持教义学方法分析；AI侵权作者群支持争议比较。不得把不同作者混成王利明个人文风，也不得将任何学者结论直接作为现行法。

## 先选择资料和功能

按 [专业工作流](references/professional-workflows.md) 选择文献分析、框架、正文、深改、引注或审稿。选题、语言精修等旧模式仍按 [模式与交付](references/work-modes.md) 使用。起草或修改连贯文本时同时读取 [用户行文偏好](references/writing-style/user-preferences.md) 和 [正文行文](references/prose-style.md)。默认引言不超过两段，摘要在正文论证形成后写；具体任务要求优先。

提出、修改或审查实质论证时，按需读取 [写作规则](references/writing-rules.md)。用户给足输入就直接交付；关键事实缺失时先完成可独立成立的部分，标明依赖该事实的结论。

AI侵权研究先从 [十专题入口](references/ai-tort-topics/index.md) 选择直接相关的1—2项，再用 [文献与证据索引](references/literature-index/index.md) 回到原分析及真实覆盖范围。专题提供截至核验日的研究起点；提出当前法结论时须重新核查变化，特别是2026年最高法涉AI意见。资料不足时完成可独立成立的部分，把缺项放在相应推理处。

写作观察见 [王利明](references/scholars/wang-liming.md)，教义学方法见 [程啸](references/scholars/cheng-xiao.md)、[林洹民](references/scholars/lin-huanmin.md) 及 [方法工具](references/doctrinal-methods/operations.md)。AI观点按专题查找，作者入口见 [学者与角色](references/scholars/index.md)。只读当前环节需要的模块。

## 选择方法

需要迁移既有王利明论文的论证步骤时，按 [方法检索](references/method-retrieval.md) 从旧争点索引选择1—2张相关卡，保留卡ID、发表语境、适用及不适用部分；新18篇资料用 `scripts/literature_lookup.py` 按编号、作者或证据等级定位。已有直接相关材料时不强配旧卡。方法卡不能替代现行法或正式引注核验。

## 写作与核验

1. 定位具体事实、现行规范冲突或学说争议，再陈述需要解决的问题和中心命题。区分现行规则、对规则的解释及立法建议。
2. 用要件、范围、规则顺位或法律效果检验概念区分。把规范、案例、学说、经验事实分别作为论据，说明它们能支持哪一步推论。
3. 针对能够动摇结论的反例或竞争解释，明确其成立条件、对结论的影响及修正。跨部门法时先确认本领域的法益、规范体系、救济主体及方法，再迁移论证步骤。
4. 以本段的论证任务决定篇幅和句式。用明示的主语、条件与因果关系连接分论点。对长句做拆分时保留例外和限定。正文与改写范围服从用户指令。
5. 审查新加或改变的法条、案例、数字、页码和直接引文。材料缺失、效力不明、版本冲突或需要正式引注时重新检索。使用 [引注规则](references/citation-rules.md)；保留 `[待核：具体缺项]`，同时区分只核了题录和已核到正文位置。
6. 交付前核对核心问题有回应、段落有必要、概念一致、推理有依据、文本用自己的表达。完整稿按需要附待核表；单段修改按用户给定输出范围交付。

与本地技能协作时，按环节沿用 `lawpaper` 的法学方法、`anti-defensive-writing` 的直接表达。文献回源可用 `academic-research-suite`，引注规则与缺项先用 `legal-citation-comprehensive`，只有已核验引注需要写入 DOCX 时调用 `legal-citation-automator`。具体法条、效力及案例核查按已授权的 `pkulaw-mcp-legal-research` 子流程或官方原始来源处理。

把每项关键判断记为“现行规范 / 裁判立场 / 学术观点 / 本次分析建议”，保留来源、版本、位置与条件。期刊摘要只支持摘要实际写出的主张；选编不支持原论文完整结构；全文转载缺注不能生成原刊页码。疑似不存在的题录应写“未核实”，检索未命中本身不能证明伪造。详细边界见 [证据与更新](references/literature-index/evidence-and-expansion.md)。

## 读新文献、更新语料与模型

- 单篇分析先读 [研究方法与更新](references/research-methodology.md)，用 [文献分析模板](templates/literature-analysis.md) 生成按原版节或页定位的分析卡。摘要、目录、选编各自记录覆盖范围。
- 扩展语料时，用 [作者与边界](references/author-profile.md) 核对署名与机构，按 [书目索引](references/corpus-catalog.md) 定位目录和检索记录。依 [工具说明](references/corpus-tooling.md) 先预览正文分区，再核对文件页序和原刊页码。完成校对后处理与统计合法取得的材料。具体研究结论见 [证据登记](references/evidence-register.md)。
- 只有跨期、跨议题的独立署名全文有足够可定位证据，且记录过反例和适用范围时，才将归纳写进默认规则。将通用法学方法、样本内规律和作者特异性分开。缺少匹配对照的语言指标保留为研究观察。以用户授权范围保存处理文件，Skill 内仅保留公开书目信息、原创分析及聚合数据。
