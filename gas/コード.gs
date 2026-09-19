/**
 * 芸能労災 投稿デスク — 投稿記録の受け口
 *
 * 投稿デスク（GitHub Pages の静的サイト）から送られてくる投稿URLを、
 * このスプレッドシートに1行ずつ書き込む。
 *
 * ・書き込みは追記のみ。消したり書き換えたりはしない
 *   （同じ日・同じ媒体をもう一度送ったときだけ、その行を上書きする）
 * ・URLの形を見て、X と Instagram の投稿URL以外は受け付けない
 * ・1日の受付上限を設けてある（公開URLなので、荒らされても増え続けない）
 *
 * 置きかた・デプロイのしかたは 設置手順.md を参照。
 */

// 書き込み先のスプレッドシート「芸能労災 投稿記録」のID。
// IDで指定しているので、このスクリプトをスプレッドシートから開いても、
// 単独のプロジェクトとして作っても、同じように動く。
var SHEET_ID = '1GgROCjiaK5QKzroyMtErOlnb7PllQqDAClps8GdVM80';

var SHEET_NAME = '投稿記録';
var MAX_PER_DAY = 60;          // 1日にこのシートへ入る行数の上限
var HEADER = ['受付日時', '投稿日', '媒体', '投稿URL', '担当者', '媒体キー'];


function doPost(e) {
  var lock = LockService.getScriptLock();
  try {
    lock.waitLock(10000);
  } catch (err) {
    return reply(e, { ok: false, error: '混み合っています。少し待ってもう一度押してください' });
  }
  try {
    var d = JSON.parse(e.postData.contents);
    var bad = validate(d);
    if (bad) return reply(e, { ok: false, error: bad });

    var sh = sheet();
    var values = sh.getDataRange().getValues();

    if (values.length - 1 >= MAX_PER_DAY * 30) {
      return reply(e, { ok: false, error: '記録が上限に達しました。矢部さんに連絡してください' });
    }
    if (countToday(values) >= MAX_PER_DAY) {
      return reply(e, { ok: false, error: '本日の受付上限に達しました' });
    }

    // 同じ投稿日・同じ媒体があれば、その行を書き換える（貼り直しのため）
    // ※ 投稿日の列はスプレッドシートが日付型に変換するので、必ず ymd() を通して比べる
    var row = -1;
    for (var i = 1; i < values.length; i++) {
      if (ymd(values[i][1]) === d.date && String(values[i][5]) === d.key) { row = i + 1; break; }
    }
    var rec = [new Date(), d.date, cut(d.label, 40), d.url, cut(d.who, 40), d.key];
    if (row > 0) {
      sh.getRange(row, 1, 1, rec.length).setValues([rec]);
    } else {
      sh.appendRow(rec);
    }
    return reply(e, { ok: true });
  } catch (err) {
    return reply(e, { ok: false, error: String(err) });
  } finally {
    lock.releaseLock();
  }
}


function doGet(e) {
  var values = sheet().getDataRange().getValues();
  var rows = [];
  for (var i = 1; i < values.length; i++) {
    var r = values[i];
    if (!r[3]) continue;
    rows.push({
      at: stamp(r[0]), date: ymd(r[1]), label: String(r[2]),
      url: String(r[3]), who: String(r[4]), key: String(r[5])
    });
  }
  return reply(e, { ok: true, rows: rows });
}


/** 静的サイトから読めるように JSONP で返す。callback が無ければ素の JSON。 */
function reply(e, obj) {
  var body = JSON.stringify(obj);
  var cb = e && e.parameter ? e.parameter.callback : null;
  if (cb && /^[A-Za-z_$][A-Za-z0-9_$]*$/.test(cb)) {
    return ContentService.createTextOutput(cb + '(' + body + ');')
      .setMimeType(ContentService.MimeType.JAVASCRIPT);
  }
  return ContentService.createTextOutput(body)
    .setMimeType(ContentService.MimeType.JSON);
}


/** 受け取ってよい形かを見る。ここを通らないものは1行も書かない。 */
function validate(d) {
  if (!d || typeof d !== 'object') return '中身が読めませんでした';
  if (!/^\d{4}-\d{2}-\d{2}$/.test(String(d.date))) return '投稿日の形が違います';
  if (['x', 'yabe', 'ig'].indexOf(String(d.key)) < 0) return '媒体が違います';
  var url = String(d.url || '');
  if (url.length > 300) return 'URLが長すぎます';
  if (d.key === 'ig') {
    if (!/^https:\/\/(www\.)?instagram\.com\/[\w\-./?=&]+$/.test(url)) {
      return 'Instagram の投稿URLではありません';
    }
  } else {
    if (!/^https:\/\/(www\.)?(x|twitter)\.com\/[A-Za-z0-9_]+\/status\/\d+/.test(url)) {
      return 'X の投稿URLではありません';
    }
  }
  return '';
}


function sheet() {
  var ss = SpreadsheetApp.openById(SHEET_ID);
  var sh = ss.getSheetByName(SHEET_NAME);
  if (!sh) {
    sh = ss.insertSheet(SHEET_NAME);
  }
  if (sh.getLastRow() === 0) {
    sh.appendRow(HEADER);
    sh.getRange(1, 1, 1, HEADER.length).setFontWeight('bold');
    sh.setFrozenRows(1);
    sh.setColumnWidth(4, 420);
  }
  return sh;
}


function countToday(values) {
  var t = Utilities.formatDate(new Date(), 'Asia/Tokyo', 'yyyy-MM-dd');
  var n = 0;
  for (var i = 1; i < values.length; i++) {
    if (values[i][0] instanceof Date &&
        Utilities.formatDate(values[i][0], 'Asia/Tokyo', 'yyyy-MM-dd') === t) n++;
  }
  return n;
}


/** 投稿日を必ず 2026-09-19 の形で返す。
 *  スプレッドシートは '2026-09-19' という文字列を日付型に変換してしまい、
 *  そのまま読むと 'Thu Sep 19 2026 ...' になる。サイト側と突き合わない。 */
function ymd(v) {
  if (v instanceof Date) return Utilities.formatDate(v, 'Asia/Tokyo', 'yyyy-MM-dd');
  return String(v);
}


function stamp(v) {
  if (v instanceof Date) return Utilities.formatDate(v, 'Asia/Tokyo', 'yyyy-MM-dd HH:mm');
  return String(v);
}


function cut(s, n) {
  s = String(s == null ? '' : s);
  return s.length > n ? s.slice(0, n) : s;
}


/** デプロイ前の動作確認用。エディタでこれを実行すると、見出し行が作られる。 */
function 準備() {
  var sh = sheet();
  Logger.log('準備できました。シート「' + sh.getName() + '」の '
    + sh.getLastRow() + '行目まで入っています。');
}
