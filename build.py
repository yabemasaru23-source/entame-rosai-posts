# -*- coding: utf-8 -*-
"""芸能労災 投稿デスク — output/ の成果物から、コピペ用の一覧サイトを組み立てる。

使い方（毎日これ1本）:
    python 投稿サイト/build.py

やっていること:
    1. output/YYYY-MM-DD/ の直近10日分を読む（X・X個人・Instagram）
    2. 本文だけを抜き出す（検証メモは載せない）
    3. tools/rules.py で禁止語・絵文字を機械チェックし、結果をカードに出す
    4. 画像を 投稿サイト/assets/ にコピーする
    5. template.html に流し込んで 投稿サイト/index.html を書き出す

出したあと:
    git add -A && git commit && git push  →  GitHub Pages に反映される

方針:
    - **このサイトから投稿はできない。** コピペ用の台。公開ボタンは人間が押す
    - 検証メモ・型・候補番号などの内部ラベルは載せない
      （memory/feedback_no_internal_labels.md）
"""
import json
import os
import re
import shutil
import sys
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUTPUT = os.path.join(ROOT, "output")
ASSETS = os.path.join(HERE, "assets")

sys.path.insert(0, ROOT)
from tools import rules  # noqa: E402

DAYS = 10
# 先の日付のぶんも載せる（2026-09-22 追加）。
# 本人の依頼「今日中に次の10本を作る」で、まとめ書きした先の日付の案が
# 当日になるまでデスクに出ない作りだった。予定日つきで前倒しに出す。
AHEAD = 14

# 本文の終わりを示す行（ここから下は検証メモなので載せない）
SEP = re.compile(r"^[─-╿\-=_\*ー]{6,}$")
META_HEAD = re.compile(r"^(【|##\s|#\s|■\s|★)")

MEDIA = [
    # (キー, 表示名, ファイル名, 台帳の媒体欄, 画像フォルダ, ALTファイル, 投稿アカウント)
    ("x", "X（@entame_rosai）", "x_post.txt", "X", "x_image", "x_image_alt.txt",
     "@entame_rosai"),
    ("yabe", "X（@yabemasaru23）", "x_post_yabemasaru23.txt", "X（@yabemasaru23）",
     "x_image_yabemasaru23", "x_image_yabemasaru23_alt.txt", "@yabemasaru23"),
    ("ig", "Instagram（@entame_rosai）", "instagram_post.md", "Instagram",
     "instagram", "instagram_alt_text.txt", "@entame_rosai"),
]

WEEK = "月火水木金土日"


def read_text(path):
    if not os.path.exists(path):
        return ""
    with open(path, encoding="utf-8") as f:
        return f.read()


def body_of_txt(text):
    """.txt の先頭から、区切り行または見出し行の手前までを本文とする。

    成果物ファイルは本文をいちばん上に書く決まり（SKILL.md 8-1）。
    ここでその決まりに乗っている。前書きが付いていたら本文と誤認するので、
    書き出したあと必ずサイト上で目で見て確認すること。
    """
    out = []
    for line in text.split("\n"):
        s = line.strip()
        if SEP.match(s) or META_HEAD.match(s):
            break
        out.append(line)
    return "\n".join(out).strip()


def body_of_instagram(text):
    """instagram_post.md から、貼り付ける対象のキャプションだけを取り出す。"""
    lines = text.split("\n")
    start = None
    for i, line in enumerate(lines):
        if line.startswith("#") and "キャプション" in line:
            start = i + 1
            break
    if start is None:
        return ""
    out = []
    for line in lines[start:]:
        s = line.strip()
        if s.startswith("## ") or SEP.match(s):
            break
        out.append(line)
    return "\n".join(out).strip()


REPLY_OPEN = re.compile(r"^-{2,}\s*返信案.*?-{2,}\s*$")
REPLY_CLOSE = re.compile(r"^-{2,}\s*ここまで\s*-{2,}\s*$")
REPLY_URL = re.compile(r"投稿URL[：:]\s*(https?://\S+)")
REPLY_HEAD = re.compile(r"^候補\d+.*?(@[A-Za-z0-9_]+)")


