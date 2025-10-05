<?php
// ===== 基本設定 =====
$DB_HOST = 'localhost';
$DB_USER = 'root';
$DB_PASS = '';
$DB_NAME = 'stock_db';
$DB_CHARSET = 'utf8mb4';

// Python（若 exec 可用）
$PYTHON      = 'python';
$BASE_DIR    = __DIR__;
$PY_BACKFILL = $BASE_DIR.'/backfill_one.py';
$PY_PREDICT  = $BASE_DIR.'/stock_predictor.py';
$PY_SCRAPER  = $BASE_DIR.'/stock_scraper.py';
$PY_QUOTE    = $BASE_DIR.'/quote_live.py';
$PY_INFO     = $BASE_DIR.'/company_info.py';

// ===== Session / CORS =====
ini_set('session.cookie_httponly', 1);
ini_set('session.use_only_cookies', 1);
session_name('mysess');
session_start();

function db(){
  global $DB_HOST,$DB_USER,$DB_PASS,$DB_NAME,$DB_CHARSET;
  return new PDO("mysql:host=$DB_HOST;dbname=$DB_NAME;charset=$DB_CHARSET",
    $DB_USER,$DB_PASS,[
      PDO::ATTR_ERRMODE=>PDO::ERRMODE_EXCEPTION,
      PDO::ATTR_DEFAULT_FETCH_MODE=>PDO::FETCH_ASSOC,
    ]);
}
function json_out($arr,$code=200){
  http_response_code($code);
  header('Content-Type: application/json; charset=utf-8');
  header('Cache-Control: no-store');
  header('Access-Control-Allow-Credentials: true');
  if(isset($_SERVER['HTTP_ORIGIN'])) header('Access-Control-Allow-Origin', $_SERVER['HTTP_ORIGIN']);
  echo json_encode($arr, JSON_UNESCAPED_UNICODE);
  exit;
}

// --- Auth helpers ---
function require_login(bool $as_json = false){
  if (empty($_SESSION['uid'])) {
    // 若是 API 或要求 JSON，就回傳 401 JSON；否則導去首頁或中止
    $wants_json = $as_json || (isset($_SERVER['HTTP_ACCEPT']) && stripos($_SERVER['HTTP_ACCEPT'], 'application/json') !== false);
    if ($wants_json) {
      http_response_code(401);
      header('Content-Type: application/json; charset=utf-8');
      echo json_encode(['error' => 'auth_required']);
      exit;
    }
    // 專案是單頁面，可改你要的登入頁
    header('Location: index.html');
    exit;
  }
}

/* 可選：專用的管理者驗證（email 可依需要調整） */
function require_admin(string $email = 'admin@example.com'){
  require_login();
  if (($_SESSION['username'] ?? '') !== $email) {
    http_response_code(403);
    exit('only admin');
  }
}

// ===== 小工具 =====
function ends_with($s,$t){ return $t==='' || substr($s,-strlen($t))===$t; }
function exec_available(){
  $disabled = array_map('trim', explode(',', (string)ini_get('disable_functions')));
  return function_exists('exec') && !in_array('exec',$disabled,true);
}
function shell_json($cmd){
  $out=[];$ret=0; @exec($cmd,$out,$ret);
  $txt = implode("\n",$out);
  $d = json_decode($txt,true);
  return [$ret, $d?:['error'=>$txt?:'exec_failed']];
}

/** 將各種人類輸入轉成 Yahoo 想要的代碼 */
function normalize_symbol($s){
  $x = strtoupper(trim($s));
  // 2330  / 2330TW / 2330-TW / 2330.TW → 2330.TW
  if(preg_match('/^(\d{4})(?:[-\.]?TWO?)?$/',$x,$m)) return $m[1].'.TW';
  if(preg_match('/^(\d+)[-\.]TWO$/',$x,$m)) return $m[1].'.TWO';
  // 若已是 .TW/.TWO，維持 dot
  if(preg_match('/^[A-Z0-9]+\.TWO?$/',$x)) return $x;
  // BRK.B → BRK-B（美股慣例），但避免改到 .TW/.TWO
  if(strpos($x,'.')!==false && !preg_match('/\.TWO?$/',$x)) $x = str_replace('.','-',$x);
  // 假如誤打 2330-TW → 2330.TW
  if(ends_with($x,'-TW')||ends_with($x,'-TWO')) $x = str_replace(['-TW','-TWO'],['.TW','.TWO'],$x);
  return $x;
}

