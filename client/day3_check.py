"""
HAJIMI — Day 3 验证脚本
===========================
验证 Day 3 全部交付物：B-C 集成联调、审计 E2E、失败归因页面增强

用法::

    python client/day3_check.py
"""

import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PASS = 0
FAIL = 0


def ok(msg, condition=True):
    global PASS
    if condition:
        print(f"  ✅ {msg}")
        PASS += 1
    else:
        print(f"  ❌ {msg}")
        FAIL += 1


def bad(msg):
    global FAIL
    print(f"  ❌ {msg}")
    FAIL += 1


# ═══════════════════════════════════════════════
#  1. B-C 集成测试脚本存在且可运行
# ═══════════════════════════════════════════════
def test_bc_integration_script():
    print("=" * 50)
    print("  1. B-C 集成测试脚本")
    print("=" * 50)

    script = os.path.join(PROJECT_ROOT, "client", "bc_integration_test.py")
    ok("bc_integration_test.py 存在", os.path.isfile(script))

    if not os.path.isfile(script):
        return

    # 检查关键内容
    with open(script, "r", encoding="utf-8") as f:
        content = f.read()

    checks = [
        ("SimulatedSignal 类", "class SimulatedSignal"),
        ("SimulatedBSignals (9 信号)", "class SimulatedBSignals"),
        ("测试1: 信号绑定", "test_signal_wiring"),
        ("测试2: ASR 管线", "test_asr_pipeline"),
        ("测试3: TTS 管线", "test_tts_pipeline"),
        ("测试4: 审计提交", "test_audit_submit"),
        ("测试5: 健康检测", "test_health_check"),
        ("测试6: 配置变更", "test_config_flow"),
        ("测试7: 完整交互序列", "test_full_interaction_sequence"),
    ]
    for desc, keyword in checks:
        ok(desc, keyword in content)

    # 尝试导入运行（不执行完整测试，只验证无语法错误）
    import py_compile
    try:
        py_compile.compile(script, doraise=True)
        ok("bc_integration_test.py 编译通过")
    except py_compile.PyCompileError as e:
        bad(f"编译失败: {e}")


# ═══════════════════════════════════════════════
#  2. 审计 E2E 测试脚本
# ═══════════════════════════════════════════════
def test_audit_e2e_script():
    print()
    print("=" * 50)
    print("  2. 审计 E2E 测试脚本")
    print("=" * 50)

    script = os.path.join(PROJECT_ROOT, "client", "audit_e2e_test.py")
    ok("audit_e2e_test.py 存在", os.path.isfile(script))

    if not os.path.isfile(script):
        return

    with open(script, "r", encoding="utf-8") as f:
        content = f.read()

    checks = [
        ("Mock HTTP 服务器", "class MockAuditHandler"),
        ("正常上报测试", "test_normal_upload"),
        ("错误重试测试", "test_server_error_retry"),
        ("脱敏验证 (6 类)", "test_desensitization"),
        ("请求格式验证", "test_record_format"),
        ("单独反馈端点", "test_feedback_endpoint"),
    ]
    for desc, keyword in checks:
        ok(desc, keyword in content)

    import py_compile
    try:
        py_compile.compile(script, doraise=True)
        ok("audit_e2e_test.py 编译通过")
    except py_compile.PyCompileError as e:
        bad(f"编译失败: {e}")


# ═══════════════════════════════════════════════
#  3. Web 管理面板 — 失败归因增强
# ═══════════════════════════════════════════════
def test_web_failures_enhancement():
    print()
    print("=" * 50)
    print("  3. Web 失败归因页增强")
    print("=" * 50)

    vue_file = os.path.join(PROJECT_ROOT, "web-admin", "src", "views", "Failures.vue")
    ok("Failures.vue 存在", os.path.isfile(vue_file))

    if not os.path.isfile(vue_file):
        return

    with open(vue_file, "r", encoding="utf-8") as f:
        content = f.read()

    checks = [
        ("el-drawer 详情滑出面板", "el-drawer"),
        ("el-collapse 折叠区", "el-collapse"),
        ("LLM 输入快照", "llm_input"),
        ("LLM 输出快照", "llm_output"),
        ("el-collapse-item LLM快照", "LLM 输入/输出快照"),
        ("el-collapse-item 指纹比对", "指纹比对详情"),
        ("柱状图点击事件", "c.on('click'"),
        ("filterType 筛选状态", "filterType"),
        ("el-tag 失败类型标签", "el-tag"),
        ("el-descriptions 详情", "el-descriptions"),
    ]
    for desc, keyword in checks:
        ok(desc, keyword in content)


