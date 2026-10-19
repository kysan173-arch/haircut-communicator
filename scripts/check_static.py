"""L1 静态检查：验证 Skill 结构完整性与范围边界。

判定标准全部为二值条件，机器判，不依赖主观阅读。

用法：
    python check_static.py
退出码 0 = 全通过，1 = 有失败项
"""

import re
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
FAILURES = []
CHECKS_RUN = 0


def check(condition: bool, label: str, detail: str = "") -> None:
    global CHECKS_RUN
    CHECKS_RUN += 1
    if not condition:
        FAILURES.append(f"{label}{'： ' + detail if detail else ''}")


def read(rel: str) -> str:
    path = SKILL_ROOT / rel
    if not path.exists():
        FAILURES.append(f"文件缺失：{rel}")
        return ""
    return path.read_text(encoding="utf-8")


def check_structure() -> None:
    """必需文件与目录结构。"""
    required = [
        "SKILL.md",
        "references/glossary-cutting.md",
        "references/failure-cases.md",
        "assets/haircut-card.md",
        "assets/intake-template.md",
    ]
    for rel in required:
        check((SKILL_ROOT / rel).exists(), f"[结构] 必需文件存在 {rel}")

    check(
        not (SKILL_ROOT / "references/glossary-perm-color.md").exists(),
        "[结构] 烫染词典已移除",
    )


def check_frontmatter() -> None:
    """SKILL.md 元数据完整性与范围声明。"""
    text = read("SKILL.md")
    if not text:
        return

    front = re.match(r"^---\n(.*?)\n---", text, re.S)
    check(front is not None, "[元数据] YAML frontmatter 存在")
    if not front:
        return

    block = front.group(1)
    check(re.search(r"^name:\s*\S+", block, re.M) is not None, "[元数据] name 字段存在")
    check(
        re.search(r"^description:\s*\S+", block, re.M) is not None,
        "[元数据] description 字段存在",
    )

    desc = ""
    m = re.search(r"^description:\s*(.+)$", block, re.M)
    if m:
        desc = m.group(1)
    check(
        "剪发" in desc,
        "[元数据] description 明确声明覆盖剪发",
    )
    check(
        "不涉及烫发" in desc or "不涉及烫染" in desc,
        "[元数据] description 明确排除烫染",
    )
    check(len(desc) > 100, "[元数据] description 长度足够触发判定", f"实际 {len(desc)} 字符")


def check_scope_boundary() -> None:
    """范围边界：主流程文件不得残留烫染内容。"""
    global CHECKS_RUN
    scope_files = [
        "SKILL.md",
        "references/glossary-cutting.md",
        "references/failure-cases.md",
        "assets/haircut-card.md",
    ]

    # 烫染术语实体，出现即视为越界残留（边界声明句除外）
    banned_terms = [
        "锡纸烫", "定位烫", "离子烫", "冷烫", "热烫", "数码烫", "陶瓷烫",
        "羊毛卷", "蛋卷", "手扫染", "挑染", "漂发", "褪色", "色度", "色调号",
        "发膜", "角蛋白",
    ]

    boundary_allow = [
        "不在范围", "不覆盖", "不在本工具", "未做处理", "不追加", "不处理该部分",
        "需单独设计", "超出验证范围", "不给建议", "不做术语翻译", "暂不考虑",
        "只处理剪发", "不给出烫染建议", "若需求是",
    ]

    for rel in scope_files:
        text = read(rel)
        if not text:
            continue
        for term in banned_terms:
            if term not in text:
                continue
            for line in text.splitlines():
                if term in line and not any(kw in line for kw in boundary_allow):
                    FAILURES.append(f"[范围] {rel} 残留烫染术语「{term}」→ {line.strip()[:50]}")
                    break
        CHECKS_RUN += 1