// ===== Yahoo 取數（含 SSL 重試 & 雙主機） =====
function _curl_json($url,$insecure=false){
  $ch = curl_init($url);
  $headers = ['User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36'];
  curl_setopt_array($ch,[
    CURLOPT_RETURNTRANSFER=>true,
    CURLOPT_FOLLOWLOCATION=>true,
    CURLOPT_TIMEOUT=>15,
    CURLOPT_HTTPHEADER=>$headers,
  ]);
  if($insecure){
    curl_setopt($ch, CURLOPT_SSL_VERIFYPEER, false);
    curl_setopt($ch, CURLOPT_SSL_VERIFYHOST, false);
  }
  $res = curl_exec($ch);
  $err = curl_error($ch);
  curl_close($ch);
  if($res===false) return ['_error'=>$err?:'curl_failed'];
  $j = json_decode($res,true);
  return $j ?: ['_error'=>'json_decode_failed'];
}
function http_get_json($url){
  // 先用 cURL（安全），失敗就 cURL 不驗證 → 再失敗用 file_get_contents（不驗證）
  if(function_exists('curl_init')){
    $j = _curl_json($url,false);
    if(!isset($j['_error'])) return $j;
    // SSL 相關才用不驗證重試
    if(stripos($j['_error'],'SSL')!==false || stripos($j['_error'],'certificate')!==false){
      $j2 = _curl_json($url,true);
      if(!isset($j2['_error'])) return $j2;
    }
  }
  $ctx = stream_context_create(['http'=>['method'=>'GET','header'=>"User-Agent: Mozilla/5.0\r\n",'timeout'=>15],
                                'ssl'=>['verify_peer'=>false,'verify_peer_name'=>false]]);
  $res = @file_get_contents($url,false,$ctx);
  if($res===false) return ['_error'=>'http_failed'];
  $j = json_decode($res,true);
  return $j ?: ['_error'=>'json_decode_failed'];
}
function yahoo_json_multi($paths){  // 針對 query1 / query2 做雙主機嘗試
  foreach($paths as $p){
    $j = http_get_json($p);
    if(!isset($j['_error'])) return $j;
  }
  return ['_error'=>'all_endpoints_failed'];
}
function y_quote($sym){
  $base = "symbols=".rawurlencode($sym);
  $j = yahoo_json_multi([
    "https://query1.finance.yahoo.com/v7/finance/quote?$base",
    "https://query2.finance.yahoo.com/v7/finance/quote?$base",
  ]);
  if(isset($j['_error'])) return ['error'=>$j['_error']];
  $r = $j['quoteResponse']['result'][0] ?? [];
  if(!$r) return ['error'=>'no_quote'];
  return [
    'symbol'=>$sym,
    'price'=>$r['regularMarketPrice']??null,
    'volume'=>$r['regularMarketVolume']??null,
    'pct_change'=>$r['regularMarketChangePercent']??null,
    'asof'=>$r['regularMarketTime']??null,
    'last_close'=>$r['regularMarketPreviousClose']??null,
  ];
}
function y_info($sym){
  $q = "modules=price,summaryProfile,defaultKeyStatistics,financialData";
  $j = yahoo_json_multi([
    "https://query1.finance.yahoo.com/v10/finance/quoteSummary/".rawurlencode($sym)."?$q",
    "https://query2.finance.yahoo.com/v10/finance/quoteSummary/".rawurlencode($sym)."?$q",
  ]);
  if(isset($j['_error'])) return ['error'=>$j['_error']];
  $res = $j['quoteSummary']['result'][0] ?? [];
  if(!$res) return ['error'=>'no_info'];
  $price = $res['price'] ?? []; $prof=$res['summaryProfile']??[]; $stat=$res['defaultKeyStatistics']??[]; $fin=$res['financialData']??[];
  $getv = function($a,$k){ return isset($a[$k]['raw']) ? $a[$k]['raw'] : ($a[$k]??null); };
  return [
    'symbol'=>$sym,
    'company_name'=>$price['longName']??($price['shortName']??null),
    'industry'=>$prof['industry']??null,
    'sector'=>$prof['sector']??null,
    'market'=> (ends_with($sym,'.TW')||ends_with($sym,'.TWO'))?'TW':'US',
    'market_cap'=>$getv($price,'marketCap')??$getv($stat,'marketCap')??null,
    'pe'=>$getv($stat,'trailingPE')??$getv($stat,'forwardPE')??null,
    'dividend_yield'=>$getv($stat,'yield')??$getv($fin,'dividendYield')??null,
    'dividend_per_share'=>$getv($stat,'lastDividendValue')??null,
  ];
}
function y_history_rows($sym,$range='10y',$interval='1d'){
  $qs = 'range='.rawurlencode($range).'&interval='.rawurlencode($interval).'&includePrePost=false';
  $j = yahoo_json_multi([
    "https://query1.finance.yahoo.com/v8/finance/chart/".rawurlencode($sym)."?$qs",
    "https://query2.finance.yahoo.com/v8/finance/chart/".rawurlencode($sym)."?$qs",
  ]);
  if(isset($j['_error'])) return [[], $j['_error']];
  $chart = $j['chart']['result'][0] ?? null;
  if(!$chart) return [[], 'no_chart'];
  $ts = $chart['timestamp'] ?? [];
  $ind = $chart['indicators']['quote'][0] ?? [];
  $rows=[];
  for($i=0;$i<count($ts);$i++){
    $d = gmdate('Y-m-d', (int)$ts[$i]);
    $open=$ind['open'][$i]??null; $high=$ind['high'][$i]??null; $low=$ind['low'][$i]??null; $close=$ind['close'][$i]??null; $vol=$ind['volume'][$i]??null;
    if($close===null) continue;
    if($open===null) $open=$close; if($high===null) $high=$close; if($low===null) $low=$close;
    $rows[]=['date'=>$d,'open'=>$open,'high'=>$high,'low'=>$low,'close'=>$close,'volume'=>$vol];
  }
  return [$rows,null];
}
?>
