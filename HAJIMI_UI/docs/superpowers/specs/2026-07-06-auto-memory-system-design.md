# HAJIMI 自动记忆系统 — 设计文档

## 目标

让 HAJIMI 在用户使用过程中**全自动**学习用户习惯，在后续任务的 LLM 调用中注入相关记忆，使规划更准确、执行更高效。用户无感知，无需手动操作。

## 核心理念

**三层记忆，全自动运转。**

```
任务完成 → 自动提取记忆 ──→ 下次任务 → 自动注入 Prompt
                ↑                            │
                └──── 反馈信号 ───────────────┘
```

---

## 架构

### 三层记忆模型

```
                         ┌──────────────────┐
                         │   用户自然语言    │
                         └────────┬─────────┘
                                  │
                 ┌────────────────┼────────────────┐
                 ▼                ▼                 ▼
          ┌────────────┐  ┌────────────┐  ┌────────────┐
          │  第1层     │  │  第2层     │  │  第3层     │
          │  用户画像   │  │  任务记忆   │  │  失败指纹   │
          │  (慢变事实) │  │ (成功案例)  │  │ (已解决问题) │
          │  profile   │  │success_     │  │failure_     │
          │            │  │  pattern   │  │  lesson     │
          └────────────┘  └────────────┘  └────────────┘
                 │                │                 │
                 └────────────────┼─────────────────┘
                                  │
                                  ▼
                         ┌──────────────────┐
                         │  MemoryRetriever │
                         │  (embedding检索) │
                         └────────┬─────────┘
                                  │
                           top-5 → top-2过滤
                           硬性 ≤300 Token
                           (复杂屏幕动态降级)
                                  │
                                  ▼
                         ┌──────────────────┐
                         │  注入 Planner +  │
                         │  Executor Prompt │
                         └──────────────────┘
```

### 数据流

```
┌─────────────────────────────────────────────────────────────────┐
│                        任务执行成功                              │
│                             │                                   │
│              ┌──────────────┴──────────────┐                    │
│              ▼                              ▼                    │
│     MemoryExtractor                  MemoryDeduper              │
│     (便宜LLM, ~500ms)                 (embedding相似度)          │
│     提取: 用了什么软件                去重: 同category           │
│           什么文件夹                  相似度>0.85则更新覆盖       │
│           什么操作模式                旧记忆 is_active=False     │
│              │                              │                    │
│              │                    同时检索 failure_lesson       │
│              │                    相似度>0.9 则 resolved+=1     │
│              │                              │                    │
│              └──────────────┬──────────────┘                    │
│                             ▼                                   │
│                      t_memories 表                              │
│                      User.preferences                           │
│                                                                 │
│   ═══════════════════════════════════════════════════════════   │
│                                                                 │
│                        下次任务到达                              │
│                             │                                   │
│                             ▼                                   │
│                    MemoryRetriever                              │
│          ┌─────────┤ 从内存缓存加载活跃记忆                      │
│          │         │ 对用户原始 query 编码检索 top-5            │
│          │         │ 过滤到 top-2                               │
│          │         │ Token 预算检查（≤300 / 复杂屏幕≤150）      │
│          │         │ 截断超限 summary                           │
│          ▼                                                   │
│   注入 Planner prompt (plan_and_locate / plan_goal)               │
│   注入 Executor prompt (EXECUTION_SYSTEM_PROMPT)                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 数据模型

### `t_memories` 表（新增）

```sql
CREATE TABLE t_memories (
    memory_id       TEXT PRIMARY KEY,        -- UUID
    user_id         TEXT NOT NULL,           -- FK → t_users.user_id，多用户隔离
    memory_type     TEXT NOT NULL,           -- 'profile' | 'success_pattern' | 'failure_lesson'
    category        TEXT,                    -- 'app_preference' | 'path_habit' | 'term_mapping' | 'task_workflow' | 'failure_avoidance'
    trigger_query   TEXT NOT NULL,           -- 用户原始自然语言指令（用于 embedding 检索匹配）
    summary         TEXT NOT NULL,           -- 单句记忆结论，≤500 字符
    embedding       BLOB,                   -- 384 维 float32 向量（对 trigger_query 编码）
    confidence      REAL DEFAULT 1.0,       -- 0.0-1.0
    is_active       INTEGER DEFAULT 1,      -- 1=有效，0=已被更新覆盖
    event_count     INTEGER DEFAULT 1,      -- 该记忆被触发/确认的次数
    resolved_count  INTEGER DEFAULT 0,      -- (仅 failure_lesson) 被新路径解决的次数
    created_at      TEXT NOT NULL,          -- ISO 8601
    updated_at      TEXT NOT NULL           -- ISO 8601
);

