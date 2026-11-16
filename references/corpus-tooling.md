# 本地语料工具

工具分开处理书目核验、私有全文和描述统计。阅读可追溯的在线全文也可以完成定性分析。定量统计另需合法保存且校对过的本地文本索引。

## 更新目录

`corpus/metadata/catalog.jsonl` 是 UTF-8 JSONL，每行登记一个出版版本。复核同名作者时同时比对署名、机构、研究方向、作者简介或原刊来源。正文采样优先用独著期刊论文。作者身份和书目出处的证据分别记录。

| 字段 | 填写方式 |
| --- | --- |
| `id`、`title`、`authors`、`year`、`venue` | 稳定 ID、原题、按原刊顺序的作者数组、出版年整数、原刊名 |
| `type` | `journal_article`、`book`、`book_chapter`、`newspaper`、`commentary` 或 `other` |
| `period`、`topics` | `early` 至 2009 年，`middle` 为 2010 至 2019 年，`recent` 自 2020 年起。主题用非空数组，可多选 |
| `source_url`、`retrieved_on` | 原刊或权威回源链接、核对日期 YYYY-MM-DD |
| `author_status`、`author_evidence` | `confirmed`、`needs_review` 或 `excluded`。已确认条目附身份核验依据 |
| `fulltext_status`、`extraction_quality` | 全文为 `available`、`partial` 或 `unavailable`。质量为 `high`、`medium`、`low` 或 `not_assessed` |
| `analysis_status`、`citation_status` | 分析为 `deep`、`partial` 或 `pending`。书目核对为 `verified`、`partial` 或 `unverified` |
| 可选字段 | `volume`、`issue`、`pages`、`doi`、`fulltext_url`、`source_note`、`rights_note`、`version_of`。未知字段可省略。提供对照论文时标记 `corpus_role: comparison` |

已确认的目标条目必须含原刊署名“王利明”。目录中的出版元数据、在线可读性、全文提取和人工深读分别登记。转载或修订保留各自版次，以 `version_of` 指向同一目录中可确认的原始版本。同题同作者或同 DOI 由脚本提示，是否为同一作品由研究者核定。不同标题的转载或修订仍需手工识别。

在 Skill 根目录运行以下命令。

```bash
python3 -B scripts/corpus_validation.py corpus/metadata/catalog.jsonl
```

输出缺项、作者消歧提示、重复候选和按已登记谱系统计的数目。谱系计数依赖已核实的版本关系。DOI 格式检查、目录一致性和 URL 格式通过后，仍须人工回源核对出版信息、引用页和实质命题。

## 加入用户补充的 PDF 或网页校对文本

先登记出版信息、精确版次、可读状态和访问限制。脚本读取研究者提供的本地 PDF 或 UTF-8 TXT/MD。网页文本保留文章原有顺序，去除导航和广告，段间空行。正文、摘要、引言、结语、脚注及参考文献在原来位置分段，尾注可标为独立区域。对存在扫描页、双栏、跨页段落、同页脚注或 OCR 错字的 PDF，先按原版校对，并登记提取偏差。PDF 需要 PATH 上的 `pdftotext` 或当前 Python 环境中的 `pypdf`。纯扫描件可先依法 OCR 并校对为 UTF-8 TXT，保存原版 PDF 和转换方式。

先预览并对照版面。预览输出块编号、判定分区、文件页序和最多 40 个字符的段首提示，不写入索引。将输出视为私有研究材料。

```bash
python3 -B scripts/corpus_analysis.py corpus/metadata/catalog.jsonl PAPER-ID "/path/to/核对稿.pdf" --preview
```

脚本在已有摘要内容后的空行切回正文，让没有“引言”标题的开篇段进入正文。只有摘要标签时，随后第一段归入摘要。连排关键词在同一文本块内合并，遇到明显句子或下一段时转入正文。对分页文件，带明确序号和“参见”等引文提示的页内脚注单独分区。圈号序号支持1—50；无引文提示、直接以国别或作者题名开头的脚注仍需按版面人工分区。同一块内的脚注续行随脚注保留。多段摘要、断栏、关键词与正文连排、脚注与正文无明显分隔等情况仍需逐块对照原刊。必要时按原刊整理为带空行及分页符的校对稿，复跑预览后再入库。

