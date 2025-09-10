<?php
// ---------- Database ----------
define('DB_HOST', 'localhost');
define('DB_USER', 'root');
define('DB_PASS', '');
define('DB_NAME', 'stock_db');

// ---------- Session ----------
function boot_session() {
  if (session_status() === PHP_SESSION_ACTIVE) return;

  // 自動推斷專案第一層路徑（/my_project）
  $script = $_SERVER['SCRIPT_NAME'] ?? '/';
  $parts  = explode('/', trim($script, '/'));
  $base   = '/' . ($parts ? $parts[0] : '');

  ini_set('session.use_strict_mode', 1);
  session_name('stk_sess');
  session_set_cookie_params([
    'lifetime' => 0,
    'path'     => $base,  // 若你改到根目錄可改為 '/'
    'secure'   => false,  // 本機 http -> false；上線 https -> true
    'httponly' => true,
    'samesite' => 'Lax'
  ]);
  session_start();
}

function json_headers() {
  header('Content-Type: application/json; charset=UTF-8');
  header('Cache-Control: no-store');
}

function json_out($arr, $code = 200) {
  http_response_code($code);
  echo json_encode($arr, JSON_UNESCAPED_UNICODE);
  exit;
}

function body_json() {
  $raw = file_get_contents('php://input');
  $j = json_decode($raw, true);
  return is_array($j) ? $j : [];
}

function db() {
  static $mysqli;
  if ($mysqli) return $mysqli;
  $mysqli = @new mysqli(DB_HOST, DB_USER, DB_PASS, DB_NAME);
  if ($mysqli->connect_errno) json_out(['error' => 'DB_CONNECT_FAIL'], 500);
  $mysqli->set_charset('utf8mb4');
  return $mysqli;
}

function require_login() {
  if (empty($_SESSION['user'])) json_out(['error' => '未登入'], 401);
}
