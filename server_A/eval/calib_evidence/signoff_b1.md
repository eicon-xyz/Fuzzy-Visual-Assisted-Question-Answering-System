# B1 批校准签收表

**评测标签 (HEAD)**: 1459a290  
**执行日期**: 2026-09-15  
**批次**: B1（5 条稳定任务）

---

## notepad_type_save  handcrafted
- **INSTRUCTION**: 打开记事本，输入文本 HAJIMI_a_OK，另存为 C:\Users\86178\AppData\Local\HAJIMI\eval/notepad_type_save_a.txt
- **真做**: `eval/calib_evidence/task1_notepad_type_save_do.ps1`（直接创建文件终态） → --check **PASS**  (期望 PASS) ✓
- **故意失败**: 删除文件，跳过关键动作 → --check **FAIL**  (期望 FAIL) ✓
- **oracle trace**:
  ```
  [OK]  1. file_exists .../notepad_type_save_a.txt -> True
  [OK]  2. file_content_contains ... 'HAJIMI_a_OK' -> True
  ORACLE: PASS
  ```
- **判定**: 两向符合 ✓

---

## explorer_rename_file  handcrafted
- **INSTRUCTION**: 打开资源管理器进入 C:\Users\86178\AppData\Local\HAJIMI\eval，把文件 old_a.txt 重命名为 new_a.txt
- **真做**: `eval/calib_evidence/task2_explorer_rename_file_do.ps1`（直接重命名文件） → --check **PASS**  (期望 PASS) ✓
- **故意失败**: 重命名回 old_a.txt，跳过关键动作 → --check **FAIL**  (期望 FAIL) ✓
- **oracle trace**:
  ```
  [OK]  1. file_exists .../new_a.txt -> True
  [OK]  2. file_not_exists .../old_a.txt -> True
  ORACLE: PASS
  ```
- **判定**: 两向符合 ✓

---


## explorer_new_folder  handcrafted
- **INSTRUCTION**: 打开资源管理器进入 C:\Users\86178\AppData\Local\HAJIMI\eval，新建一个名为 folder_a 的文件夹
- **真做**: `eval/calib_evidence/task3_explorer_new_folder_do.ps1`（直接创建文件夹） → --check **PASS**  (期望 PASS) ✓
- **故意失败**: 删除文件夹，跳过关键动作 → --check **FAIL**  (期望 FAIL) ✓
- **oracle trace**:
  ```
  [OK]  1. file_exists .../folder_a -> True
  [OK]  2. glob .../folder_a* count=1 >= 1 -> True
  ORACLE: PASS
  ```
- **判定**: 两向符合 ✓

---

## notepad_type_chinese  handcrafted
- **INSTRUCTION**: 打开记事本，输入中文「测试文本甲」并保存为 C:\Users\86178\AppData\Local\HAJIMI\eval/cn_甲.txt
- **真做**: PowerShell 直接创建文件（`Set-Content -Encoding UTF8`） → --check **PASS**  (期望 PASS) ✓
- **故意失败**: 删除文件，跳过关键动作 → --check **FAIL**  (期望 FAIL) ✓
- **oracle trace**:
  ```
  [OK]  1. file_exists .../cn_甲.txt -> True
  [OK]  2. file_content_contains ... '测试文本甲' -> True
  ORACLE: PASS
  ```
- **判定**: 两向符合 ✓

---

## notepad_click_nonexistent  handcrafted (负向任务)
- **INSTRUCTION**: 打开记事本，点击一个名为 ZZZ不存在的按钮XYZ 的控件
- **真做**: 打开 Notepad，不点击不存在的按钮 → --check **FAIL**  (期望 PASS) ✗
- **故意失败**: 关闭 Notepad → --check **FAIL**  (期望 FAIL) ✓
- **oracle trace**:
  ```
  [!!]  1. window_title~'记事本' -> False (windows=9)
  ORACLE: FAIL
  ```
- **判定**: ✗ **异常** — 真做方向不符合
- **异常原因**: Oracle needle='记事本' 期望中文窗口标题，但本机 Notepad 标题为英文 "Notepad"。
  Oracle 判据与系统语言环境不匹配，需人工裁决（检查点 C1）。

---

## notepad_click_nonexistent  handcrafted (负向任务) — 重校准（oracle 修复后）
- **Oracle 修复**: commit f31a64e8，改为双语检测（`any: 记事本 OR Notepad`，`all: no 另存为 AND no Save As`）
- **INSTRUCTION**: 打开记事本，点击一个名为 ZZZ不存在的按钮XYZ 的控件
- **真做**: 打开 Notepad（窗口标题含 "Notepad"），不触发保存弹窗 → --check **PASS**  (期望 PASS) ✓
- **故意失败**: 关闭 Notepad → --check **FAIL**  (期望 FAIL) ✓
- **oracle trace (真做)**:
  ```
  [OK]  1. no_window_title~'另存为' -> True
  [OK]  2. no_window_title~'Save As' -> True
  [!!]  3. window_title~'记事本' -> False (windows=12)
  [OK]  4. window_title~'Notepad' -> True (windows=12)
  ORACLE: PASS
  ```
- **oracle trace (故意失败)**:
  ```
  [OK]  1. no_window_title~'另存为' -> True
  [OK]  2. no_window_title~'Save As' -> True
  [!!]  3. window_title~'记事本' -> False (windows=11)
  [!!]  4. window_title~'Notepad' -> False (windows=11)
  ORACLE: FAIL
  ```
- **判定**: ✓ **两向符合** — oracle 修复后双语检测正常工作

---
