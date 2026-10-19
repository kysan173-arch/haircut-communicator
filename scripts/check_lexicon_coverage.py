"""L2 词典覆盖测试：真实原话 → 行级「口语别名」反查。

核心逻辑：用户在理发店说的几乎不会是术语。如果一条真实原话在词典的
「口语别名」列检索不到，那 L3 翻译必然跑偏——这是可提前判定的失败。

**判据（v2，2026-10-19 重写）**
旧版用 `kw in glossary` 做全文字符串包含，等于「这个词你在 166 行里写过没有」，
永远通过、不携带信息量。现改为：

1. **只在「口语别名」列反查**。效果列 / 特征列 / 适配脸型列一律不参与匹配——
   这正是 glossary「使用纪律」的要求：效果列只用于解释，不用于反查方案。
2. **行级判定**：命中必须落到某一行，且该行的标准术语等于期望值。
3. **负样本**：效果描述类原话必须**零命中**。命中任何术语行 = 越界
   （把「想显脸小」映射到「渐变」就是替用户选方案）。

两条腿都要有：只有正样本会奖励越界，只有负样本测不出覆盖。

用法：
    python check_lexicon_coverage.py
退出码 0 = 全通过，1 = 有失败项
"""

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
GLOSSARY = SKILL_ROOT / "references/glossary-cutting.md"

ALIAS_COLUMN = "口语别名"
# 别名与用户原话的字符集相似度下限（低于此视为不同说法）
SIMILARITY_THRESHOLD = 0.65
MIN_TOKEN_LEN = 2


@dataclass
class AliasRow:
    term: str
    section: str
    aliases: list[str] = field(default_factory=list)


@dataclass
class Case:
    utterance: str
    kind: str  # "term" | "unmapped"
    expect: list[str]
    reason: str


# ── 测试集 ──────────────────────────────────────────────────
# kind="term"     → 用户已指明维度且指明类型，必须命中期望术语之一
# kind="unmapped" → 用户只说效果 / 只说维度未说类型 / 只是发质信息，
#                   必须零命中。命中任何术语即为越界，应转追问。
TEST_CASES = [
    # ── 正样本：维度 + 类型都说了，必须能反查到术语 ──
    Case("两边弄短点", "term", ["渐变"], "指明部位（两边）+ 方向（短），渐变为标准映射"),
    Case("两边推短", "term", ["渐变", "铲青"], "推短是渐变/铲青的口语说法"),
    Case("两边剃光", "term", ["铲青"], "剃光 = 推到极短，铲青"),
    Case("鬓角弄利落点", "term", ["推边"], "鬓角收窄 = Taper"),
    Case("层次感强一点", "term", ["高层次"], "用户明确说了「层次」"),
    Case("头顶蓬松点", "term", ["高层次", "高颅顶"], "指明部位（头顶）+ 效果（蓬松）"),
    Case("有点轻盈感", "term", ["高层次"], "轻盈是层次的直接口语别名"),
    Case("齐刘海", "term", ["空气齐刘海"], "指明刘海类型"),
    Case("八字刘海", "term", ["八字刘海"], "指明刘海类型"),
    Case("发尾往里收", "term", ["内扣"], "指明发尾走向"),
    Case("发尾往外翘", "term", ["外翻"], "指明发尾走向"),
    Case("打薄一点", "term", ["打薄"], "指明处理方式"),
    Case("剪短点薄点能扎上就行", "term", ["打薄"], "用户明确说了「薄点」"),
    Case("发量少想要蓬松的层次", "term", ["高层次"], "用户明确说了「层次」+「蓬松」"),
    Case("后面留个台阶", "term", ["方颈线"], "指明后颈形状（台阶）"),
    Case("剪到肩膀", "term", ["锁骨发"], "长发剪短的高频表述"),
    Case("发尾一刀切", "term", ["齐发尾"], "指明发尾形状"),
    Case("别打层次", "term", ["零层次"], "用户明确否定了层次这一技术"),

    # ── 负样本：必须零命中 ──
    Case("剪短一点但别太短", "unmapped", [], "长度未量化 → 追问厘米，不得映射术语"),
    Case("稍微修一下", "unmapped", [], "整体约束型原话 → 进约束区块，不落维度"),
    Case("修一下就行", "unmapped", [], "整体约束型原话 → 进约束区块，不落维度"),
    Case("留长一点但要修", "unmapped", [], "长度未量化 → 追问"),
    Case("显得精神一点", "unmapped", [], "效果描述 → 追问改哪个部位"),
    Case("想显脸小", "unmapped", [], "效果描述 → 追问两侧/露额/发尾"),
    Case("别太老气", "unmapped", [], "效果描述 → 追问具体部位"),
    Case("显得温柔", "unmapped", [], "效果描述 → 追问具体部位"),
    Case("想显高一点", "unmapped", [], "效果描述 → 追问具体部位"),
    Case("头发太塌了", "unmapped", [], "效果描述 → 追问发根支撑还是整体减量"),
    Case("留个刘海", "unmapped", [], "维度已定、类型未定 → 给 2-3 个类型让用户选"),
    Case("修一下发尾", "unmapped", [], "维度已定、方向未定 → 不得默认内扣"),
    Case("刘海厚一点", "unmapped", [], "维度已定、属性未定 → 追问"),
    Case("婚礼要用留长发但想剪短", "unmapped", [], "冲突需求 → 追问优先级，不得自行定方案"),
    Case("自然卷想剪短", "unmapped", [], "长度意图 + 发质约束，无术语可映射"),
    Case("头发硬容易炸", "unmapped", [], "发质信息输入 → 只做可行性提示，不得输出打薄"),
    Case("细软发质", "unmapped", [], "发质信息输入 → 只做可行性提示"),
    Case("到腰的长发", "unmapped", [], "长发表述不是需求 → 追问要改哪儿"),
    Case("想显瘦一点", "unmapped", [], "效果描述 → 追问部位"),
    Case("别剪太碎", "unmapped", [], "否定句式：说的是不要碎剪，不得正向匹配碎剪"),
    Case("后脑勺修的圆满一点", "term", ["圆颈线"], "指明部位（后脑勺）+ 形状（圆满/圆弧）"),
]


