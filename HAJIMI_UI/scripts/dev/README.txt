开发者/高级入口（根目录请用 启动全栈.bat / 启动本地.bat / stop_all.bat）
唯一模式 = L5 自动执行（server_A Sidecar :8011）；旧的 Mock、CPU Omni 降级
（start_local_cpu）、内网联调（start_lan_client / GPU 隧道）入口已随 L4 移除。

  dev\start_all.bat           — L5 Sidecar + B 端（转发 scripts\start_all.bat）
  dev\start_ui.bat            — 仅 B 端 UI（转发 scripts\start_ui.bat）
  dev\check_deploy.bat        — 只检查环境/链路（转发 scripts\check_deploy.bat）
  dev\test_click_fixed.bat    — 固定坐标点击 Tier1
  dev\test_click_http.bat     — 固定坐标点击 Tier2 HTTP（需 8011 Sidecar）
  check_bat_parens.py         — 静态扫描 .bat：if/for 括号块内 echo 未转义 ( )

launchers\ 下旧路径已重定向到此目录。