def check_pipeline_rules() -> None:
    """四段流水线与硬底线规则必须在 SKILL.md 中显式存在。"""
    text = read("SKILL.md")
    if not text:
        return

    rules = [
        ("第1 段：意图识别", "[流水线] 第1段存在"),
        ("第 2 段：参数化补全", "[流水线] 第2段存在"),
        ("第 3 段：术语映射", "[流水线] 第3段存在"),
        ("第 4 段：校验与输出", "[流水线] 第4段存在"),
        ("硬底线规则", "[规则] 硬底线规则存在"),
        ("绝不静默猜测长度", "[规则] 长度追问规则存在"),
        ("物理兜底锚点", "[规则] 术语+锚点双输出规则存在"),
        ("范围边界", "[规则] 范围边界声明存在"),
        ("不要默认甩模板", "[规则] 模板使用条件约束存在"),
    ]
    for keyword, label in rules:
        check(keyword in text, label)

    check(
        "长度 / 层次 / 刘海 / 两侧 / 发尾 / 打薄" in text,
        "[规则] 六维模型为纯剪发维度",
    )


def check_card_template() -> None:
    """指令卡模板必须包含硬底线区块与数值要求。"""
    text = read("assets/haircut-card.md")
    if not text:
        return

    required_blocks = ["【长度】", "【层次】", "硬底线", "【打薄】"]
    for block in required_blocks:
        check(block in text, f"[指令卡] 含{block} 区块或要求")

    check(
        "反例" in text or "错误示范" in text,
        "[指令卡] 含正反示例对照",
    )


def check_intake_template() -> None:
    """输入模板必须覆盖四类关键字段。"""
    text = read("assets/intake-template.md")
    if not text:
        return

    fields = ["发质软硬", "发量", "日常打理", "最不能接受"]
    for field in fields:
        check(field in text, f"[输入模板] 覆盖字段 {field}")

    check("模板 A" in text and "模板 B" in text, "[输入模板] 提供精简/完整双版本")
    check(
        "不收脸型" in text or "为什么不收脸型" in text,
        "[输入模板] 说明为何不收脸型",
    )


def check_failure_cases() -> None:
    """反例库必须含真实判例与追问模板。"""
    text = read("references/failure-cases.md")
    if not text:
        return

    check("齐齐哈尔" in text, "[反例库] 含齐齐哈尔判例")
    check("白云区" in text, "[反例库] 含广州白云区判例")
    check("追问模板" in text, "[反例库] 含追问模板")
    check("硬底线" in text, "[反例库] 含底线追问话术")

    ambiguous_modes = re.findall(r"### 模式 ([A-F])", text)
    check(
        len(set(ambiguous_modes)) >= 5,
        "[反例库] 歧义模式覆盖 A-F",
        f"实际 {len(set(ambiguous_modes))} 条",
    )


def check_glossary_coverage() -> None:
    """剪发词典核心术语不得缺失。"""
    text = read("references/glossary-cutting.md")
    if not text:
        return

    core_terms = [
        "高层次", "低层次", "渐变", "Fade", "Undercut", "空气刘海", "八字刘海",
        "内扣", "外翻", "打薄", "Blunt cut", "Air bangs", "Side part",
    ]
    for term in core_terms:
        check(term in text, f"[词典] 含核心术语 {term}")

    check("口语别名" in text, "[词典] 提供口语别名反查列")
    check("物理锚点" in text, "[词典] 提供物理锚点兜底列")


