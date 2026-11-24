"""Short word-by-word Chinese glosses shown under each English word in the caption.

The gloss list is aligned with WORD_RE matches over the cue text (the same regex the player uses),
so `cue["gl"][k]` belongs to the player's word `data-k="k"`.
"""
from __future__ import annotations

import re

from .dictionary import Dictionary

WORD_RE = re.compile(r"[A-Za-z][A-Za-z'’-]*")
MAX_LEN = 6

# Function words: the dictionary's first sense is unhelpful for these, so they get hand-picked glosses.
# (word, coarse POS) wins over (word, None).
FUNCTION: dict[tuple[str, str | None], str] = {
    ("the", None): "这", ("a", None): "一个", ("an", None): "一个",
    ("to", "PART"): "", ("to", None): "到", ("of", None): "的", ("and", None): "和", ("or", None): "或",
    ("but", None): "但是", ("in", None): "在…里", ("on", None): "在…上", ("at", None): "在", ("for", None): "为了",
    ("with", None): "和…一起", ("from", None): "从", ("by", None): "通过", ("as", None): "作为", ("about", None): "关于",
    ("into", None): "进入", ("out", None): "出", ("up", None): "向上", ("over", None): "超过", ("than", None): "比",
    ("is", None): "是", ("are", None): "是", ("am", None): "是", ("was", None): "是", ("were", None): "是",
    ("be", None): "是", ("been", None): "是", ("being", None): "是",
    ("i", None): "我", ("you", None): "你", ("he", None): "他", ("she", None): "她", ("it", None): "它",
    ("we", None): "我们", ("they", None): "他们", ("me", None): "我", ("him", None): "他", ("her", None): "她",
    ("us", None): "我们", ("them", None): "他们", ("my", None): "我的", ("your", None): "你的", ("his", None): "他的",
    ("its", None): "它的", ("our", None): "我们的", ("their", None): "他们的", ("myself", None): "我自己",
    ("yourself", None): "你自己", ("this", None): "这", ("these", None): "这些", ("those", None): "那些",
    ("that", "SCONJ"): "", ("that", "PRON"): "那", ("that", None): "那",
    ("do", "AUX"): "", ("does", "AUX"): "", ("did", "AUX"): "", ("do", None): "做", ("does", None): "做", ("did", None): "做",
    ("have", "AUX"): "已", ("has", "AUX"): "已", ("had", "AUX"): "已", ("have", None): "有", ("has", None): "有", ("had", None): "有",
    ("will", None): "将", ("would", None): "会", ("can", None): "能", ("could", None): "能", ("should", None): "应该",
    ("may", None): "可能", ("might", None): "可能", ("must", None): "必须", ("shall", None): "将",
    ("not", None): "不", ("no", None): "没有", ("so", "CCONJ"): "所以", ("so", "SCONJ"): "所以", ("so", None): "这么",
    ("if", None): "如果", ("because", None): "因为", ("when", None): "当…时", ("while", None): "当…时",
    ("what", None): "什么", ("which", None): "哪个", ("who", None): "谁", ("how", None): "怎样", ("why", None): "为什么",
    ("where", None): "哪里", ("there", None): "那里", ("here", None): "这里", ("then", None): "然后", ("now", None): "现在",
    ("very", None): "非常", ("just", None): "只是", ("also", None): "也", ("too", None): "也", ("really", None): "真的",
    ("only", None): "只", ("even", None): "甚至", ("still", None): "仍然", ("all", None): "所有", ("some", None): "一些",
    ("any", None): "任何", ("more", None): "更多", ("most", None): "最", ("much", None): "很多", ("many", None): "许多",
    ("like", "VERB"): "喜欢", ("like", None): "像", ("get", None): "得到", ("got", None): "得到", ("go", None): "去",
    ("going", None): "去", ("know", None): "知道", ("think", None): "认为", ("want", None): "想要", ("make", None): "使",
    ("yes", None): "是", ("yeah", None): "是的", ("okay", None): "好", ("ok", None): "好", ("oh", None): "哦",
    ("um", None): "嗯", ("uh", None): "呃", ("hi", None): "嗨", ("hello", None): "你好", ("thanks", None): "谢谢",
    ("'s", "PART"): "的", ("'s", None): "是", ("'re", None): "是", ("'m", None): "是", ("'ll", None): "将",
    ("'ve", None): "已", ("'d", None): "会", ("n't", None): "不",
}


