<?php
require_once __DIR__ . '/config.php';
require_login();
if (($_SESSION['username']??'')!=='admin@example.com') die('only admin');
if ($_SERVER['REQUEST_METHOD']==='POST'){
  $cmd = escapeshellcmd("$PYTHON \"$PY_SCRAPER\"");
  [$ret,$d] = shell_json($cmd); echo '<pre>'.htmlspecialchars(print_r($d,true)).'</pre>'; exit;
}
?><!doctype html>
<html><head><meta charset="utf-8"><title>Admin</title></head>
<body>z
  <h3>Daily Scraper</h3>
  <form method="post"><button>Run Now</button></form>
</body></html>