def check_traceability_gate() -> None:
    """溯源闸门：防止 Skill 从翻译器退化成造型师。"""
    skill = read("SKILL.md")
    card = read("assets/haircut-card.md")
    intake = read("assets/intake-template.md")
    glossary = read("references/glossary-cutting.md")
    cases = read("references/failure-cases.md")
    if not (skill and card and intake and glossary and cases):
        return

    # SKILL.md 必须有溯源概念与禁止造型推荐声明
    check("溯源闸门" in skill, "[溯源] SKILL.md 含溯源闸门章节")
    check("回指" in skill, "[溯源] 定义了回指判据")
    check("待确认" in skill, "[溯源] 无溯源项有标注机制")
    check("造型推荐不在范围内" in skill, "[溯源] 明确声明不做造型推荐")
    check("我适合什么发型" in skill, "[溯源] 覆盖「我适合什么发型」的触发处置")

    # 指令卡不得保留「可默认」审美值
    for dim in ["高层次", "空气刘海", "内扣"]:
        pattern = f"可默认{dim}"
        check(
            pattern not in card,
            "[溯源] 指令卡已删除「可默认」审美默认值",
            f"仍存在：{pattern}",
        )
    check(
        "不用默认值填空" in card or "不输出该行" in card,
        "[溯源] 指令卡声明缺失维度不填默认值",
    )

    # 输入模板不得用「推荐/建议」列替用户选
    check(
        "| 发质 | 推荐 | 禁忌 |" not in intake,
        "[溯源] 发质表已改为可行性表述而非推荐",
    )
    check(
        "绝不能反向从打理频率推出" in intake,
        "[溯源] 打理频率表只做拦截不做反向推荐",
    )

    # 词典不得用效果列反推方案
    check("替用户选方案" in glossary, "[溯源] 词典声明不反推方案")

    # 反例库必须有模式 G（效果描述被误读为指令）
    check("### 模式 G" in cases, "[溯源] 反例库含模式 G（效果被误读为剪法）")
    check(
        "不写「建议改中高层次」" in cases,
        "[溯源] 发质约束话术禁止建议式替换",
    )

    # 「不做推荐」声明的触发判据（用例 27 实测暴露：只转追问不声明）
    check("他要一个" in skill and "成品" in skill, "[溯源] 明确「要成品才声明不做推荐」的判据")
    check("剪到下颌线" in glossary, "[溯源] 口径表区分下颌线与下巴尖")


def check_neckline_and_constraint() -> None:
    """后颈收边术语 + 整体约束区块（P0-2 新增结构）。"""
    glossary = read("references/glossary-cutting.md")
    card = read("assets/haircut-card.md")
    skill = read("SKILL.md")
    if not (glossary and card and skill):
        return

    # 词典：后颈收边必须成节，且三种形状齐全
    for term in ["后颈收边", "圆颈线", "Rounded neckline", "方颈线", "Square neckline", "自然颈线"]:
        check(term in glossary, f"[后颈] 词典含 {term}")
    check(
        "收边高度" in glossary,
        "[后颈] 声明收边高度必须量化（只说修圆不说高度会被一路推上去）",
    )

    # 指令卡：整体约束必须是独立区块，不能混进维度行
    check("【整体约束】" in card, "[约束] 指令卡含【整体约束】区块示例")
    check("【后颈】" in card, "[后颈] 指令卡含【后颈】区块示例")
    check(
        "整体约束" in card and "不许塞进长度行" in card,
        "[约束] 卡片填充规则声明整体约束不得塞进长度行",
    )

    # SKILL.md：意图分类与规则必须同时存在，防止只改一处
    check("整体约束类" in skill, "[约束] 意图表含整体约束类")
    check("整体约束**不是第七维**" in skill, "[约束] 声明整体约束不是第七维")
    check("整体约束型原话已转为" in skill, "[约束] 出卡校验清单含整体约束项")
    check(
        "整体约束" in skill and "不要硬塞进长度维" in skill,
        "[约束] 第2段含整体约束处理规则",
    )


