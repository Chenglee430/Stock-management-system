<?php
require_once __DIR__.'/config.php';

// DB 可能未建；失敗也不要中斷
$pdo = null; try{ $pdo = db(); }catch(Exception $e){ $pdo=null; }

$action = $_GET['action'] ?? '';
$BODY = json_decode(file_get_contents('php://input'), true) ?: [];

function rows_to_history($rows){
  $out=[]; foreach($rows as $r){
    $out[]=[
      'date'=>$r['date'],
      'open'=>is_null($r['open'])?null:(float)$r['open'],
      'high'=>is_null($r['high'])?null:(float)$r['high'],
      'low' =>is_null($r['low']) ?null:(float)$r['low'],
      'close'=>is_null($r['close'])?null:(float)$r['close'],
      'volume'=>is_null($r['volume'])?null:(int)$r['volume'],
    ];
  }
  return array_reverse($out); // 新→舊
}

function get_company_info_safe($sym){
  global $PYTHON,$PY_INFO,$pdo;
  if(exec_available()){
    [$ret,$d] = shell_json(escapeshellcmd("$PYTHON \"{$PY_INFO}\" ".escapeshellarg($sym)));
    if(!empty($d) && empty($d['error'])) return $d;
  }
  $d = y_info($sym);
  if(empty($d['error'])) return $d;
  if($pdo){
    $st=$pdo->prepare("SELECT MAX(company_name) AS company_name, MAX(industry) AS industry FROM stock_data WHERE symbol IN (?, REPLACE(?, '.TW',''))");
    $st->execute([$sym,$sym]); $r=$st->fetch();
    return ['symbol'=>$sym,'company_name'=>$r['company_name']??null,'industry'=>$r['industry']??null];
  }
  return ['symbol'=>$sym];
}

// 不強制登入，避免因 session/CORS 造成整站失效
if($action==='health'){ json_out(['ok'=>true,'exec'=>exec_available(),'db'=>$GLOBALS['pdo']?'ok':'unavailable']); }
if($action==='markets'){ json_out(['ok'=>true,'items'=>['TW','US']]); }

if($action==='quote_live'){
  $sym = normalize_symbol($BODY['symbol']??'');
  // 先 Python
  if(exec_available()){
    global $PYTHON,$PY_QUOTE;
    [$ret,$d] = shell_json(escapeshellcmd("$PYTHON \"{$PY_QUOTE}\" ".escapeshellarg($sym)));
    if(!empty($d) && empty($d['error'])) json_out(['ok'=>true]+$d);
  }
  // Yahoo 後備（永不 500）
  $d = y_quote($sym);
  if(empty($d['error'])) json_out(['ok'=>true]+$d);
  json_out(['ok'=>false,'error'=>$d['error']??'quote_failed']); // 200
}

if($action==='info'){
  $sym = normalize_symbol($BODY['symbol']??'');
  $d = get_company_info_safe($sym);
  if(!empty($d['error'])) json_out(['ok'=>false]+$d); // 200
  json_out(['ok'=>true,'info'=>$d]);
}

