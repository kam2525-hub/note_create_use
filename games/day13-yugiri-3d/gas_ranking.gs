/**
 * YUGIRI MASTER 3D — Google スプレッドシート全国ランキング用 Google Apps Script
 *
 * 【セットアップ手順】
 * 1. 新しい Google スプレッドシートを作成
 * 2. メニュー「拡張機能」→「Apps Script」を開く
 * 3. このファイルの中身をすべて貼り付けて保存
 * 4. 右上「デプロイ」→「新しいデプロイ」→ 種類「ウェブアプリ」
 *    - 次のユーザーとして実行: 自分
 *    - アクセスできるユーザー: 全員
 * 5. 発行されたウェブアプリ URL（https://script.google.com/macros/s/.../exec）をコピーし、
 *    games/day13-yugiri-3d/index.html 内の GAS_ENDPOINT に貼り付ける
 */

const SHEET_NAME = 'yugiri_ranking';
const TIER_NAMES = ['初級', '上級', '達人', '鬼', '神域【極】'];
const MAX_ROWS_RETURN = 25;

function getOrCreateSheet_() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  let sheet = ss.getSheetByName(SHEET_NAME);
  if (!sheet) {
    sheet = ss.insertSheet(SHEET_NAME);
  }
  if (sheet.getLastRow() === 0) {
    sheet.appendRow([
      'timestamp',
      'tierIdx',
      'tierName',
      'name',
      'waterLeftMl',
      'noodlesLost',
      'justCount',
      'timeLeft',
      'rank',
      'score'
    ]);
    sheet.setFrozenRows(1);
  }
  return sheet;
}

function sanitizeText_(val, maxLen) {
  let s = String(val == null ? '' : val).trim();
  if (/^[=+\-@]/.test(s)) {
    s = "'" + s;
  }
  return s.slice(0, maxLen) || '名無しの湯切り師';
}

function buildSortedRanking_(sheet, filterTierIdx) {
  const lastRow = sheet.getLastRow();
  if (lastRow <= 1) return [];
  const rows = sheet.getRange(2, 1, lastRow - 1, 10).getValues();
  const list = [];

  for (let i = 0; i < rows.length; i++) {
    const r = rows[i];
    const tierIdx = Number(r[1]);
    if (!Number.isInteger(tierIdx) || tierIdx < 0 || tierIdx >= TIER_NAMES.length) continue;
    if (filterTierIdx !== null && tierIdx !== filterTierIdx) continue;

    const waterLeftMl = Number(r[4]);
    const noodlesLost = Number(r[5]) || 0;
    const justCount = Number(r[6]) || 0;
    const timeLeft = Number(r[7]) || 0;
    const score = Number(r[9]) || 0;
    if (!isFinite(waterLeftMl) || waterLeftMl < 0 || waterLeftMl > 1200) continue;

    list.push({
      timestamp: r[0] instanceof Date ? r[0].toISOString() : String(r[0]),
      tierIdx,
      tierName: String(r[2] || TIER_NAMES[tierIdx]),
      name: String(r[3] || '名無しの湯切り師'),
      waterLeftMl: Math.round(waterLeftMl * 100) / 100,
      noodlesLost: Math.max(0, Math.floor(noodlesLost)),
      justCount: Math.max(0, Math.floor(justCount)),
      timeLeft: Math.round(timeLeft * 100) / 100,
      rank: String(r[8] || ''),
      score: Math.round(score)
    });
  }

  // 順位ルール: 残湯mLが少ない順 -> 麺流出が少ない順 -> 高難度順 -> JUST回数多い順 -> 残り時間多い順
  list.sort((a, b) => {
    if (Math.abs(a.waterLeftMl - b.waterLeftMl) > 0.005) return a.waterLeftMl - b.waterLeftMl;
    if (a.noodlesLost !== b.noodlesLost) return a.noodlesLost - b.noodlesLost;
    if (a.tierIdx !== b.tierIdx) return b.tierIdx - a.tierIdx;
    if (a.justCount !== b.justCount) return b.justCount - a.justCount;
    return b.timeLeft - a.timeLeft;
  });

  return list.slice(0, MAX_ROWS_RETURN);
}

function jsonOut_(obj) {
  return ContentService
    .createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}

function doGet(e) {
  try {
    const p = (e && e.parameter) || {};
    const tierParam = p.tier;
    const filterTier = (tierParam !== undefined && tierParam !== '' && tierParam !== 'all')
      ? Number(tierParam)
      : null;

    const sheet = getOrCreateSheet_();
    const list = buildSortedRanking_(sheet, Number.isInteger(filterTier) ? filterTier : null);
    return jsonOut_({ ok: true, items: list });
  } catch (err) {
    return jsonOut_({ ok: false, error: String(err) });
  }
}

function doPost(e) {
  const lock = LockService.getScriptLock();
  try {
    lock.waitLock(8000);
    const raw = (e && e.postData && e.postData.contents) ? e.postData.contents : '{}';
    const data = JSON.parse(raw);

    const tierIdx = Number(data.tierIdx);
    const waterLeftMl = Number(data.waterLeftMl);
    const noodlesLost = Math.max(0, Math.min(200, Math.floor(Number(data.noodlesLost) || 0)));
    const justCount = Math.max(0, Math.min(99, Math.floor(Number(data.justCount) || 0)));
    const timeLeft = Number(data.timeLeft);
    const score = Math.max(0, Math.min(999999, Math.floor(Number(data.score) || 0)));

    if (!Number.isInteger(tierIdx) || tierIdx < 0 || tierIdx >= TIER_NAMES.length) {
      return jsonOut_({ ok: false, error: 'Invalid tierIdx' });
    }
    if (!isFinite(waterLeftMl) || waterLeftMl < 0 || waterLeftMl > 1100) {
      return jsonOut_({ ok: false, error: 'Invalid waterLeftMl' });
    }
    if (!isFinite(timeLeft) || timeLeft < 0 || timeLeft > 30.0) {
      return jsonOut_({ ok: false, error: 'Invalid timeLeft' });
    }

    const name = sanitizeText_(data.name, 12);
    const rank = sanitizeText_(data.rank, 8);
    const tierName = TIER_NAMES[tierIdx];

    const sheet = getOrCreateSheet_();
    sheet.appendRow([
      new Date(),
      tierIdx,
      tierName,
      name,
      Math.round(waterLeftMl * 100) / 100,
      noodlesLost,
      justCount,
      Math.round(timeLeft * 100) / 100,
      rank,
      score
    ]);

    const top = buildSortedRanking_(sheet, tierIdx);
    return jsonOut_({ ok: true, items: top });
  } catch (err) {
    return jsonOut_({ ok: false, error: String(err) });
  } finally {
    try { lock.releaseLock(); } catch (_) {}
  }
}
