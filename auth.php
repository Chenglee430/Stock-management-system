<?php
require_once __DIR__ . '/config.php';
boot_session();
json_headers();
$mysqli = db();

$action = $_GET['action'] ?? '';
$B = body_json();

if ($action === 'register') {
  $u = trim($B['username'] ?? ''); $p = (string)($B['password'] ?? '');
  if ($u === '' || $p === '') json_out(['error'=>'缺少帳號或密碼'], 400);

  $stmt = $mysqli->prepare("SELECT id FROM users WHERE username=?");
  $stmt->bind_param('s', $u); $stmt->execute(); $stmt->store_result();
  if ($stmt->num_rows > 0) json_out(['error'=>'帳號已存在'], 409);
  $stmt->close();

  $hash = password_hash($p, PASSWORD_DEFAULT);
  $stmt = $mysqli->prepare("INSERT INTO users (username,password) VALUES (?,?)");
  $stmt->bind_param('ss', $u, $hash);
  if ($stmt->execute()) json_out(['success'=>'註冊成功']);
  json_out(['error'=>'REGISTER_FAIL'], 500);
}

if ($action === 'login') {
  $u = trim($B['username'] ?? ''); $p = (string)($B['password'] ?? '');
  if ($u === '' || $p === '') json_out(['error'=>'缺少帳號或密碼'], 400);

  $stmt = $mysqli->prepare("SELECT id,password FROM users WHERE username=?");
  $stmt->bind_param('s', $u); $stmt->execute(); $stmt->bind_result($uid, $hash);
  if ($stmt->fetch() && password_verify($p, $hash)) {
    $_SESSION['user'] = ['id'=>$uid,'name'=>$u];
    json_out(['success'=>'登入成功']);
  }
  json_out(['error'=>'帳號或密碼錯誤'], 403);
}

if ($action === 'forgot') {
  $u = trim($B['username'] ?? '');
  if ($u === '') json_out(['error'=>'缺少帳號'], 400);
  $tmp  = substr(str_shuffle('ABCDEFGHJKLMNPQRSTUVWXYZ23456789'), 0, 8);
  $hash = password_hash($tmp, PASSWORD_DEFAULT);
  $stmt = $mysqli->prepare("UPDATE users SET password=? WHERE username=?");
  $stmt->bind_param('ss', $hash, $u); $stmt->execute();
  if ($stmt->affected_rows > 0) json_out(['success'=>'已重設','temp_password'=>$tmp]);
  json_out(['error'=>'帳號不存在'], 404);
}

if ($action === 'logout') {
  $_SESSION = [];
  if (ini_get('session.use_cookies')) {
    $p = session_get_cookie_params();
    setcookie(session_name(), '', time()-42000, $p['path'], $p['domain'] ?? '', $p['secure'], $p['httponly']);
  }
  session_destroy();
  json_out(['success'=>'已登出']);
}

json_out(['error'=>'unknown_action'], 400);