if($action==='history'){
  $sym = normalize_symbol($BODY['symbol']??''); $limit = max(60,(int)($BODY['limit']??240));
  $rows=[];
  if($pdo){
    try{
      $st=$pdo->prepare("SELECT date,open,high,low,close,volume FROM stock_data WHERE symbol IN (?, REPLACE(?, '.TW','')) ORDER BY date ASC");
      $st->execute([$sym,$sym]); $rows=$st->fetchAll();
      $rows = array_slice($rows, max(0,count($rows)-$limit));
    }catch(Exception $e){ $rows=[]; }
  }
  if(!$rows){
    [$rowsY,$err] = y_history_rows($sym,'10y','1d');
    if(!$err && $rowsY){
      $rows=$rowsY;
      if($pdo){
        $ins=$pdo->prepare("INSERT INTO stock_data(symbol,date,open,high,low,close,volume) VALUES(?,?,?,?,?,?,?)
                            ON DUPLICATE KEY UPDATE open=VALUES(open), high=VALUES(high), low=VALUES(low), close=VALUES(close), volume=VALUES(volume)");
        foreach($rowsY as $r){ $ins->execute([$sym,$r['date'],$r['open'],$r['high'],$r['low'],$r['close'],$r['volume']]); }
      }
    }
  }
  json_out(['ok'=>true,'rows'=>rows_to_history($rows)]);
}

if($action==='update_today'){
  $sym = normalize_symbol($BODY['symbol']??'');
  $success=false; $note='';
  if(exec_available()){
    global $PYTHON,$PY_BACKFILL;
    [$ret,$d] = shell_json(escapeshellcmd("$PYTHON \"{$PY_BACKFILL}\" ".escapeshellarg($sym)));
    $success = !empty($d['success']); $note = $success ? '已更新(Py)':'嘗試更新(Py)';
  }
  if(!$success){
    [$rows,$err] = y_history_rows($sym,'10y','1d');
    if(!$err && $rows){
      if($pdo){
        $ins=$pdo->prepare("INSERT INTO stock_data(symbol,date,open,high,low,close,volume) VALUES(?,?,?,?,?,?,?)
                            ON DUPLICATE KEY UPDATE open=VALUES(open), high=VALUES(high), low=VALUES(low), close=VALUES(close), volume=VALUES(volume)");
        foreach($rows as $r){ $ins->execute([$sym,$r['date'],$r['open'],$r['high'],$r['low'],$r['close'],$r['volume']]); }
      }
      $success=true; $note='已更新(Yahoo)';
    }else{ $note='更新失敗：'.($err?:'unknown'); }
  }
  // 最新一筆（DB 可用則取 DB；否則取剛抓的 rows 末筆）
  $latest=null;
  if($pdo){
    $st=$pdo->prepare("SELECT date,open,high,low,close,volume FROM stock_data WHERE symbol IN (?, REPLACE(?, '.TW','')) ORDER BY date DESC LIMIT 1");
    $st->execute([$sym,$sym]); $latest=$st->fetch();
  }
  if(!$latest){
    [$rows,$err] = y_history_rows($sym,'1y','1d');
    if(!$err && $rows) $latest = end($rows);
  }
  json_out(['ok'=>true,'success'=>$success,'note'=>$note,'latest'=>$latest]);
}

if($action==='predict'){
  $sym = normalize_symbol($BODY['symbol']??'');
  if(exec_available()){
    global $PYTHON,$PY_PREDICT;
    [$ret,$d] = shell_json("$PYTHON \"{$PY_PREDICT}\" ".escapeshellarg($sym).' '.escapeshellarg(''));
    if(!empty($d['success'])){
      json_out(['ok'=>true,'method'=>$d['method'],'last_close'=>$d['last_close'],'last_close_date'=>$d['last_close_date'],'pred_close'=>$d['next_close_pred'],'proxy_used'=>$d['proxy_used']??null]);
    }
  }
  // 後備：線性回歸 60 根（DB / Yahoo）
  $series=[];
  if($pdo){
    try{
      $st=$pdo->prepare("SELECT date, close FROM stock_data WHERE symbol IN (?, REPLACE(?, '.TW','')) ORDER BY date DESC LIMIT 60");
      $st->execute([$sym,$sym]); $rows=$st->fetchAll(); $series=array_reverse($rows);
    }catch(Exception $e){}
  }
  if(!$series){
    [$rows,$err] = y_history_rows($sym,'1y','1d');
    if(!$err && $rows) $series = array_slice($rows,-60);
  }
  if(!$series) json_out(['ok'=>false,'error'=>'no_data_for_prediction']); // 200

  $n=count($series); $sx=$sy=$sxx=$sxy=0.0;
  for($i=1;$i<=$n;$i++){ $x=$i; $y=(float)$series[$i-1]['close']; $sx+=$x; $sy+=$y; $sxx+=$x*$x; $sxy+=$x*$y; }
  $den = ($n*$sxx - $sx*$sx) ?: 1;
  $b = ($n*$sxy - $sx*$sy) / $den; $a = ($sy - $b*$sx) / $n;
  $pred = $a + $b*($n+1);
  json_out(['ok'=>true,'method'=>'PHP_LR(60)','last_close'=>(float)$series[$n-1]['close'],'last_close_date'=>$series[$n-1]['date'],'pred_close'=>round($pred,4)]);
}

// 其餘需要 DB 的功能：若 DB 不可用就回空而不是 500
if($action==='rankings' || $action==='screen' || $action==='portfolio_backtest'){
  if(!$pdo) json_out(['ok'=>false,'error'=>'db_unavailable']);
}

json_out(['ok'=>false,'error'=>'unknown_action']);

// === 預測「隔日收盤價」===
if ($action === 'predict') {
    $input  = json_decode(file_get_contents('php://input'), true);
    $symbol = trim($input['symbol'] ?? '');
    if ($symbol === '') { echo json_encode(['ok'=>false,'error'=>'no_symbol']); exit; }

    $py  = 'python'; 
    $cmd = escapeshellcmd($py) . ' ' .
           escapeshellarg(__DIR__ . DIRECTORY_SEPARATOR . 'stock_predictor.py') . ' ' .
           escapeshellarg($symbol);

    $json = shell_exec($cmd);
    $out  = @json_decode($json, true);

    if (isset($out['success']) && $out['success']) {
        echo json_encode([
          'ok'=>true,
          'method' => $out['method'] ?? 'close_model',
          'last_close' => $out['last_close'] ?? null,
          'last_close_date' => $out['last_close_date'] ?? null,
          'pred_close' => $out['next_close_pred'] ?? null,
          'proxy' => $out['proxy_used'] ?? null,
          'components' => $out['components'] ?? null
        ]);
    } else {
        echo json_encode(['ok'=>false,'error'=>$out['error'] ?? 'predict_failed','raw'=>$json]);
    }
    exit;
}
// == 目標價預測 ==
if ($action === 'predict_target') {
    $input = json_decode(file_get_contents('php://input'), true);
    $symbol  = trim($input['symbol'] ?? '');
    $horizon = intval($input['horizon'] ?? 20);  // 預設 20 交易日

    if ($symbol === '') {
        echo json_encode(['ok'=>false,'error'=>'no_symbol']); exit;
    }

    // Windows XAMPP：請確認 python 在 PATH；必要時改成 python.exe 的絕對路徑
    $py = 'python';
    $script = __DIR__ . DIRECTORY_SEPARATOR . 'stock_target_predictor.py';
    $cmd = escapeshellcmd($py) . ' ' . escapeshellarg($script) . ' ' . escapeshellarg($symbol) . ' ' . escapeshellarg($horizon);

    $json = shell_exec($cmd);
    $out  = @json_decode($json, true);

    if (isset($out['success']) && $out['success']) {
        echo json_encode([
            'ok' => true,
            'method'          => $out['method'] ?? 'target_model',
            'last_close'      => $out['last_close'] ?? null,
            'last_close_date' => $out['last_close_date'] ?? null,
            'horizon_days'    => $out['horizon_days'] ?? $horizon,
            'tech_target'     => $out['tech_target'] ?? null,
            'val_target'      => $out['val_target'] ?? null,
            'suggested_target'=> $out['suggested_target'] ?? null,
            'components'      => $out['components'] ?? null
        ]);
    } else {
        echo json_encode(['ok'=>false,'error'=>$out['error'] ?? 'predict_target_failed','raw'=>$json]);
    }
    exit;
}