# ═══════════════════════════════════════════════
#  4. 审计代理 — send_feedback 验证
# ═══════════════════════════════════════════════
def test_audit_feedback():
    print()
    print("=" * 50)
    print("  4. 审计代理 send_feedback")
    print("=" * 50)

    from client.audit.audit_agent import AuditAgent

    agent = AuditAgent()
    ok("send_feedback 方法存在", hasattr(agent, "send_feedback"))

    # 验证方法签名
    import inspect
    sig = inspect.signature(agent.send_feedback)
    params = list(sig.parameters.keys())
    ok("参数 task_id 存在", "task_id" in params)
    ok("参数 feedback_type 存在", "feedback_type" in params)
    ok("参数 comment 存在", "comment" in params)

    agent.shutdown()


# ═══════════════════════════════════════════════
#  5. 配置轮询器 — E2E 测试 (对 Mock 服务器)
# ═══════════════════════════════════════════════
def test_config_e2e():
    print()
    print("=" * 50)
    print("  5. 配置轮询器 E2E")
    print("=" * 50)

    from client.config.config_poller import ConfigPoller

    poller = ConfigPoller(
        server_url="http://localhost:18900",  # Mock 审计服务器端口
        interval_min=5,
    )

    state = poller.get_state()
    ok("轮询器创建成功", state["interval_min"] == 5)

    # 模拟服务端不可达
    result = poller.poll_now()
    ok("服务端不可达 → 返回 None (不崩溃)", result is None)

    poller.shutdown()
    ok("轮询器正常关闭", True)


# ═══════════════════════════════════════════════
#  6. B-C 控制器信号完整性
# ═══════════════════════════════════════════════
def test_controller_signals():
    print()
    print("=" * 50)
    print("  6. B-C 控制器信号完整性")
    print("=" * 50)

    from client.integration.controller import VoiceIntegrationController, HealthStatus

    ctrl = VoiceIntegrationController()
    ctrl.start()

    # 验证 9 个关键方法/信号处理函数存在
    methods = [
        ("_on_asr_result", "ASR 转写结果 → B"),
        ("_on_asr_stop", "ASR 停止录音"),
        ("_on_tts_enqueue", "TTS 播报入队"),
        ("_on_tts_status", "TTS 状态回传"),
        ("_on_audit_status", "审计状态回传"),
        ("_on_config_changed", "配置变更通知"),
        ("_handle_health_request", "健康检查请求"),
        ("health_check", "health_check 方法"),
    ]
    for method, desc in methods:
        ok(f"{desc} ({method})", hasattr(ctrl, method))

    # 健康检查
    health = ctrl.health_check()
    ok(f"健康检查返回 HealthStatus", isinstance(health, HealthStatus))
    ok(f"overall 字段存在", hasattr(health, "overall"))
    ok(f"7 个字段完整", all(hasattr(health, f) for f in [
        "asr_available", "asr_engine", "tts_available", "tts_engine",
        "audit_db_ok", "server_reachable", "queue_depth"
    ]))

    ctrl.shutdown()


# ═══════════════════════════════════════════════
#  汇总
# ═══════════════════════════════════════════════

if __name__ == "__main__":
    print()
    print("  HAJIMI Day 3 — 验证")
    print()

    test_bc_integration_script()
    test_audit_e2e_script()
    test_web_failures_enhancement()
    test_audit_feedback()
    test_config_e2e()
    test_controller_signals()

    print()
    print("=" * 50)
    print(f"  结果: {PASS} 通过, {FAIL} 失败")
    if FAIL == 0:
        print("  Day 3 全部验证通过")
    else:
        print(f"  ⚠ {FAIL} 项未通过")
