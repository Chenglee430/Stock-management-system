<?php
// auth.php — 專用於 users(username, password, reset_code, reset_expires)
// 只輸出 JSON；任何錯誤都包成 JSON 回前端
declare(strict_types=1);

while (ob_get_level()) { ob_end_clean(); }
header('Content-Type: application/json; charset=utf-8');
ini_set('display_errors', '0');
ini_set('log_errors', '1');
error_reporting(E_ALL);

function json_out(array $a, int $code = 200){ http_response_code($code); echo json_encode($a, JSON_UNESCAPED_UNICODE); exit; }
function json_ok(array $a = []){ json_out(['ok'=>true] + $a); }
function json_err(string $msg, int $code = 400){ json_out(['ok'=>false,'error'=>$msg], $code); }

set_error_handler(function($sev,$msg,$file,$line){ throw new ErrorException($msg,0,$sev,$file,$line); });
set_exception_handler(function($e){ json_err('伺服器錯誤：'.$e->getMessage(), 500); });

// ---------- Session ----------
session_set_cookie_params([
  'lifetime'=>0,'path'=>'/',
  'secure'=>isset($_SERVER['HTTPS']) && $_SERVER['HTTPS']==='on',
  'httponly'=>true,'samesite'=>'Lax',
]);
session_start();

// ---------- DB 參數（請依實際環境調整） ----------
$DB_HOST = '127.0.0.1';
$DB_NAME = 'stock_db';   // ← 你的資料庫名稱
$DB_USER = 'root';       // ← XAMPP 預設
$DB_PASS = '';           // ← XAMPP 預設空字串

try {
  $pdo = new PDO("mysql:host=$DB_HOST;dbname=$DB_NAME;charset=utf8mb4", $DB_USER, $DB_PASS, [
    PDO::ATTR_ERRMODE=>PDO::ERRMODE_EXCEPTION,
    PDO::ATTR_DEFAULT_FETCH_MODE=>PDO::FETCH_ASSOC,
  ]);
} catch (Throwable $e) {
  json_err('DB 連線失敗：'.$e->getMessage(), 500);
}

// ---------- 小工具 ----------
function require_post(): array{
  if (($_SERVER['REQUEST_METHOD'] ?? '') !== 'POST') json_err('必須使用 POST', 405);
  $ct = $_SERVER['CONTENT_TYPE'] ?? '';
  if (stripos($ct,'application/json') !== false){
    $raw = file_get_contents('php://input'); $arr = json_decode($raw,true);
    return is_array($arr) ? $arr : [];
  }
  return $_POST;
}
function is6(string $s): bool { return (bool)preg_match('/^\d{6}$/',$s); }
function is4(string $s): bool { return (bool)preg_match('/^\d{4}$/',$s); }
function is_email(string $s): bool { return filter_var($s, FILTER_VALIDATE_EMAIL) !== false; }
function now(): string { return (new DateTime('now'))->format('Y-m-d H:i:s'); }
function afterMin(int $m): string { $d=new DateTime('now'); $d->modify("+$m minutes"); return $d->format('Y-m-d H:i:s'); }

// ---------- Route ----------
$action = $_GET['action'] ?? $_POST['action'] ?? '';