def normalize(text: str) -> str:
    """去掉标点与空白，只留汉字/字母/数字，便于字符集比对。"""
    return re.sub(r"[^\u4e00-\u9fffA-Za-z0-9]", "", text)


def similarity(a: str, b: str) -> float:
    """字符集 Jaccard 相似度。中文短句没有词边界，字符集比分词更稳。"""
    sa, sb = set(normalize(a)), set(normalize(b))
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def is_separator(cells: list[str]) -> bool:
    joined = "".join(cells)
    return bool(joined) and set(joined) <= set("-: ")


def parse_alias_rows(text: str) -> list[AliasRow]:
    """只解析含「口语别名」列的表格，逐行取出标准术语与别名清单。"""
    rows: list[AliasRow] = []
    section = ""
    header: list[str] | None = None
    alias_idx = -1

    for raw in text.splitlines():
        line = raw.strip()

        if line.startswith("## "):
            section = line.lstrip("# ").strip()
            header = None
            continue

        if not line.startswith("|"):
            header = None
            continue

        cells = [c.strip() for c in line.strip("|").split("|")]
        if header is None:
            header = cells
            alias_idx = header.index(ALIAS_COLUMN) if ALIAS_COLUMN in header else -1
            continue

        if is_separator(cells) or alias_idx < 0:
            continue

        term = cells[0]
        if not term or term == "—":
            continue

        aliases_raw = cells[alias_idx] if alias_idx < len(cells) else ""
        aliases = [a.strip() for a in re.split(r"[、，,/／]", aliases_raw) if a.strip()]
        rows.append(AliasRow(term=term, section=section, aliases=aliases))

    return rows


def match_rows(utterance: str, rows: list[AliasRow]) -> list[tuple[AliasRow, str]]:
    """反查：返回 (命中的行, 命中的别名) 列表。只在别名列比对。"""
    hits: list[tuple[AliasRow, str]] = []
    u = normalize(utterance)

    for row in rows:
        for alias in row.aliases:
            a = normalize(alias)
            if len(a) < MIN_TOKEN_LEN:
                continue
            contained = a in u or u in a
            if contained or similarity(a, u) >= SIMILARITY_THRESHOLD:
                hits.append((row, alias))
                break

    return hits


def dedupe_terms(hits: list[tuple[AliasRow, str]]) -> list[str]:
    seen: list[str] = []
    for row, _ in hits:
        if row.term not in seen:
            seen.append(row.term)
    return seen


def term_matches(expected: str, actual_row_term: str) -> bool:
    """术语名比对。词典里一行可能挂多个名字（「铲青 / 底切」），要能拆开比。"""
    parts = [normalize(p) for p in re.split(r"[/／、\s]", actual_row_term) if normalize(p)]
    ne = normalize(expected)
    if not ne:
        return False
    return ne in parts or ne in normalize(actual_row_term)


# 判据自检：故意给错期望，比对逻辑必须判它不通过。
# 防的是「判据恒真」——旧版 `kw in glossary` 就是这样骗过所有人的。
SELF_CHECK = [
    ("打薄一点", "内扣"),
    ("齐刘海", "八字刘海"),
    ("发尾往里收", "外翻"),
]