CREATE INDEX idx_memories_user_active_type ON t_memories(user_id, is_active, memory_type);
```

### `User.preferences` 更新

`t_users.preferences` JSON 字段，当前为空壳。提取到用户画像时写入结构：

```json
{
  "app_preferences": [
    {"app_category": "browser", "preferred": "Chrome", "avoid": "Edge", "updated_at": "..."},
    {"app_category": "office", "preferred": "WPS", "avoid": null, "updated_at": "..."}
  ],
  "path_habits": [
    {"purpose": "work_documents", "path": "D:\\Work", "updated_at": "..."},
    {"purpose": "downloads", "path": "D:\\Downloads", "updated_at": "..."}
  ],
  "term_mappings": [
    {"user_term": "做表", "actual_app": "Excel", "updated_at": "..."}
  ]
}
```

**更新覆盖规则**：同 key（如 `browser`）写入新值时，旧值被替换，不保留历史。

---

## Phase 1：成功任务记忆（核心路径）

### 提取流程

任务成功后，`demo.py` 在后台线程调用 `MemoryExtractor.extract_from_success()`：

1. **输入**：`user_id`、`user_query`（原始自然语言）、`steps`（执行步骤列表）、执行上下文（app_name, folder_path 从步骤中推断）
2. **LLM 提取**：用便宜模型（默认 Qwen-Turbo）提取一句结论
3. **去重入库**：调用 `MemoryDeduper.check_and_merge(user_id, summary, category)`
4. **画像同步**：异步更新 `User.preferences`
5. **失败消解**：检索关联的 `failure_lesson`，触发 `resolved_count += 1`

### 便宜 LLM Prompt（防解析失败）

```
从以下任务执行记录中提取关键信息。严格返回 JSON，不要任何其他文字：
{"app": "使用的应用名(无则null)", "path": "涉及的文件路径(无则null)", "summary": "一句话概括操作(≤100字)"}