需要用于引注时，可手工核对版面并另存刊页映射 JSON。例如 `[[2, 53], [3, "S7"]]` 表示文件第 2 页是刊页 53，文件第 3 页是增刊页 S7。第一列从 1 起数，可只填已核实的页。物理页序和刊页标签均须唯一，封面或未核页可留空。把同一份映射通过 `--printed-pages` 传给预览和正式入库。输出中 `page` 是文件页序，`printed_page` 是人工核实后提供的刊页标签。脚本验证格式和页序范围，标签需由读者对照原刊确认。

```bash
python3 -B scripts/corpus_analysis.py corpus/metadata/catalog.jsonl PAPER-ID "/path/to/核对稿.pdf" \
  --processed-dir "/path/to/私有语料/processed" \
  --printed-pages "/path/to/刊页映射.json" \
  --quality high --quality-note "已对照原版核查段序、页数、脚注和 OCR" \
  --rights-note "合法取得的研究用副本，按来源条件保存和使用"
```

`--source-url` 可记录具体全文版次链接。省略时优先取目录的 `fulltext_url`。只保留稳定回源链接，认证令牌、机构登录参数和下载凭据留在本地访问环境。私有索引存放在 Skill 目录以外，记录书目 ID、原始字节 SHA-256、提取器、质量、文本块编号和文件页序。未提供刊页映射时，引用前按原刊核对精确页码。索引保留文本内容，交付和分享 Skill 时仅附书目与研究笔记。脚本可以读取旧索引。若要采用新的分区和刊页映射，用同一来源文件预览确认后加 `--replace` 重新生成索引。

## 分层统计和术语检查

```bash
python3 -B scripts/style_statistics.py corpus/metadata/catalog.jsonl \
  --processed-dir "/path/to/私有语料/processed" \
  --group-by period --tokenizer lexicon --top 40
```

- 默认仅纳入身份确认、完整可读、通过本地索引校验且提取质量为 `high` 或 `medium` 的期刊论文。每个版本谱系只计一个可用全文。结果列出样本与排除原因。没有合格样本时返回 `no_eligible_local_texts`。
- 默认正文覆盖引言、主体和结语，排除识别到的标题、摘要、关键词、脚注和参考文献。正文范围及章节位置按启发式识别，跨页段落可能拆成多个文本块。统计前抽查文本块和分区。必要时用人工校对稿替换索引。
- `--tokenizer lexicon` 用通用法学词表最长匹配，未识别汉字按单字计。可用 `--lexicon` 提供每行一词的补充表。输出记录词表哈希。已有 `jieba` 时可用 `--tokenizer jieba`，并保持各组使用同一版本和相同参数。`--tokenizer chars` 得出字粒度数据。词与字单位的结果应分别解释。
- 词元按每万词元计，连接表达按每万汉字计，并列涉及论文数。句长和段长以汉字和 ASCII 字母数字计数，排除标点。连接表达用最长字面匹配，语法功能需回读段落判断。
- `--group-by` 可设 `corpus_role`、`period`、`topic`、`authorship`、`venue` 或 `paper`。各组始终区分研究对象和对照。做作者比较时按年份、主题、期刊及文章类型配对。多主题论文可进入多个组，分组数量不能相加当作独立论文数。
- `--terms` 接受如 `{"个人信息":["个人资料","个人数据"]}` 的 UTF-8 JSON。报告列出每篇的字面命中和文本块 ID。两种用词可能对应不同概念，回读原文后再判断术语是否漂移。
- 频率、长度和词表命中用来定位值得细读的现象。作者特征还需要多个独著文本中的功能一致性、同层对照、反例和具体位置。

## 运行工具测试

```bash
python3 -B -m unittest discover -v -s tests -p test_corpus_tools.py
```

测试材料为合成夹具。PDF 用例需要环境可导入 `reportlab` 以生成测试文件，读取后端仍为 `pdftotext` 或 `pypdf`。真实作者归纳和写作任务表现另行验证。
