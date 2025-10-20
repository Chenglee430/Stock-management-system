<?php
// auth.php — 完整覆蓋版
declare(strict_types=1);
session_start();
header('Content-Type: application/json; charset=utf-8');

const DB_HOST = '127.0.0.1';
const DB_USER = 'stockapp';
const DB_PASS = '920430';
const DB_NAME = 'stock_db';

function db() {
    static $pdo=null;
    if ($pdo) return $pdo;
    $dsn = 'mysql:host='.DB_HOST.';dbname='.DB_NAME.';charset=utf8mb4';
    $pdo = new PDO($dsn, DB_USER, DB_PASS, [
        PDO::ATTR_ERRMODE=>PDO::ERRMODE_EXCEPTION,
        PDO::ATTR_DEFAULT_FETCH_MODE=>PDO::FETCH_ASSOC,
    ]);
    return $pdo;
}
function json_ok($obj=[])  { echo json_encode(['ok'=>true]+$obj, JSON_UNESCAPED_UNICODE); exit; }
function json_err($msg)    { echo json_encode(['ok'=>false,'error'=>$msg], JSON_UNESCAPED_UNICODE); exit; }

$action = $_GET['action'] ?? ($_POST['action'] ?? '');

// whoami
if ($action==='whoami' && $_SERVER['REQUEST_METHOD']==='GET') {
    if (!empty($_SESSION['user'])) json_ok(['user'=>$_SESSION['user']]);
    json_ok(['user'=>null]);
}

// register
if ($action==='register' && $_SERVER['REQUEST_METHOD']==='POST') {
    $username = trim($_POST['username'] ?? '');
    $password = trim($_POST['password'] ?? '');
    if (!$username || !preg_match('/^\d{6}$/', $password)) json_err('密碼需為 6 位數字');
    try{
        $pdo = db();
        $s = $pdo->prepare('SELECT id FROM users WHERE username=? LIMIT 1');
        $s->execute([$username]);
        if ($s->fetch()) json_err('帳號已存在');
        $hash = password_hash($password, PASSWORD_BCRYPT);
        $pdo->prepare('INSERT INTO users (username, password) VALUES (?,?)')->execute([$username,$hash]);
        json_ok();
    }catch(Throwable $e){ json_err('register_failed'); }
}

// login
if ($action==='login' && $_SERVER['REQUEST_METHOD']==='POST') {
    $username = trim($_POST['username'] ?? '');
    $password = trim($_POST['password'] ?? '');
    if (!$username || !$password) json_err('need_username_password');
    try{
        $pdo = db();
        $s = $pdo->prepare('SELECT id, username, password FROM users WHERE username=? LIMIT 1');
        $s->execute([$username]);
        $u = $s->fetch();
        if (!$u || !password_verify($password, $u['password'])) {
            $ip = $_SERVER['REMOTE_ADDR'] ?? '';
            $pdo->prepare('INSERT INTO login_attempts (username, ip_address) VALUES (?,?)')->execute([$username,$ip]);
            json_err('帳號或密碼錯誤');
        }
        $_SESSION['user'] = ['id'=>$u['id'],'username'=>$u['username']];
        json_ok(['user'=>$_SESSION['user']]);
    }catch(Throwable $e){ json_err('login_failed'); }
}

// forgot_password
if ($action==='forgot_password' && $_SERVER['REQUEST_METHOD']==='POST') {
    $email = trim($_POST['email'] ?? '');
    if (!$email) json_err('need_email');
    $_SESSION['fp_email'] = $email;
    $_SESSION['fp_code']  = strval(random_int(1000, 9999));
    json_ok(['code'=>$_SESSION['fp_code']]); // 測試環境直接回傳
}

// reset_password
if ($action==='reset_password' && $_SERVER['REQUEST_METHOD']==='POST') {
    $email = trim($_POST['email'] ?? '');
    $code  = trim($_POST['code'] ?? '');
    $newp  = trim($_POST['new_password'] ?? '');
    if (!$email || !$code || !preg_match('/^\d{6}$/', $newp)) json_err('invalid_params');

    if (!isset($_SESSION['fp_email'], $_SESSION['fp_code']) ||
        $_SESSION['fp_email'] !== $email || $_SESSION['fp_code'] !== $code) {
        json_err('驗證碼錯誤或已失效');
    }
    try{
        $pdo = db();
        $hash = password_hash($newp, PASSWORD_BCRYPT);
        $ok = $pdo->prepare('UPDATE users SET password=? WHERE username=?')->execute([$hash,$email]);
        if ($ok) { unset($_SESSION['fp_email'], $_SESSION['fp_code']); json_ok(); }
        json_err('reset_failed');
    }catch(Throwable $e){ json_err('reset_failed'); }
}

// logout
if ($action==='logout' && $_SERVER['REQUEST_METHOD']==='GET') {
    $_SESSION=[]; session_destroy(); json_ok();
}

json_err('unknown_action');
