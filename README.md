# 民法与 AI 交叉领域法学写作 Skill

面向民法与人工智能交叉问题的中文学术研究与写作，支持文献分析、选题、论证框架、正文起草与修改、审稿及引注核验。在 Codex 输入 `$chinese-civil-ai-legal-writing`，接上任务和现有材料；也可用中文说明任务。版本 2.0.0，升级核验于2026-11-15至16日。保留原51篇方法卡与旧检索能力，新增三类资料分工、18篇候选证据台账、10篇正文分析及十个AI侵权专题。

## 调用例子

1. `$chinese-civil-ai-legal-writing` 我想从零写一篇关于数据共享责任的法学论文。先从给定规范和三条材料提炼问题、中心命题和章节框架。
2. `$chinese-civil-ai-legal-writing` 深度修改这篇侵权法论文。先指出论证缺口，正文只修我标出的两段，保留实体观点。
3. `$chinese-civil-ai-legal-writing` 分析这篇新论文的论证结构，逐节标出命题、反方、证据与原刊位置。
4. `$chinese-civil-ai-legal-writing` 审查第二节论证，区分规范前提、因果推断和价值选择，提出可直接替换的段落。
5. `$chinese-civil-ai-legal-writing` 按我上传的期刊体例核这几条脚注，分别检查题录、页码和正文命题支持。
6. `$chinese-civil-ai-legal-writing` 我补充一篇论文的原刊 PDF。核对作者、版本和来源后更新分析卡；全文只保存在我指定的私有目录。

[Skill 入口](SKILL.md) · [语料目录](references/corpus-catalog.md) · [写作模型](references/evidence-register.md) · [更新语料](references/research-methodology.md) · [本轮验收](tests/civil-ai-v2/index.md) · [旧测试记录](tests/evaluation.md)

民法与 AI 交叉领域论文按[六项专业工作流](references/professional-workflows.md)选资料和交付物，使用[资料索引](references/scholars/index.md)、[十项专题](references/ai-tort-topics/index.md)及[18篇证据索引](references/literature-index/index.md)。需要迁移既有方法卡时再用[方法检索](references/method-retrieval.md)，已有直接相关材料时不强配旧卡。起草默认[引言两段、摘要后写及直接表达偏好](references/writing-style/user-preferences.md)。

现有全文覆盖及元数据状态可运行 `python3 scripts/literature_lookup.py --validate` 查看；`--id 5 --show-analysis`读取单篇分析；`--author "作者名" --full-body`查询作者相关材料。此脚本检索台账和原创分析；正式法律依据、引文和页码仍按任务需要回源核验。全文原件保存在用户私有目录；分享包不含论文全文。
