<?php require_once __DIR__ . '/config.php'; boot_session(); require_login(); ?>
<!DOCTYPE html><html lang="zh-Hant"><head>
<meta charset="UTF-8"><title>管理工具</title>
<style>body{font-family:sans-serif} pre{background:#111;color:#eee;padding:8px;border-radius:6px}</style>
</head><body>
<h2>管理工具</h2>
<button onclick="audit()">符號稽核</button>
<button onclick="repair()">修復台股符號</button>
<pre id="out">Ready.</pre>
<script>
const BASE = location.origin + location.pathname.replace(/\/admin\.php$/,'');
async function call(action){
  const r = await fetch(`${BASE}/api.php?action=${action}`, {credentials:'include'});
  return r.json();
}
async function audit(){ out.textContent='Loading...'; out.textContent = JSON.stringify(await call('admin_audit'),null,2); }
async function repair(){ out.textContent='Loading...'; out.textContent = JSON.stringify(await call('admin_repair'),null,2); }
const out = document.getElementById('out');
</script>
</body></html>
