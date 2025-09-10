<?php
require_once __DIR__ . '/config.php';
boot_session(); json_headers(); require_login();
$mysqli = db();

$action   = $_GET['action'] ?? '';
$symbol   = strtoupper(trim($_GET['symbol'] ?? ''));
$industry = trim($_GET['industry'] ?? '');

function symClause(){ return "symbol IN (?, REPLACE(?, '.TW',''), CONCAT(REPLACE(?,'.TW',''),'.TWO'))"; }

// --- 將指定 symbol 更新到最新可得收盤（若當日未收盤，會是前一交易日） ---
function ensure_latest($symbol){
  $py = (PHP_OS_FAMILY==='Windows')?'python':'python3';
  // backfill_one.py 會自動使用「今天～往前」策略補滿且寫入 DB（已改為動態日期）
  $cmd = $py.' '.escapeshellarg(__DIR__.'/backfill_one.py').' '.escapeshellarg($symbol);
  @exec($cmd.' 2>&1', $out, $code);
  // 不管結果（首次無資料可能會 fail，但我們仍回 DB 查）
  return [$code, $out];
}

// --- update_today: 手動觸發最新化 ---
if ($action === 'update_today') {
  if ($symbol === '') json_out(['error'=>'缺少 symbol'],400);
  [$code,$out] = ensure_latest($symbol);

  // 回報 DB 最後一天與收盤
  $stmt = $mysqli->prepare("SELECT date, close FROM stock_data WHERE ".symClause()." ORDER BY date DESC LIMIT 1");
  $stmt->bind_param('sss',$symbol,$symbol,$symbol);
  $stmt->execute(); $stmt->bind_result($d,$c);
  if ($stmt->fetch()) {
    json_out(['success'=>true,'last_date'=>$d,'last_close'=>$c,'runner'=>$out]);
  }
  json_out(['error'=>'no_data_after_update','runner'=>$out], 500);
}

// --- info ---
if ($action === 'info') {
  if ($symbol === '') json_out(['error'=>'缺少 symbol'],400);
  ensure_latest($symbol);
  $sql="SELECT company_name, industry, MAX(date) FROM stock_data WHERE ".symClause();
  $stmt=$mysqli->prepare($sql); $stmt->bind_param('sss',$symbol,$symbol,$symbol);
  $stmt->execute(); $stmt->bind_result($name,$ind,$last);
  if ($stmt->fetch()) json_out(['symbol'=>$symbol,'company_name'=>$name,'industry'=>$ind,'last_date'=>$last?:null]);
  json_out(['error'=>'no_data'],404);
}

// --- history（查前先更新）---
if ($action === 'history') {
  if ($symbol === '') json_out(['error'=>'缺少 symbol'],400);
  ensure_latest($symbol);
  $sql="SELECT date, close FROM stock_data WHERE ".symClause()." ORDER BY date";
  $stmt=$mysqli->prepare($sql); $stmt->bind_param('sss',$symbol,$symbol,$symbol);
  $stmt->execute(); $res=$stmt->get_result(); $rows=[];
  while($r=$res->fetch_assoc()) $rows[]=$r;
  if (!$rows) json_out(['error'=>'no_data'],404);
  json_out(['symbol'=>$symbol,'history'=>$rows]);
}

// --- 最高價（查前先更新）---
if ($action === 'highest') {
  if ($symbol === '') json_out(['error'=>'缺少 symbol'],400);
  ensure_latest($symbol);
  $sql="SELECT MAX(close) FROM stock_data WHERE ".symClause();
  $stmt=$mysqli->prepare($sql); $stmt->bind_param('sss',$symbol,$symbol,$symbol);
  $stmt->execute(); $stmt->bind_result($mx);
  if ($stmt->fetch()) json_out(['symbol'=>$symbol,'highest'=>$mx]);
  json_out(['error'=>'no_data'],404);
}

// --- by_industry（此處不強制更新全部，維持原樣）---
if ($action === 'by_industry') {
  if ($industry === '') json_out(['error'=>'缺少 industry'],400);
  $stmt=$mysqli->prepare("SELECT DISTINCT symbol, company_name FROM stock_data WHERE industry LIKE CONCAT('%',?,'%') LIMIT 200");
  $stmt->bind_param('s',$industry); $stmt->execute(); $res=$stmt->get_result(); $rows=[];
  while($r=$res->fetch_assoc()) $rows[]=$r;
  json_out(['industry'=>$industry,'symbols'=>$rows]);
}

// --- 預測（會先更新到最新，回傳明日預測價）---
if ($action === 'predict') {
  if ($symbol === '') json_out(['error'=>'缺少 symbol'],400);
  ensure_latest($symbol);
  $py = (PHP_OS_FAMILY==='Windows')?'python':'python3';
  $cmd = $py.' '.escapeshellarg(__DIR__.'/stock_predictor.py').' '.escapeshellarg($symbol).' lr';
  @exec($cmd.' 2>&1', $out, $code);
  $raw = implode("\n",$out);
  $j = json_decode($raw, true);
  if (is_array($j) && !empty($j['success'])) json_out($j);
  json_out(['error'=>'predict_fail','detail'=>$out],500);
}

// --- 管理工具（保留）---
if ($action === 'admin_audit') {
  $res=$mysqli->query("SELECT symbol, COUNT(*) AS cnt FROM stock_data GROUP BY symbol ORDER BY symbol LIMIT 2000");
  $rows=[]; while($r=$res->fetch_assoc()) $rows[]=$r;
  json_out(['total'=>count($rows),'symbols'=>$rows]);
}
if ($action === 'admin_repair') {
  $mysqli->query("UPDATE stock_data SET symbol=CONCAT(LEFT(symbol,4),'.TW') WHERE LENGTH(symbol)=4 AND symbol REGEXP '^[0-9]{4}$'");
  json_out(['success'=>'ok']);
}

json_out(['error'=>'unknown_action'],400);