def check_followup_and_inference() -> None:
    """追问预算（防连问三遍）+ 模式 H（防两步推理代填）。"""
    skill = read("SKILL.md")
    cases = read("references/failure-cases.md")
    glossary = read("references/glossary-cutting.md")
    if not (skill and cases and glossary):
        return

    # 追问预算：上限、禁第三轮、收口机制、授权默认的区分
    check("追问预算" in skill, "[预算] SKILL.md 含追问预算章节")
    check("最多两轮" in skill, "[预算] 声明整轮最多两轮")
    check("≤3 个问题" in skill and "≤1 个问题" in skill, "[预算] 第1轮≤3、第2轮≤1 均写明")
    check(
        "| 第 3 轮 | **禁止** |" in skill,
        "[预算] 第3轮明文禁止",
    )
    check("追不上" not in skill, "[预算] 无错别字残留")
    check("追问不能替代出卡" in skill, "[预算] 声明追问不替代出卡")
    check("授权默认值 ≠ 静默默认值" in skill, "[预算] 区分授权默认与静默默认")
    check(
        "连续追问三轮以上" in skill,
        "[预算] 失败模式表含「连续追问三轮」",
    )

    # 模式 H：两步推理禁令
    check("### 模式 H" in cases, "[模式H] 反例库含模式 H")
    check("两步推理禁令" in cases, "[模式H] 标题含「两步推理禁令」")
    check(
        "不允许用「效果 → 术语」的两步推理" in cases,
        "[模式H] 禁令措辞明确",
    )
    check(
        "必须是**引用**，不能是**推断**" in cases,
        "[模式H] 判据为「引用非推断」",
    )
    check("「显然」就是两步推理的入口" in cases, "[模式H] 含自检话术（「显然」即入口）")
    check("A-H" in cases, "[模式H] 检索说明覆盖 A-H")
    check(
        "用两步推理代填" in skill,
        "[模式H] SKILL.md 失败模式表含两步推理条目",
    )
    check(
        "没有「效果→术语」的推断行" in skill,
        "[模式H] 出卡校验清单含推断行检查",
    )

    # 长发锚点：长度追问与长发场景的落点
    for anchor in ["肩线", "胸线", "腰线"]:
        check(anchor in glossary, f"[长发] 词典锚点表含 {anchor}")


def check_followup_language() -> None:
    """第十组：追问用语——问句必须落在顾客参照系，卡尺 mm 不得进追问。"""
    skill = read("SKILL.md")
    glossary = read("references/glossary-cutting.md")
    cases = read("references/failure-cases.md")

    # A. 规则本体存在
    check("追问用语规则" in skill, "[追问用语] SKILL.md 含「追问用语规则」小节")
    check("毫米数不进问句" in skill, "[追问用语] 明确禁止毫米数进入追问")
    check("卡尺" in skill, "[追问用语] 说明 mm 是卡尺编号（非剪除量）")
    check("顾客不看数字就能选出来" in skill, "[追问用语] 含可验证性判据")
    check("剪除量" in skill and "位置" in skill, "[追问用语] 区分位置型/卡尺型数字")

    # B. 对外表达规范·状态 A 也受约束（规则清单，不只是第2段）
    state_a_rules = skill.split("状态 A", 1)[-1].split("状态 B", 1)[0] if "状态 A" in skill else ""
    check("mm 数" in state_a_rules or "毫米" in state_a_rules,
          "[追问用语] 状态 A 输出规则含禁用 mm 数的条款")
    check("不出现 mm 数" in state_a_rules or "不出现" in state_a_rules,
          "[追问用语] 状态 A 明确「不出现」术语/数字")

    # C. 词典双参照系表
    check("双参照系" in glossary, "[追问用语] 词典含「双参照系」对照表")
    for column in ["顾客听不懂", "顾客参照系"]:
        check(column in glossary, f"[追问用语] 双参照系表含「{column}」列")

    # D. 单位换算不得回退（1cm ≠ 3mm）
    check("约 3 分" in glossary or "约 3分" in glossary, "[追问用语] 1cm 换算已修正为「约 3 分」")
    check("| 1cm | 约 3mm |" not in glossary, "[追问用语] 未回退到错误的「1cm = 3mm」")

    # E. 反例库里不得残留术语化追问模板
    check("推剪到 3mm" not in cases, "[追问用语] 反例库已移除「推剪到 3mm」坏模板")
    check("卡尺型数字不进问句" in cases, "[追问用语] 反例库模式 A 含数字归属说明")

    # F. 参照系（直观化）：手部度量 / 社会符号 / 现状对比 / 结果优先
    check("参照尺" in glossary, "[追问用语] 词典含「参照尺」小节")
    check("手掌宽" in glossary, "[追问用语] 参照尺含手部度量")
    check("军训头" in glossary, "[追问用语] 参照尺含社会符号（军训头/胡茬）")
    check("现状对比" in glossary, "[追问用语] 参照尺含「现状对比」")
    check("参照系怎么选" in glossary, "[追问用语] 词典含「参照系怎么选」场景表")
    check("能问结果就别问长度" in skill, "[追问用语] 明确「结果优先于长度」")
    check("先定结果，再定位置" in skill, "[追问用语] 明确确认顺序")
    check("让他用手捏" in skill or "用手捏住" in skill, "[追问用语] 含「捏发确认」兜底手段")
    check("最多用两种参照" in glossary, "[追问用语] 限定单次追问的参照系数量")