switch ($action) {
  // 誰已登入
  case 'whoami': {
    if (!empty($_SESSION['user'])) json_ok(['user'=>['username'=>$_SESSION['user']['username']]]);
    echo json_encode(['ok'=>false]); // 給前端判斷是否顯示登入視窗
    exit;
  }

  // 登出
  case 'logout': {
    $_SESSION = [];
    if (ini_get('session.use_cookies')){
      $p = session_get_cookie_params();
      setcookie(session_name(),'',time()-42000,$p['path'],$p['domain']??'',$p['secure']??false,$p['httponly']??true);
    }
    session_destroy();
    json_ok();
  }

  // 註冊（帳號=你輸入的字串；建議填 email。密碼=6 位數字）
  case 'register': {
    $p = require_post();
    $username = trim((string)($p['username'] ?? ''));
    $password = trim((string)($p['password'] ?? ''));
    if ($username === '' || !is6($password)) json_err('帳號或密碼格式不正確（密碼需為6位數字）');

    $stmt = $pdo->prepare("SELECT id FROM users WHERE username=?");
    $stmt->execute([$username]);
    if ($stmt->fetch()) json_err('帳號已存在');

    $hash = password_hash($password, PASSWORD_DEFAULT);
    // 如果帳號看起來是 email，就同時寫入 email 欄位；否則留空
    if (is_email($username)) {
      $stmt = $pdo->prepare("INSERT INTO users (username, email, password, created_at) VALUES (?, ?, ?, NOW())");
      $stmt->execute([$username, $username, $hash]);
    } else {
      $stmt = $pdo->prepare("INSERT INTO users (username, password, created_at) VALUES (?, ?, NOW())");
      $stmt->execute([$username, $hash]);
    }
    json_ok(['message'=>'註冊成功']);
  }

  // 登入（可輸入 username 或 email；密碼 6 位數字）
  case 'login': {
    $p = require_post();
    $acct    = trim((string)($p['username'] ?? '')); // 前端欄位名就是 username
    $password= trim((string)($p['password'] ?? ''));
    if ($acct === '' || !is6($password)) json_err('帳號或密碼格式不正確');

    // 同時支援用 username 或 email 登入
    $stmt = $pdo->prepare("SELECT id, username, password FROM users WHERE username=? OR email=? LIMIT 1");
    $stmt->execute([$acct, $acct]);
    $u = $stmt->fetch();
    if (!$u || !password_verify($password, $u['password'])) json_err('帳號或密碼錯誤');

    $_SESSION['user'] = ['id'=>$u['id'], 'username'=>$u['username']];
    json_ok(['user'=>['username'=>$u['username']]]);
  }

  // 忘記密碼：產生 4 碼驗證碼（測試直接回傳）
  case 'forgot_password': {
    $p = require_post();
    // 你的前端欄位叫 fpEmail，但其實是拿來填帳號（多半是 email）
    $acct = trim((string)($p['email'] ?? $p['username'] ?? ''));
    if ($acct === '') json_err('請輸入帳號');

    $stmt = $pdo->prepare("SELECT id FROM users WHERE username=? OR email=? LIMIT 1");
    $stmt->execute([$acct, $acct]);
    $u = $stmt->fetch();
    if (!$u) json_err('查無此帳號');

    $code = str_pad((string)random_int(0,9999),4,'0',STR_PAD_LEFT);
    $exp  = afterMin(15);
    $stmt = $pdo->prepare("UPDATE users SET reset_code=?, reset_expires=? WHERE id=?");
    $stmt->execute([$code, $exp, $u['id']]);

    json_ok(['message'=>'驗證碼已產生','code'=>$code,'expires'=>$exp]);
  }

  // 重設密碼
  case 'reset_password': {
    $p = require_post();
    $acct = trim((string)($p['email'] ?? $p['username'] ?? ''));
    $code = trim((string)($p['code'] ?? ''));
    $newp = trim((string)($p['new_password'] ?? ''));
    if ($acct==='' || !is4($code) || !is6($newp)) json_err('格式錯誤（帳號 / 4 碼驗證 / 6 碼新密碼）');

    $stmt = $pdo->prepare("SELECT id, reset_code, reset_expires FROM users WHERE username=? OR email=? LIMIT 1");
    $stmt->execute([$acct, $acct]);
    $u = $stmt->fetch();
    if (!$u) json_err('查無此帳號');
    if ($u['reset_code'] !== $code) json_err('驗證碼錯誤');
    if (!$u['reset_expires'] || new DateTime($u['reset_expires']) < new DateTime()) json_err('驗證碼已過期');

    $hash = password_hash($newp, PASSWORD_DEFAULT);
    $pdo->beginTransaction();
    try{
      $stmt = $pdo->prepare("UPDATE users SET password=?, reset_code=NULL, reset_expires=NULL WHERE id=?");
      $stmt->execute([$hash, $u['id']]);
      $pdo->commit();
    }catch(Throwable $e){
      $pdo->rollBack();
      json_err('重設失敗：'.$e->getMessage(), 500);
    }
    json_ok(['message'=>'密碼已更新']);
  }

  default: json_err('未知的 action');
}