def reply_items(folder, date):
    """x_reply_candidates.txt から、送れる形の返信案だけを取り出す。

    返信はいいねの10倍の重みがあり、フォロワー数に依存せず相手のフォロワーに届く
    唯一の外部露出経路（SKILL.md 第6章）。**それがデスクに1件も出ていなかった。**
    案は毎日作られているのに、作業者の画面には X と Instagram しか並んでおらず、
    09-03 以降ほぼ全件が「生成済・未送信」のまま台帳に積み上がっていた。

    本文は `--- 返信案（…） ---` と `--- ここまで ---` にはさまれた部分だけを取る。
    その手前にある「投稿URL：」が返信先。どちらも無い塊は候補として出さない
    （返信先の分からない本文を出すと、貼る先を人間に探させることになる）。
    """
    raw = read_text(os.path.join(folder, "x_reply_candidates.txt"))
    if not raw.strip():
        return []
    lines = raw.split("\n")
    out = []
    i = 0
    while i < len(lines):
        if not REPLY_OPEN.match(lines[i].strip()):
            i += 1
            continue
        body = []
        j = i + 1
        while j < len(lines) and not REPLY_CLOSE.match(lines[j].strip()):
            body.append(lines[j])
            j += 1
        text = "\n".join(body).strip()
        # 直前までさかのぼって、返信先のURLと相手のアカウント名を拾う
        target, who = "", ""
        for k in range(i - 1, -1, -1):
            if not target:
                m = REPLY_URL.search(lines[k])
                if m:
                    target = m.group(1)
            m2 = REPLY_HEAD.match(lines[k].strip())
            if m2:
                who = m2.group(1)
                break
        if text and target:
            out.append({
                "key": "reply%d" % (len(out) + 1),
                "date": date,
                "label": "X 返信%s（@entame_rosai）" % ("・" + who if who else ""),
                "account": "@entame_rosai",
                "text": text,
                "chars": len(text.replace("\n", "")),
                "lines": len(text.split("\n")),
                "hashtags": len(re.findall(r"#[^\s#]+", text)),
                "limit": 140,
                "status": "（返信。台帳は「X（返信）」の行）",
                "url": "",
                "replyTo": target,
                "images": [],
                "alt": "",
                "check": check(text),
            })
        i = j + 1
    return out


def ledger():
    """posting_log.md の表から、日付×媒体ごとの状態と投稿URLを拾う。

    列は | 日付 | 媒体 | 内容 | 状態 | URL | 備考 | の6列で固定。
    内容欄が長いので、状態とURLだけを見る。
    """
    path = os.path.join(OUTPUT, "posting_log.md")
    found = {}
    for line in read_text(path).split("\n"):
        if not line.startswith("|"):
            continue
        f = line.rstrip().split("|")
        if len(f) < 7:
            continue
        date = f[1].replace("*", "").strip()
        if not re.fullmatch(r"\d{2}-\d{2}", date):
            continue
        media = f[2].replace("*", "").strip()
        status = f[4].replace("*", "").strip()
        url = f[5].strip()
        m = re.search(r"https?://\S+", url)
        found[(date, media)] = {
            "status": status,
            "url": m.group(0) if m else "",
        }
    return found


def copy_images(date, folder):
    """画像を assets/ に写して、サイトから開けるようにする。"""
    src = os.path.join(OUTPUT, date, folder)
    if not os.path.isdir(src):
        return []
    names = sorted(n for n in os.listdir(src) if n.lower().endswith((".png", ".jpg", ".jpeg")))
    if not names:
        return []
    dst = os.path.join(ASSETS, date, folder)
    os.makedirs(dst, exist_ok=True)
    out = []
    for n in names:
        shutil.copyfile(os.path.join(src, n), os.path.join(dst, n))
        out.append({"name": n, "path": "assets/%s/%s/%s" % (date, folder, n)})
    return out


