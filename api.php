<?php
// api.php — 修正版（含 history 純 PHP 版）
declare(strict_types=1);
header('Content-Type: application/json; charset=utf-8');
session_start();

// ===== 權限 =====
function need_login() {
    if (empty($_SESSION['user'])) {
        echo json_encode(['ok'=>false, 'error'=>'not_logged_in'], JSON_UNESCAPED_UNICODE);
        exit;
    }
}

// ===== Python 執行 =====
function run_py(string $script, array $args=[]): array {
    $binCandidates = ['py -3', 'py', 'python', 'python3']; // Windows/XAMPP 常見
    $scriptPath = __DIR__ . DIRECTORY_SEPARATOR . $script;

    foreach ($binCandidates as $bin) {
        $cmd = $bin . ' ' . escapeshellarg($scriptPath);
        foreach ($args as $a) $cmd .= ' ' . escapeshellarg((string)$a);
        $cmd .= ' 2>&1';
        $out = [];
        $ret = 0;
        @exec($cmd, $out, $ret);
        if ($ret===0 && !empty($out)) {
            $last = trim(end($out));
            $json = json_decode($last, true);
            if (is_array($json)) return $json;
        }
    }
    return ['error'=>'python_exec_failed','script'=>$script,'args'=>$args,'raw'=>($out ?? [])];
}

function ok($data){ echo json_encode(['ok'=>true]+$data, JSON_UNESCAPED_UNICODE); exit; }
function err($msg,$extra=[]){ echo json_encode(['ok'=>false,'error'=>$msg]+$extra, JSON_UNESCAPED_UNICODE); exit; }

function normalize_symbol($s){
    $x = strtoupper(trim((string)$s));
    if (preg_match('/^\d{4}(\.TW|\.TWO)?$/', $x)) {
        return preg_match('/\.TW|\.TWO$/', $x) ? $x : ($x.'.TW');
    }
    return str_replace('.', '-', $x);
}

// 路由與別名
$action = $_GET['action'] ?? $_POST['action'] ?? '';
$aliases = [
  'quote'=>'quote_live','company'=>'info','update_history'=>'update_today',
  'predict'=>'predict_next','next'=>'predict_next','target'=>'predict_target',
  'signal_suggest'=>'signal','signal_eval'=>'signal','risk_eval'=>'risk',
  'health'=>'diag'
];
if (isset($aliases[$action])) $action = $aliases[$action];

// 0) 健康檢查
if ($action === 'diag') {
    ok(['php'=>'ok','session'=>!empty($_SESSION['user']),'time'=>date('c')]);
}

// 1) 即時報價
if ($action === 'quote_live') {
    need_login();
    $sym = normalize_symbol($_POST['symbol'] ?? $_GET['symbol'] ?? '');
    if (!$sym) err('no_symbol');
    $r = run_py('quote_live.py', [$sym]);
    if (!empty($r['error'])) err('quote_failed',['raw'=>$r]);
    ok(['data'=>$r]);
}

// 2) 公司基本資料
if ($action === 'info') {
    need_login();
    $sym = normalize_symbol($_POST['symbol'] ?? $_GET['symbol'] ?? '');
    if (!$sym) err('no_symbol');
    $r = run_py('company_info.py', [$sym]);
    if (!empty($r['error'])) err('info_failed',['raw'=>$r]);
    ok(['data'=>$r]);
}

// 2.5) 歷史K線（最近400根，升冪）
if ($action === 'history') {
    need_login();
    $sym = normalize_symbol($_POST['symbol'] ?? $_GET['symbol'] ?? '');
    if (!$sym) err('no_symbol');

    try {
        $pdo = new PDO(
            'mysql:host=127.0.0.1;dbname=stock_db;charset=utf8mb4',
            'stockapp','920430',
            [
                PDO::ATTR_ERRMODE=>PDO::ERRMODE_EXCEPTION,
                PDO::ATTR_DEFAULT_FETCH_MODE=>PDO::FETCH_ASSOC,
            ]
        );
        $st = $pdo->prepare(
            "SELECT date, open, high, low, close, volume
             FROM stock_data
             WHERE symbol=? AND close IS NOT NULL
             ORDER BY date DESC
             LIMIT 400"
        );
        $st->execute([$sym]);
        $rows = $st->fetchAll();

        // 轉成升冪
        $rows = array_reverse($rows);

        // 組成前端需要的 ohlc 陣列（純 PHP）
        $ohlc = array_map(function(array $r){
            return [
                'date'   => $r['date'],
                'open'   => isset($r['open'])   ? (float)$r['open']   : null,
                'high'   => isset($r['high'])   ? (float)$r['high']   : null,
                'low'    => isset($r['low'])    ? (float)$r['low']    : null,
                'close'  => isset($r['close'])  ? (float)$r['close']  : null,
                'volume' => isset($r['volume']) ? (int)$r['volume']   : null,
            ];
        }, $rows);

        ok(['data'=>['ohlc'=>$ohlc]]);
    } catch (Throwable $e) {
        err('history_failed', ['msg'=>$e->getMessage()]);
    }
}

// 3) 更新至最新日K
if ($action === 'update_today') {
    need_login();
    $sym = normalize_symbol($_POST['symbol'] ?? $_GET['symbol'] ?? '');
    if (!$sym) err('no_symbol');
    $r = run_py('backfill_one.py', [$sym]);
    if (!empty($r['success'])) ok(['updated'=>$r]);
    err('update_failed', ['raw'=>$r]);
}

// 4) 預測（明日）
if ($action === 'predict_next') {
    need_login();
    $sym = normalize_symbol($_POST['symbol'] ?? $_GET['symbol'] ?? '');
    $proxy = $_POST['proxy'] ?? $_GET['proxy'] ?? '';
    if (!$sym) err('no_symbol');
    $r = run_py('stock_predictor.py', [$sym, $proxy]);
    if (!empty($r['error'])) err('predict_failed',['raw'=>$r]);
    ok(['data'=>$r]);
}

// 5) 目標價
if ($action === 'predict_target') {
    need_login();
    $sym = normalize_symbol($_POST['symbol'] ?? $_GET['symbol'] ?? '');
    $h   = intval($_POST['horizon'] ?? $_GET['horizon'] ?? 40);
    if (!$sym) err('no_symbol');
    $r = run_py('stock_target_predictor.py', [$sym, $h]);
    if (!empty($r['error'])) err('predict_target_failed',['raw'=>$r]);
    ok(['data'=>$r]);
}

// 6) 近日操作建議
if ($action === 'signal') {
    need_login();
    $sym = normalize_symbol($_POST['symbol'] ?? $_GET['symbol'] ?? '');
    if (!$sym) err('no_symbol');
    $r = run_py('trade_signal.py', [$sym]);
    if (!empty($r['error'])) err('signal_failed',['raw'=>$r]);
    ok(['data'=>$r]);
}

// 7) 風險評估
if ($action === 'risk') {
    need_login();
    $sym = normalize_symbol($_POST['symbol'] ?? $_GET['symbol'] ?? '');
    $h   = intval($_POST['horizon'] ?? $_GET['horizon'] ?? 20);
    if (!$sym) err('no_symbol');
    $r = run_py('risk_engine.py', [$sym, $h]);
    if (!empty($r['error'])) err('predict_risk_failed',['raw'=>$r]);
    ok(['data'=>$r]);
}

err('unknown_action');