# Everyday words whose first dictionary sense is rare or misleading ("channel: 海峡", "commute: 交换").
# Keyed by lemma; checked before the dictionary.
COMMON: dict[str, str] = {
    "channel": "频道", "commute": "通勤", "clip": "片段", "suck": "很糟", "great": "很棒的", "improve": "提高",
    "practice": "练习", "practise": "练习", "way": "方法", "kind": "种类", "pretty": "相当", "mean": "意思是",
    "guess": "猜", "cool": "酷", "fine": "好的", "show": "展示", "watch": "看", "check": "查看", "level": "水平",
    "native": "母语的", "fluent": "流利的", "content": "内容", "episode": "一集", "podcast": "播客", "stuff": "东西",
    "thing": "事情", "lot": "很多", "bit": "一点", "sure": "当然", "actually": "其实", "basically": "基本上",
    "literally": "简直", "totally": "完全", "super": "超级", "awesome": "很棒的", "amazing": "惊人的",
    "comment": "评论", "subscribe": "订阅", "link": "链接", "app": "应用", "online": "在线", "website": "网站",
    "recommend": "推荐", "focus": "专注", "learn": "学习", "study": "学习", "speak": "说", "talk": "说话",
    "listen": "听", "word": "单词", "sentence": "句子", "phrase": "短语", "grammar": "语法", "vocabulary": "词汇",
    "accent": "口音", "pronunciation": "发音", "exam": "考试", "test": "测试", "score": "分数", "skill": "技能",
    "tip": "建议", "lesson": "课", "teacher": "老师", "student": "学生", "class": "课", "course": "课程",
    "today": "今天", "video": "视频", "busy": "忙碌的", "person": "人", "people": "人们", "time": "时间",
    "day": "天", "year": "年", "week": "周", "really": "真的", "good": "好的", "bad": "坏的", "big": "大的",
    "small": "小的", "little": "小的", "new": "新的", "old": "旧的", "right": "对的", "wrong": "错的",
    "start": "开始", "finish": "完成", "try": "尝试", "help": "帮助", "need": "需要", "use": "使用",
    "find": "发现", "give": "给", "take": "拿", "come": "来", "see": "看见", "look": "看", "say": "说",
    "tell": "告诉", "ask": "问", "feel": "感觉", "keep": "保持", "let": "让", "put": "放", "work": "工作",
    "life": "生活", "world": "世界", "friend": "朋友", "family": "家人", "home": "家", "book": "书",
    "question": "问题", "answer": "回答", "example": "例子", "reason": "原因", "idea": "想法", "problem": "问题",
    "important": "重要的", "different": "不同的", "easy": "容易的", "hard": "难的", "difficult": "困难的",
    "natural": "自然的", "naturally": "自然地", "slowly": "慢慢地", "quickly": "快速地", "probably": "可能",
    "maybe": "也许", "exercise": "练习", "simple": "简单的", "daily": "每天的", "notice": "注意到",
    "automatically": "自动地", "translate": "翻译", "head": "头脑", "explain": "解释", "opinion": "看法",
    "especially": "尤其", "best": "最好的", "better": "更好的", "favourite": "最喜欢的", "favorite": "最喜欢的",
}


def _first_sense(zh: str) -> str:
    """'vt. 交换；折偿　vi. …' -> '交换' (trimmed to MAX_LEN characters)."""
    line = zh.split("　")[0]
    line = re.sub(r"^[a-z]+\.\s*", "", line)
    sense = re.split(r"[；;,，]", line)[0]
    sense = re.sub(r"[（(][^）)]*[）)]|\[[^\]]*\]|<[^>]*>", "", sense).strip()
    return sense[:MAX_LEN]


def _token_gloss(tok, dic: Dictionary) -> str:
    lower = tok.lower_.replace("’", "'")
    for key in ((lower, tok.pos_), (lower, None)):
        if key in FUNCTION:
            return FUNCTION[key]
    if not tok.is_alpha and not lower.startswith("'"):
        return ""
    lemma = tok.lemma_.lower()
    if lower in COMMON:
        return COMMON[lower]
    info = None
    if tok.tag_ in ("VBN", "JJ") and lower != lemma:  # "bored", "interested" (not "listening": that's the verb)
        adjective = dic.word(lower, "ADJ")
        if adjective and adjective["zh"].startswith("a."):
            info = adjective
    if info is None and lemma in COMMON:
        return COMMON[lemma]
    if info is None:
        info = dic.word(lemma, tok.pos_) or dic.word(lower, tok.pos_)
    if not info or (tok.pos_ == "PROPN" and not info["rank"]):
        return ""  # names and unknown words keep an empty gloss
    return _first_sense(info["zh"])


def word_glosses(doc, dic: Dictionary) -> list[str]:
    """One gloss per WORD_RE match in doc.text.

    A match can span several spaCy tokens ("it's" = it + 's, "don't" = do + n't); their glosses are joined,
    so "it's" reads 它是 and "don't" reads 不.
    """
    out = []
    for m in WORD_RE.finditer(doc.text):
        toks = [t for t in doc if m.start() <= t.idx < m.end()]
        if not toks:  # match starts inside a token
            toks = [t for t in doc if t.idx <= m.start() < t.idx + len(t.text)][:1]
        out.append("".join(_token_gloss(t, dic) for t in toks)[:MAX_LEN])
    return out