def check(text):
    """禁止語・絵文字・ハッシュタグ・リンクを機械で見る。

    正典は memory/feedback_compliance.md、その機械可読版が tools/rules.py。
    ここは rules.py を呼ぶだけで、独自のリストを持たない（持つとずれる）。
    """
    errors, warns = rules.scan(text)
    emoji = rules.emoji_in(text)
    if emoji:
        errors.append("絵文字: " + "".join(emoji))
    for label in rules.INTERNAL_LABELS:
        if label in text:
            errors.append("内部ラベルが本文に混ざっている: " + label)
    return {"errors": errors, "warns": warns}


def collect():
    days = []
    led = ledger()
    today = datetime.now().date()
    offsets = list(range(-AHEAD, 0)) + list(range(DAYS))  # 先の日付 → 今日 → 過去
    offsets.sort()                                        # 未来が上、過去が下
    for i in offsets:
        d = today - timedelta(days=i)
        date = d.strftime("%Y-%m-%d")
        folder = os.path.join(OUTPUT, date)
        if not os.path.isdir(folder):
            continue
        items = []
        for key, label, fname, ledger_media, imgdir, altfile, account in MEDIA:
            raw = read_text(os.path.join(folder, fname))
            if not raw.strip():
                continue
            text = body_of_instagram(raw) if key == "ig" else body_of_txt(raw)
            if not text:
                continue
            rec = led.get((d.strftime("%m-%d"), ledger_media), {})
            hashtags = re.findall(r"#[^\s#]+", text)
            items.append({
                "key": key,
                "date": date,          # 端末に残す投稿記録の鍵（date/key）に使う
                "label": label,
                "account": account,    # 投稿画面を開くボタンのすぐ下に出す
                "text": text,
                "chars": len(text.replace("\n", "")),
                "lines": len(text.split("\n")),
                "hashtags": len(hashtags),
                "limit": 140 if key == "x" else 0,
                "status": rec.get("status", "（台帳に記載なし）"),
                "url": rec.get("url", ""),
                "images": copy_images(date, imgdir),
                "alt": read_text(os.path.join(folder, altfile)).strip(),
                "check": check(text),
            })
        items.extend(reply_items(folder, date))
        if items:
            days.append({
                "date": date,
                "label": "%d月%d日（%s）%s" % (
                    d.month, d.day, WEEK[d.weekday()],
                    "　投稿予定日" if d > today else ""),
                "items": items,
            })
    return days


def main():
    if os.path.isdir(ASSETS):
        shutil.rmtree(ASSETS)          # 10日から外れた画像を置き去りにしない
    days = collect()
    if not days:
        print("output/ に直近%d日分が見つかりません。" % DAYS)
        sys.exit(1)

    conf = {}
    conf_path = os.path.join(HERE, "config.json")
    if os.path.exists(conf_path):
        conf = json.loads(read_text(conf_path))

    data = {
        "account": "@entame_rosai",
        "days": days,
        "builtAt": datetime.now().strftime("%Y-%m-%d %H:%M"),
        # 空なら、保存はその端末のブラウザにだけ残る（共有されない）
        "endpoint": conf.get("endpoint", ""),
    }
    blob = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    tpl = read_text(os.path.join(HERE, "template.html"))
    out = tpl.replace("__DATA__", blob)
    dest = os.path.join(HERE, "index.html")
    with open(dest, "w", encoding="utf-8") as f:
        f.write(out)

    ng = sum(len(i["check"]["errors"]) for d in days for i in d["items"])
    print("組み立てました:", dest)
    print("  日数 %d日 ／ 投稿 %d件 ／ %d KB"
          % (len(days), sum(len(d["items"]) for d in days), len(out.encode("utf-8")) // 1024))
    if ng:
        print("  ★ 機械チェックのNGが %d件あります。サイト上で赤く出ています" % ng)
    else:
        print("  機械チェックのNGは0件")
    if data["endpoint"]:
        print("  投稿記録の共有：あり（スプレッドシートに集まります）")
    else:
        print("  ★ 投稿記録の共有：なし。config.json の endpoint が空です")
        print("     （gas/設置手順.md の手順6の /exec のURLを入れると共有されます）")
    print("次に: git add -A && git commit -m '投稿デスク更新' && git push")


if __name__ == "__main__":
    main()
