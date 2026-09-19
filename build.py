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
    for i in range(DAYS):
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
        if items:
            days.append({
                "date": date,
                "label": "%d月%d日（%s）" % (d.month, d.day, WEEK[d.weekday()]),
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

    data = {
        "account": "@entame_rosai",
        "days": days,
        "builtAt": datetime.now().strftime("%Y-%m-%d %H:%M"),
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
    print("次に: git add -A && git commit -m '投稿デスク更新' && git push")


if __name__ == "__main__":
    main()
