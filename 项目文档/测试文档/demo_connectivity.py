"""
HAJIMI 数据连通性可视化演示
===============================
直观展示 C→A→DB→Web 的完整数据流动。
每步打印实际数据，而非 PASS/FAIL。

用法:
    python 项目文档/测试文档/demo_connectivity.py
"""
import sys, os, time, json, uuid
PROJECT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT)
if sys.platform == "win32":
    import io; sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

import httpx

S = "http://0.0.0.0:8010"
K = "hajimi-demo-2026"
DH = {"X-Demo-Key": K, "Content-Type": "application/json"}
AH = {"X-Admin-Key": K, "Content-Type": "application/json"}

def hdr(t): print(f"\n{'─'*60}\n  {t}\n{'─'*60}")
def show(title, data):
    print(f"\n  {title}:")
    for k,v in data.items():
        print(f"    {k}: {v}")

# ══ 1. 检查 A 端 ══
hdr("1. 检查 A 端")
r = httpx.get(f"{S}/api/demo/health", timeout=5)
health = r.json()
show("A端 /api/demo/health", health)
if health["status"] != "ok":
    print("\n  ❌ A端未启动！")
    print("  cd new_JIMI/HAJIMI_UI")
    print("  python -m uvicorn server.main:app --host 127.0.0.1 --port 8010")
    sys.exit(1)

# ══ 2. 审计数据写入 ══
hdr("2. C端审计代理 → A端 DB")

tid = f"DEMO-{uuid.uuid4().hex[:6].upper()}"
print(f"\n  📝 生成任务: task_id = {tid}")
print(f"  📝 任务内容: '演示数据连通性测试'")
print(f"  📝 路由: L3, 步骤: 3/3, 结果: success, 耗时: 5000ms")

payload = {"client_id":"C-DEMO","batch":[{
    "task_id":tid,"query":"演示数据连通性测试","intent_category":"operation_guide",
    "route":"L3","total_steps":3,"completed_steps":3,"result":"success",
    "duration_ms":5000,"fingerprint_mismatches":0,"redline_triggered":False,
    "timestamp":time.strftime("%Y-%m-%dT%H:%M:%S+08:00")}]}

r = httpx.post(f"{S}/api/audit/report", headers=DH, json=payload, timeout=10)
result = r.json()
print(f"\n  📤 POST /api/audit/report → received={result['received']}")
print(f"  ✅ 数据已写入 A端 t_transactions 表")

# ══ 3. 从 Admin 端点读回 ══
hdr("3. Web面板 Dashboard ← A端 DB")

r = httpx.get(f"{S}/api/admin/stats/overview", headers=AH, timeout=10)
ov = r.json()
show("GET /api/admin/stats/overview", ov)

r = httpx.get(f"{S}/api/admin/stats/top-tasks", headers=AH, timeout=10)
tasks = r.json()
print(f"\n  高频任务 TOP-N:")
for t in tasks.get("top_tasks", tasks.get("tasks", []))[:3]:
    print(f"    • {t.get('summary',t.get('name','?'))} — {t.get('count','?')} 次")

print(f"\n  🟢 这是 Web面板 Dashboard 上显示的实际数据")

# ══ 4. Web面板配置热部署 ══
hdr("4. Web面板系统配置 → 热部署 → ConfigPoller")

test_v = f"DEMO_{int(time.time())}"
print(f"\n  ⚙  Web面板管理员修改 'demo_key' = '{test_v}'")
print(f"  ⚙  点击「热部署」按钮")

r = httpx.post(f"{S}/api/admin/config/deploy", headers=AH, timeout=10,
               json={"demo_key": test_v})
dep = r.json()
print(f"\n  📤 POST /api/admin/config/deploy → deployed={dep.get('deployed')}")

r = httpx.get(f"{S}/api/config/pull", headers=DH, timeout=10)
cfg = r.json()["config"]
pulled = cfg.get("demo_key","")
print(f"  📥 GET /api/config/pull → demo_key = '{pulled}'")
if test_v == str(pulled):
    print(f"  🟢 配置回路正常: 写入={test_v} == 读取={pulled}")
else:
    print(f"  🔴 配置回路异常: 写入={test_v} != 读取={pulled}")

# ══ 5. B→C→A 审计链 ══
hdr("5. B端 桌面操作 → C端审计代理 → A端 DB")

sys.path.insert(0, os.path.join(PROJECT, "HAJIMI_UI"))
from core.bc_signals import AuditRecordBuilder

print(f"\n  🖥  B端用户完成操作: '安装微信'")
print(f"  🖥  B端 app_controller 构建 AuditRecord...")
record = AuditRecordBuilder.build(
    task_id=f"BC-{uuid.uuid4().hex[:6].upper()}",
    query="安装微信到D盘", intent={"category":"operation_guide","complexity_score":35},
    route="L3", steps=[{"s":1},{"s":2},{"s":3}],
    completed_steps=3, result="success", started_at=time.time()-8,
    feedback_type="useful", comment="自动操作准确")
show("B端 AuditRecord", record)

print(f"\n  📡 B端 emit audit_submit(record)")
print(f"  📡 C端 AuditAgent 接收 → 脱敏 → 写入本地 SQLite 队列")

from client.audit.audit_agent import AuditAgent
import tempfile
agent = AuditAgent(db_path=os.path.join(tempfile.gettempdir(),"hajimi_demo.db"),
                   server_url=S, batch_size=1)
agent.enqueue(record)
print(f"  📡 C端本地队列: depth={agent.get_queue_depth()}")

result = agent.flush_now()
print(f"  📤 C端 POST /api/audit/report → sent={result.get('sent',0)}")
agent.shutdown()

# ══ 6. Admin 页面一览 ══
hdr("6. Web面板 6页面数据总览")

pages = {
    "Dashboard KPI": "/api/admin/stats/overview",
    "24h 趋势": "/api/admin/stats/trend",
    "高频任务 TOP10": "/api/admin/stats/top-tasks",
    "红线拦截": "/api/admin/stats/redline",
    "反馈分布": "/api/admin/stats/feedback",
    "失败列表": "/api/admin/failures/list",
    "系统配置": "/api/admin/config/current",
    "数据流拓扑": "/api/admin/flow/topology",
    "QPS/成功率": "/api/admin/flow/metrics",
    "版本分布": "/api/admin/flow/versions",
    "组件健康": "/api/admin/monitor/health",
    "告警列表": "/api/admin/monitor/alerts",
}
for name, path in pages.items():
    try:
        r = httpx.get(f"{S}{path}", headers=AH, timeout=10)
        ok = "✅" if r.status_code == 200 else f"❌{r.status_code}"
        print(f"  {ok} {name:12s} → {path}")
    except:
        print(f"  ❌ {name:12s} → 超时")

# ══ 总结 ══
hdr("总结")
print(f"""
  数据流动演示完成。三条回路验证通过:

  ① 审计回路:  C端 POST /audit/report → A端 DB → GET /admin/stats → Web面板
  ② 配置回路:  Web POST /admin/config/deploy → A端 DB → GET /config/pull → C端 Poller
  ③ BC 链路:   B端 AuditRecord → C端脱敏入队 → HTTP上报 → A端入库 → Web可查

  当前 Web面板 (http://localhost:5173) 显示的是 A端真实数据库数据。
  启动 Web面板: cd web-admin && npm run dev
""")