任务: {query}
步骤: {steps}
```

解析时使用 `providers.py` 已有的 `extract_json_object()` 回退解析器，外层加 `try/except` 容错——解析失败则用原始文本的前 100 字作为 summary。

### 检索注入流程

每次 Planner 调用前，`MemoryRetriever.retrieve(user_id, query)` 执行：

1. **编码**：对 `query`（用户原始自然语言）编码为 384 维向量
2. **检索**：在 `_memory_cache[user_id]` 中遍历 `is_active=True` 的向量，计算余弦相似度，取 top-5
3. **过滤**：top-5 → 去除非必要类型 → 保留 top-2
4. **Token 预算检查**：（见边界条件 4）
5. **截断**：每条 summary 超 150 Token 则尾部截断
6. **格式化输出**：

```
[相关记忆]
1. {summary}
2. {summary}
```

### 去重逻辑（更新覆盖）

`MemoryDeduper.check_and_merge(user_id, summary, category)`：

1. 对同 `user_id`、同 `category` 且 `is_active=True` 的记忆做 embedding 相似度比对
2. **相似度 >0.85**：新 summary 覆盖旧记录，旧记录 `is_active=False`，旧 embedding 从 `_memory_cache[user_id]` 移除
3. **相似度 ≤0.85**：直接 INSERT 新行，追加到 `_memory_cache[user_id]`
4. 跨 category 不去重（`app_preference` 不会误合并到 `path_habit`）

### 注入目标

| 注入点 | 位置 | 方式 |
|--------|------|------|
| Plan+Locate Combo | `agent/chains.py` → `plan_and_locate()` | `PLAN_LOCATE_COMBO_USER` 中 `{user_memory}` 占位 |
| Planner (standalone) | `agent/chains.py` → `plan_goal()` | `PLANNER_USER_TEMPLATE` 中 `{user_memory}` 占位 |
| Executor | `executor/agent.py` | `EXECUTION_SYSTEM_PROMPT` 末尾追加记忆上下文 |

---

## Phase 2：用户画像 + 失败指纹

### 第1层：用户画像（更新覆盖）

- `MemoryExtractor` 使用便宜 LLM 提取偏好时，返回 `memory_type='profile'` 和具体 `category`
- `MemoryDeduper` 对同 `category` 做去重
- **更新覆盖规则**：当新画像条目与旧条目同 `category` 且相似度 >0.85 → 新覆盖旧，旧 `is_active=False`
- **严禁两条矛盾记忆共存**：同一 category 在任何时刻最多只有 1 条 is_active=True 的记忆

### 第3层：失败指纹

**写入门槛**：
- 仅当任务彻底失败时触发（执行引擎耗尽 15 轮重试，`result='failed'`）
- 单步偶发重试（retry count < 15）不记录
- `memory_type='failure_lesson'`，`category='failure_avoidance'`

**精准关联（防误伤）**：
- `extract_from_success()` 中，提取成功后检索所有 `memory_type='failure_lesson'` 且 `is_active=True`
- 仅当 `trigger_query` 与新成功任务的 `user_query` 余弦相似度 **>0.9** 时，该失败记忆 `resolved_count += 1`
- `resolved_count >= 1` 时 `is_active=False`，后续不再注入

**失败提示格式**：
```
[注意] 上次类似任务失败: {summary}。已成功绕过 {resolved_count} 次。
```

---

## 边界条件

### 1. 检索性能保障（防全表扫描）+ 多用户隔离

**问题**：记忆积累到 1000+ 条时，每次从 SQLite 查全表再做 Python 余弦相似度遍历，延迟可达 100ms+。同时多用户场景下必须按 `user_id` 隔离，防止 A 用户的记忆注入到 B 用户的 Prompt。

**方案**：
- 应用启动时，`MemoryRetriever` 将 `is_active=True` 的记忆按 `user_id` 分组加载到 `_memory_cache: Dict[str, List[MemoryCacheEntry]]`（以 user_id 为键的字典）
- 检索时直接遍历 `_memory_cache[user_id]` 做余弦相似度，O(n)，无 DB 查询，天然隔离不同用户
- 去重合并会持续淘汰旧记忆（`is_active=False`），活跃记忆数量可控
- 新增/更新记忆时加锁同步更新对应 `user_id` 的缓存列表
- DB 层面建立复合索引：`CREATE INDEX idx_memories_user_active_type ON t_memories(user_id, is_active, memory_type)`（加速启动加载 + 按用户查询）
- 所有 MemoryExtractor 和 MemoryRetriever 公开 API 都必须接受 `user_id` 参数

### 2. 失败指纹精准关联（防误伤）

**问题**：无过滤地将所有失败记忆关联到任何成功任务，会导致"打开浏览器成功"误消解"用 Excel 导出 PDF 失败"。

**方案**：
- `extract_from_success()` 中增加 `_resolve_failure_lessons(user_query)` 步骤
- 对 `user_query` 编码后在内存缓存中检索所有 `memory_type='failure_lesson'` 且 `is_active=True` 的记忆
- 仅当 `cosine_similarity > 0.9`（严格阈值）时才触发 `resolved_count += 1`
- `resolved_count >= 1` 时 `is_active = False`

### 3. 便宜 LLM 输出格式约束（防解析失败）

**问题**：便宜模型可能输出"好的，分析结果如下：……"而非纯 JSON，导致字段无法入库。

**方案**：
- Prompt 中强制声明：`严格返回 JSON，不要任何其他文字`
- 使用 `providers.py` 已有的 `extract_json_object()` 健壮解析器（支持代码块提取、BOM 清理、尾随逗号修复、反向扫描查找 `{...}`）
- 外层 `try/except` 兜底：JSON 解析完全失败时，用原始 LLM 输出的前 100 字作为 `summary`，`app` 和 `path` 设为 `null`
- 解析失败记录 warning 日志，但不阻塞提取流程

### 4. 动态 Token 预算分配（防注意力崩溃）

**问题**：当 OmniParser 返回 50+ 元素时，Prompt 本身已达 2000+ Token，再加 300 Token 记忆可能导致轻量模型注意力漂移。

**方案**：
- `MemoryRetriever.retrieve()` 接受可选的 `element_count` 参数
- **元素 >50**：`MEMORY_TOKEN_BUDGET = 150`，只注入 top-1（仅 `success_pattern`）
- **元素 ≤50**：`MEMORY_TOKEN_BUDGET = 300`，注入 top-2
- 截断策略：按中文字符 ≈1 token，英文单词 ≈0.75 token 估算，超限从 `summary` 尾部截断并追加 `…`
- 默认不传 `element_count` 时按 300 Token 预算

### 5. 内存缓存并发安全（防遍历崩溃）

**问题**：`demo.py` 在后台线程调用 `MemoryExtractor` 提取记忆后通过 `_update_cache()` 写入 `_memory_cache`，同时前端请求线程调用 `retrieve()` 遍历同一列表。Python 的 list 在遍历过程中被另一个线程追加或替换元素，可能触发 `RuntimeError: list changed size during iteration` 或读到半更新状态。

**方案**：
- `MemoryRetriever` 内部维护一个 `threading.Lock`（`_cache_lock`）
- `retrieve()` 遍历 `_memory_cache[user_id]` 时 `with self._cache_lock:`
- `_update_cache()` 追加/替换 `_memory_cache[user_id]` 时 `with self._cache_lock:`
- 锁粒度控制在缓存操作层，不包裹 DB I/O 或 LLM 调用（避免长时间持锁）
- 提取流程中：先完成 LLM 调用 + DB 写入（无锁），最后仅 `_update_cache` 时加锁

---

## 模块结构

```
server/services/memory/
├── __init__.py          # 包入口，导出 MemoryExtractor, MemoryRetriever
├── extractor.py         # MemoryExtractor — 从成功/失败任务自动提取记忆
├── retriever.py         # MemoryRetriever — 检索+过滤+格式化，注入 prompt
├── deduper.py           # MemoryDeduper — 相似度去重，更新覆盖策略
└── embedder.py          # 薄封装，复用 embedding_matcher 的编码 + DB blob 读写
```

### 模块职责

**`embedder.py`**：
- `encode(text) -> np.ndarray`：封装 `embedding_matcher.get_embedding()`
- `to_blob(vec) -> bytes`：`np.ndarray.tobytes()`
- `from_blob(b) -> np.ndarray`：`np.frombuffer().reshape()`

**`extractor.py` — `MemoryExtractor`**：
- `extract_from_success(user_id, user_query, steps, context)`：便宜 LLM 提取 → 去重 → 入库 → 消解失败
- `extract_from_failure(user_id, user_query, steps, error_detail)`：仅当完全失败时调用
- `_extract_with_llm(query, steps)`：调用便宜 LLM，返回 `{app, path, summary}`
- `_resolve_failure_lessons(user_id, user_query)`：在 `_memory_cache[user_id]` 中检索并消解关联的失败指纹

**`retriever.py` — `MemoryRetriever`**：
- `load_cache()`：启动时从 DB 加载所有 `is_active=True` 记忆，按 `user_id` 分组到 `_memory_cache: Dict[str, List[MemoryCacheEntry]]`
- `retrieve(user_id, query, element_count=None)`：编码 → 在 `_memory_cache[user_id]` 中检索 top-5 → 过滤 top-2 → Token 预算 → 格式化。操作时持有 `_cache_lock` 读锁。
- `_update_cache(user_id, memory)`：在 `_cache_lock` 保护下追加或替换对应 user_id 缓存条目
- 包含 `threading.Lock` 实例 `_cache_lock`

**`deduper.py` — `MemoryDeduper`**：
- `check_and_merge(user_id, summary, category, memory_type)`：同 user_id + 同 category 去重，>0.85 更新覆盖

---

## 文件改动清单

与浏览器改动（`browser/controller.py`、`executor/agent.py`、`executor/engine.py`）**零冲突**。

| 文件 | 操作 | 行数估算 |
|------|------|----------|
| `server/database/models.py` | 改：新增 `Memory` ORM 类 | +35 |
| `server/database/repository.py` | 改：新增 `MemoryRepository` CRUD | +60 |
| `server/services/memory/__init__.py` | **新** | +15 |
| `server/services/memory/embedder.py` | **新** | +40 |
| `server/services/memory/extractor.py` | **新** | +100 |
| `server/services/memory/retriever.py` | **新** | +70 |
| `server/services/memory/deduper.py` | **新** | +50 |
| `server/services/agent/prompts.py` | 改：`{user_memory}` 占位 (+5 行) | +5 |
| `server/services/agent/chains.py` | 改：检索注入 (+15 行) | +15 |
| `server/services/executor/agent.py` | 改：Executor prompt 末尾注入 (+8 行) | +8 |
| `server/routes/demo.py` | 改：成功后触发异步提取 (+15 行) | +15 |
| **合计** | | **~410 行** |

### 关键约束汇总

| 约束 | 值 |
|------|-----|
| 多用户隔离 | `_memory_cache` 为 `Dict[user_id, List[...]]`；所有 API 接受 `user_id` |
| 并发安全 | `threading.Lock` 保护缓存读写，不包裹 I/O |
| 检索 top-K | top-5 → 过滤到 top-2 |
| 注入 Token 硬上限 | ≤300 Token |
| 复杂屏幕 Token 降级 | 元素 >50 时降级到 ≤150 Token |
| 去重相似度阈值 | >0.85 即合并 |
| 合并策略 | 新覆盖旧，旧 `is_active=False` |
| 失败消解相似度阈值 | >0.9（严格） |
| Embedding 检索目标 | 用户原始自然语言 (`trigger_query`) |
| 画像冲突策略 | 同 `category` 冲突时更新覆盖 |
| 失败记忆门槛 | 仅 `result='failed'`（15 轮耗尽） |
| 失败记忆消亡 | 新路径成功（相似度 >0.9）后 `is_active=False` |
| 便宜 LLM | Qwen-Turbo（默认，可通过配置切换） |

---

## 验证标准

1. **记忆提取**：执行一次成功任务（如"打开计算器"）后，`t_memories` 表中出现对应的 `memory_type='success_pattern'` 记录
2. **记忆去重**：执行两次几乎相同的任务后，表中只有 1 条 `is_active=True`，旧记忆 `is_active=False`
3. **检索注入**：第三次执行同类任务时，Planner prompt 中包含 `[相关记忆]` 块，且 Token 数 ≤300
4. **复杂屏幕降级**：模拟元素 >50 的场景，注入 Token ≤150
5. **失败指纹录入**：任务彻底失败（如"打开不存在的应用"且 15 轮耗尽）后，表中出现 `memory_type='failure_lesson'` 记录
6. **失败指纹消解**：用新路径成功完成同类任务后，关联失败记忆 `is_active=False`
7. **无关任务不误消解**：打开 Chrome 成功后，Excel 导出 PDF 的失败指纹不被消解（相似度不达 0.9）
8. **便宜 LLM 容错**：模拟模型返回非 JSON 输出，系统不崩溃，`summary` 使用原始文本前 100 字
9. **重启持久化**：服务重启后，`is_active=True` 的记忆仍可用于检索
10. **画像更新覆盖**：用户从 Chrome 转向 Edge 后，`app_preference` 中 browser 为 Edge，无残留 Chrome 记录
11. **多用户隔离**：用户 A 的记忆检索结果中不包含用户 B 的记忆
12. **并发安全**：同时执行提取（写）和检索（读）时，不抛出遍历异常