def self_check(rows: list[AliasRow]) -> list[str]:
    """返回自检失败项。自检失败说明判据本身坏了，比用例失败更严重。"""
    problems: list[str] = []
    for utterance, wrong_term in SELF_CHECK:
        terms = dedupe_terms(match_rows(utterance, rows))
        if any(term_matches(wrong_term, t) for t in terms):
            problems.append(
                f"「{utterance}」被误判为命中「{wrong_term}」，比对逻辑不可信"
            )
    return problems


def check_length_anchors(text: str) -> list[str]:
    """长度锚点资源存在性。

    追问话术（耳上/耳垂/后颈）与长发场景（肩线/胸线/腰线）都靠这张表。
    锚点缺失 = 追问只能给模糊选项，长发用户无处落地。
    """
    required = ["耳上", "耳垂", "下颌线", "眉上", "锁骨", "肩线", "胸线", "腰线", "后颈发际线"]
    m = re.search(r"关键锚点参照物.*?\n(.*?)(?=\n## |\n--- )", text, re.S)
    block = m.group(1) if m else ""
    return [a for a in required if a not in block]


def main() -> int:
    print("=" * 64)
    print("L2 词典覆盖测试：真实原话 → 行级「口语别名」反查（v2）")
    print("=" * 64)

    if not GLOSSARY.exists():
        print(f"词典文件缺失：{GLOSSARY}")
        return 1

    rows = parse_alias_rows(GLOSSARY.read_text(encoding="utf-8"))
    glossary_text = GLOSSARY.read_text(encoding="utf-8")
    if not rows:
        print("词典中未解析到任何「口语别名」行，解析器失效")
        return 1

    print(f"词典可反查行：{len(rows)} 行")
    print("判定：只比「口语别名」列；效果/特征/适配脸型列不参与匹配\n")

    # ── 长度锚点资源（追问话术与长发场景的落点）──
    missing_anchors = check_length_anchors(glossary_text)
    if missing_anchors:
        print(f"【长度锚点】✗ 缺失 {missing_anchors}——追问给不出具体位置，长发无处落地")
    else:
        print("【长度锚点】✓ 9 个锚点齐全（含肩线/胸线/腰线三个长发锚点）\n")

    # ── 判据自检（先证明尺子本身是准的）──
    judge_problems = self_check(rows)
    if judge_problems:
        print("【判据自检】✗ 判据不可信，后续结果无意义")
        for p in judge_problems:
            print(f"  · {p}")
        print("\n结果：不通过（判据自检失败）")
        return 1
    print(f"【判据自检】✓ {len(SELF_CHECK)} 组反向用例均正确判红，判据可信\n")

    positives = [c for c in TEST_CASES if c.kind == "term"]
    negatives = [c for c in TEST_CASES if c.kind == "unmapped"]
    failures: list[str] = []

    print(f"【正样本 {len(positives)} 条】用户指明了维度与类型，必须反查到术语")
    for case in positives:
        terms = dedupe_terms(match_rows(case.utterance, rows))
        matched = [t for t in terms if any(term_matches(e, t) for e in case.expect)]
        ok = bool(matched)
        mark = "✓" if ok else "✗"
        if ok:
            print(f"  {mark} 「{case.utterance}」→ {matched[0]}")
        else:
            print(f"  {mark} 「{case.utterance}」期望 {case.expect}，实得 {terms or '无命中'}")
            failures.append(
                f"[缺口] 「{case.utterance}」期望 {case.expect}，实得 {terms or '无命中'}"
                f"（{case.reason}）"
            )

    print(f"\n【负样本 {len(negatives)} 条】只说效果/只说维度/只是发质信息，必须零命中")
    for case in negatives:
        terms = dedupe_terms(match_rows(case.utterance, rows))
        ok = not terms
        mark = "✓" if ok else "✗"
        if ok:
            print(f"  {mark} 「{case.utterance}」→ 零命中（正确转追问）")
        else:
            print(f"  {mark} 「{case.utterance}」→ 误命中 {terms}（越界：应转追问）")
            failures.append(
                f"[越界] 「{case.utterance}」误命中 {terms}（{case.reason}）"
            )

    total = len(TEST_CASES)
    passed = total - len(failures)
    print(f"\n用例：{total}    通过：{passed}    失败：{len(failures)}")

    if failures:
        print("\n失败明细：")
        for f in failures:
            print(f"  · {f}")
        print("\n结果：不通过")
        return 1

    print("\n结果：全部通过 ✓")
    print("提示：L2 通过只证明「原话能反查到正确术语」，不证明翻译质量，仍需 L3。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
