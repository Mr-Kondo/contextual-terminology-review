#!/usr/bin/env python3
"""日本語Wikipediaの実際の項目から、Ruri検索の採否判断用の課題セットを作る(bench_ruri_adoption.py の --data に渡す)。

目的: 作成者(AI)が正解を決めない、公開された実文章での確認。正解は『項目の構造』から機械的に付く。
  - 用語 = 項目名。語義 = 導入部の第1文。根拠の行 = 導入部の先頭2文
  - verbatim   : 本文(導入部の後)で、項目名をそのまま含む最初の文(20〜140字)
  - variant    : その項目へのリダイレクト名のうち、項目名を含まないもの(辞書順で最大2つ)を『{名}について確認します。』に入れた文。表記ゆれ・略称・英名
  - paraphrase : 本文(導入部の後)で、項目名もリダイレクト名も含まない最初の文(25〜140字)。概念の説明を、名前を出さずに言っている文
  - negative   : 用語集に無い近い分野の項目(NEGATIVE_TITLES)の、本文(無ければ全体)の最初の文(25〜140字)のうち、用語集のどの項目名も含まないもの
  - 分割: 各カテゴリ内で id の順に dev / test を交互に割り当てる(奇数番がtest)
選択の規則(結果を見る前に固定): TERM_TITLES の順に、存在し、本文が400字以上で、導入部の第1文が20字以上(曖昧さ回避ページ等を除く)、導入部の後に文が4つ以上ある最初の MAX_TERMS(150)項目。項目名の括弧書き(例: ……(プログラミング))は用語から除く。

著作権: Wikipediaの本文はCC BY-SA。取得した本文はリポジトリに入れない(出力は --out の先。既定は .work/ で追跡対象外)。
リポジトリに残すのは、このスクリプトと、得点・命中などの数値だけ。出力は ID と数値で、本文を含まない。

  python3 tools/fetch_wiki_bench.py --out .work/wiki-bench.json
  .venv/bin/python tools/bench_ruri_adoption.py --data .work/wiki-bench.json --threshold-rule p95 --models 70m,310m --out docs/evidence/ruri-wiki-bench.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

API = "https://ja.wikipedia.org/w/api.php"
UA = "contextual-terminology-review-benchmark/0.1 (https://github.com/Mr-Kondo/contextual-terminology-review)"
MAX_TERMS = 150

TERM_TITLES = """冪等 キャッシュ ロールバック リファクタリング 回帰テスト デッドロック スループット レイテンシ 可用性 継続的インテグレーション
継続的デリバリー マイクロサービス 仮想化 負荷分散 スケーラビリティ 技術的負債 バージョン管理システム コードレビュー 単体テスト 結合テスト
テスト駆動開発 静的コード解析 カプセル化 ポリモーフィズム 再帰 ガベージコレクション メモリリーク 排他制御 セマフォ REST
SQLインジェクション クロスサイトスクリプティング 多要素認証 公開鍵暗号 ハッシュ関数 電子署名 ファイアウォール VPN ゼロトラスト
ランサムウェア フィッシング 脆弱性 ペネトレーションテスト 暗号化 認証 アクセス制御 バックアップ 冗長性 フェイルオーバー
RAID ストレージ 正規化 インデックス データベース 主キー 外部キー ACID特性 結果整合性 CAP定理 シャーディング
レプリケーション データウェアハウス ETL ビッグデータ データマイニング 機械学習 深層学習 過学習 交差検証 ニューラルネットワーク
自然言語処理 強化学習 教師あり学習 教師なし学習 特徴量 バイアス 混同行列 適合率と再現率 ROC曲線 標準偏差 分散 中央値 平均
相関係数 回帰分析 仮説検定 p値 信頼区間 ベイズ推定 正規分布 大数の法則 中心極限定理 標本 外れ値 サンプリング
アジャイルソフトウェア開発 スクラム ウォーターフォールモデル カンバン プロダクトバックログ スプリント ベロシティ ステークホルダー
マイルストーン ガントチャート クリティカルパス ワークブレークダウンストラクチャ リスクマネジメント 品質管理 品質保証 PDCAサイクル
カイゼン シックスシグマ トヨタ生産方式 ジャストインタイム サプライチェーン在庫管理 在庫 リードタイム ボトルネック
損益計算書 貸借対照表 キャッシュ・フロー計算書 減価償却 粗利益 営業利益 経常利益 売上原価 のれん 自己資本比率
流動比率 ROE ROI 内部収益率 正味現在価値 機会費用 サンクコスト 限界費用 損益分岐点 割引現在価値 レバレッジ
契約 瑕疵担保責任 契約不適合責任 検収 請負 準委任契約 秘密保持契約 サービス・レベル・アグリーメント 知的財産権 著作権
個人情報保護法 コンプライアンス ガバナンス 内部統制 監査 デューデリジェンス ベンチマーキング KPI OKR
バランスト・スコアカード SWOT分析 ペルソナ ユーザーストーリー ユーザビリティ アクセシビリティ ユーザーインターフェース
プロトタイプ ワイヤーフレーム A/Bテスト コンバージョン率 ネットワーク帯域 パケット ルーター ドメインネームシステム
トランスポート層セキュリティ HTTP IPアドレス サブネットマスク ネットワークアドレス変換 帯域幅 タイムアウト
トランザクション処理 ログ SLA 加速度 速度 トルク 公差 精度と確度 有効数字 次元解析 誤差 不確かさ 熱容量 エントロピー""".split()

NEGATIVE_TITLES = """ワードプロセッサ プリンター キーボード マウス (コンピュータ) ディスプレイ スキャナ 名刺 会議 議事録 稟議 出張 福利厚生 オフィス
電話 電子メール ファクシミリ プレゼンテーション 在宅勤務 パーソナルコンピュータ スマートフォン 液晶ディスプレイ 光ディスク USBメモリ
電卓 そろばん 手帳 カレンダー 時計 筆記具 文房具 事務用品 書類 封筒 印鑑 領収書 請求書 見積書 納品書 名簿 履歴書 面接
就職活動 新入社員 研修 昇進 退職 転職 副業 労働組合 有給休暇 残業 通勤 満員電車 フレックスタイム制 社員食堂 自動販売機 コピー機
エレベーター 非常口 防災 避難訓練 消火器 防犯カメラ 入退室管理 受付 来客 接待 名刺交換 挨拶 敬語 謙譲語 手紙 年賀状 暑中見舞い 贈答
お中元 お歳暮 領収 値引き 割引 セール 福袋 ポイントカード クレジットカード 電子マネー 現金 小切手 手形 為替 株式 債券 投資信託
保険 年金 税金 消費税 所得税 確定申告 源泉徴収 給与明細 ボーナス 退職金 住宅ローン 家賃 敷金 礼金 引っ越し 宅配便 郵便""".replace("マウス (コンピュータ)", "マウス_(コンピュータ)").split()


def split_sentences(text: str) -> list:
    out = []
    for para in re.split(r"\n+", re.sub(r"[ \t]+", " ", text)):
        para = para.strip()
        if not para or para.startswith("=="):
            continue
        out += [seg.strip() for seg in re.split(r"(?<=。)", para) if seg.strip()]
    return out


def split_intro_body(extract: str):
    m = re.search(r"\n\n+==", extract)
    intro = extract[:m.start()] if m else extract
    body = extract[m.start():] if m else ""
    return split_sentences(intro), split_sentences(body)


def build_item(title, extract, redirects):
    """1項目から、用語エントリと課題の素(未割付)を作る。条件を満たさなければ None。"""
    intro, body = split_intro_body(extract)
    title = re.sub(r"\s*[（(][^）)]*[）)]$", "", title)               # 『リファクタリング (プログラミング)』→『リファクタリング』
    if len(extract) < 400 or len(body) < 4 or not intro or len(intro[0]) < 20:   # 曖昧さ回避ページなど、語義の無い項目を除く
        return None
    names = [title] + [r for r in redirects if len(r) >= 2]
    sense = intro[0][:160]
    line = "".join(intro[:2])[:300]
    verbatim = next((s for s in body if 20 <= len(s) <= 140 and title in s), None)
    para = next((s for s in body if 25 <= len(s) <= 140 and not any(n in s for n in names) and s != verbatim), None)
    variants = sorted(r for r in redirects if len(r) >= 2 and title not in r and r not in title)[:2]
    return {"title": title, "sense": sense, "line": line, "verbatim": verbatim, "paraphrase": para, "variants": variants}


def build_dataset(items, negatives):
    terms, queries = [], []
    for i, it in enumerate(items, 1):
        tid = f"w{i:03d}"
        terms.append({"id": tid, "term": it["title"], "aliases": [], "sense": it["sense"], "source_id": f"wp-{tid}", "line": it["line"]})
        it["id"] = tid
    titles = [t["term"] for t in terms]

    def add(cat, rows):
        for n, (text, gold) in enumerate(rows, 1):
            queries.append({"id": f"{cat[:3]}{n:03d}", "category": cat, "split": "dev" if n % 2 == 0 else "test", "text": text, "gold": gold})
    add("verbatim", [(it["verbatim"], [it["id"]]) for it in items if it["verbatim"]])
    add("variant", [(f"{v}について確認します。", [it["id"]]) for it in items for v in it["variants"]])
    add("paraphrase", [(it["paraphrase"], [it["id"]]) for it in items if it["paraphrase"]])
    add("negative", [(s, []) for s in negatives if not any(t in s for t in titles)])
    return {"description": "日本語Wikipediaの実際の項目から機械的に作った課題セット(正解は項目名・リダイレクト・本文の構造から付く)。Wikipediaの本文はCC BY-SA。リポジトリには入れない。",
            "terms": terms, "queries": queries}


def api(params):
    url = API + "?" + urllib.parse.urlencode({**params, "format": "json", "formatversion": "2"})
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.loads(r.read().decode("utf-8"))
    time.sleep(0.15)
    return data


def fetch_page(title):
    d = api({"action": "query", "prop": "extracts|redirects", "explaintext": 1, "rdlimit": "max", "rdnamespace": 0, "redirects": 1, "titles": title})
    pages = d.get("query", {}).get("pages", [])
    if not pages or pages[0].get("missing"):
        return None
    p = pages[0]
    return p["title"], p.get("extract", ""), [r["title"] for r in p.get("redirects", [])] + ([title] if title != p["title"] else [])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--max-terms", type=int, default=MAX_TERMS)
    a = ap.parse_args(argv)
    items, seen = [], set()
    for t in TERM_TITLES:
        if len(items) >= a.max_terms:
            break
        page = fetch_page(t)
        if not page or page[0] in seen:
            continue
        item = build_item(page[0], page[1], page[2])
        if item:
            seen.add(page[0])
            items.append(item)
    negatives = []
    for t in NEGATIVE_TITLES:
        page = fetch_page(t.replace("_", " "))
        if page:
            _, body = split_intro_body(page[1])
            sent = next((s for s in body + split_sentences(page[1]) if 25 <= len(s) <= 140), None)
            if sent:
                negatives.append(sent)
    data = build_dataset(items, negatives)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    from collections import Counter
    print(json.dumps({"terms": len(data["terms"]), "queries": dict(Counter(q["category"] for q in data["queries"])), "out": str(a.out)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