def check_photo_input() -> None:
    """第十一组：照片输入——只能当验证器，不能当推荐器。"""
    skill = read("SKILL.md")
    glossary = read("references/glossary-cutting.md")
    card = read("assets/haircut-card.md")

    # A. 章节与定位声明
    check("照片输入" in skill, "[照片] SKILL.md 含「照片输入」章节")
    check("验证器" in skill, "[照片] 明确照片是验证器")
    check("照片绝对不可以" in skill, "[照片] 含「不可以做什么」清单")
    check("造型推荐" in skill.split("照片输入", 1)[-1], "[照片] 照片章节内重申不越界造型推荐")

    # B. 触发条件（避免默认索取照片）
    photo_section = skill.split("照片输入", 1)[-1].split("## 追问预算", 1)[0] if "照片输入" in skill else ""
    for trigger in ["后脑形状", "长发大改", "追问两轮"]:
        check(trigger in photo_section, f"[照片] 触发条件含「{trigger}」")
    check("不要照片" in photo_section, "[照片] 明确日常场景不索取照片")
    check("只要必要的那一张" in photo_section, "[照片] 限定只要必要视角，不要求四面全套")

    # C. 输出纪律
    check("用位置，不用数字" in photo_section, "[照片] 读图结果用位置描述")
    check("照片不能替代确认" in photo_section, "[照片] 照片结果必须回用户确认")

    # D. 词典：口径表与视角表
    check("位置词口径表" in glossary, "[照片] 词典含「位置词口径表」")
    check("照片视角能判断什么" in glossary, "[照片] 词典含「照片视角能判断什么」")
    check("唯一不可替代" in glossary, "[照片] 明确后面那张照片不可替代")
    check("不要凭照片给发质方案" in glossary, "[照片] 禁止凭照片定发质方案")

    # E. 指令卡：照片坐标区块
    check("照片坐标" in card, "[照片] 指令卡含「照片坐标」区块")
    check("精确不等于授权" in card, "[照片] 指令卡声明精确≠授权")
    check("锚点由用户指认" in card, "[照片] 标注锚点必须由用户指认，模型不猜像素")
    check("模型不做图像识别" in card, "[照片] 声明模型不做图像识别")


def main() -> int:
    print("=" * 60)
    print("L1 静态检查：结构完整性 / 范围边界 / 规则存在性")
    print("=" * 60)

    checkers = [
        check_structure,
        check_frontmatter,
        check_scope_boundary,
        check_pipeline_rules,
        check_card_template,
        check_intake_template,
        check_failure_cases,
        check_glossary_coverage,
        check_traceability_gate,
        check_neckline_and_constraint,
        check_followup_and_inference,
        check_followup_language,
        check_photo_input,
    ]
    for fn in checkers:
        fn()

    print(f"\n检查项：{CHECKS_RUN}    失败：{len(FAILURES)}")
    if FAILURES:
        print("\n失败明细：")
        for f in FAILURES:
            print(f"  ✗ {f}")
        print("\n结果：不通过")
        return 1
    print("\n结果：全部通过 ✓")
    return 0


if __name__ == "__main__":
    sys.exit(main())