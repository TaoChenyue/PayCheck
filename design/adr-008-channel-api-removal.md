# ADR-008: 渠道 API 端点去留评估

> **作者**: 架构师
> **日期**: 2026-08-02
> **关联 Issue**: TCY-71
> **状态**: 提议中

---

## 背景

TCY-61 审计发现后端 6 个渠道 API 端点完全闲置：

| 端点 | 方法 | 路由 |
|---|---|---|
| 支付宝列表 | GET | `/api/channels/alipay/` |
| 支付宝详情 | GET | `/api/channels/alipay/{id}/` |
| 微信列表 | GET | `/api/channels/wechat/` |
| 微信详情 | GET | `/api/channels/wechat/{id}/` |
| 银行列表 | GET | `/api/channels/boc/` |
| 银行详情 | GET | `/api/channels/boc/{id}/` |

需要评估这些端点的去留并输出决策。

---

## 调用链分析

### 1. 前端调用路径

前端通过以下路径查询渠道数据：

```
ChannelPage → useTransactions() → GET /api/transactions/?platform=xxx
```

- `frontend/src/pages/ChannelPage.tsx` 渲染渠道页面，使用 `useTransactions` hook
- `frontend/src/hooks/useTransactions.ts` 统一调用 `/api/transactions/` 端点
- `TransactionViewSet` 支持 `platform` 查询参数筛选渠道
- **前端代码中零引用 `/api/channels/` 路径**

### 2. 后端内部调用路径

后端其他模块与渠道模型的交互全部走 ORM 直连：

| 调用方 | 文件 | 调用方式 |
|---|---|---|
| 数据导入 | `backend/apps/ingest/tasks.py` | `AlipayTx.objects.create()`, `WechatTx.objects.create()`, `BocTx.objects.create()` |
| 交易删除级联 | `backend/apps/transactions/views.py` | `AlipayTx.objects.filter(id=source_id).delete()` 等 |

**零内部模块通过 HTTP 调用渠道 API 端点。**

### 3. URL 路由注册链

```
config/urls.py
  └── path("api/channels/", include("apps.channels.urls"))
        └── apps/channels/urls.py
              └── router.register("alipay", AlipayTxViewSet)
              └── router.register("wechat", WechatTxViewSet)
              └── router.register("boc", BocTxViewSet)
                    └── apps/channels/views.py
                          └── AlipayTxViewSet / WechatTxViewSet / BocTxViewSet
```

### 4. 渠道模块组件依赖矩阵

| 组件 | 被谁依赖 | 去留 |
|---|---|---|
| `models.py` | `ingest/tasks.py`, `transactions/views.py` | **保留** |
| `admin.py` | Django Admin 自动发现 | **保留**（调试/运维入口） |
| `views.py` | `urls.py` → `config/urls.py` | **移除** |
| `serializers.py` | `views.py` | **移除**（仅被 views 引用） |
| `urls.py` | `config/urls.py` | **移除**（路由注册） |

---

## 方案对比

### 方案 A：完全移除（推荐）

移除 `views.py` 内容、`urls.py` 内容、`serializers.py`，从 `config/urls.py` 中移除 `api/channels/` 路由注册。保留 `models.py` 和 `admin.py`。

**清理清单**：

| 文件 | 操作 | 说明 |
|---|---|---|
| `backend/apps/channels/views.py` | 清空或删除 | ViewSet 无人调用 |
| `backend/apps/channels/urls.py` | 清空路由 | 无可用视图 |
| `backend/apps/channels/serializers.py` | 删除 | 仅被 views 引用 |
| `backend/config/urls.py` | 移除第 8 行 | `path("api/channels/", ...)` |
| `backend/apps/channels/models.py` | 保留 | 被 ingest + transactions 依赖 |
| `backend/apps/channels/admin.py` | 保留 | Django Admin 运维入口 |

**优点**：
- 消除死代码，降低维护负担
- 缩小 API 攻击面（6 个未认证的只读端点）
- `channels/` app 保持为纯数据层，职责更清晰

**缺点**：
- 如需临时查询原始渠道表数据，只能通过 Django Admin 或数据库直连

### 方案 B：保留但添加权限控制

保留所有端点，添加 `IsAuthenticated` + `IsAdminUser` 权限类。

**优点**：
- 保留了通过 API 直接查询渠道表的能力
- 有权限控制，不暴露裸数据

**缺点**：
- Django Admin 已经提供了完全相同的查询能力（带 UI、筛选、导出）
- 维护 3 个 ViewSet + 3 个 Serializer 的持续成本
- 前端永远不需要这些端点（统一走 `/api/transactions/`）
- YAGNI（You Aren't Gonna Need It）

### 方案 C：合并到 TransactionViewSet（过度工程）

将渠道特有的余额/币种/分行等字段通过 TransactionSerializer 按需暴露。

**优点**：
- 统一入口，减少端点数量

**缺点**：
- TransactionSerializer 需要根据 platform 动态包含字段（增加复杂度）
- 前端当前不需要渠道特有字段（余额、币种、分行等仅在导入时使用）
- 违反"简单优先"原则

---

## 决策

**选择方案 A：完全移除渠道 API 端点。**

### 理由

1. **零调用方**：前后端均无 HTTP 消费者，是纯粹的死代码
2. **功能已被覆盖**：前端通过 `/api/transactions/?platform=xxx` 查询渠道数据，Django Admin 提供运维级数据访问
3. **简单优先**：移除比保留 + 加权限更简单，符合项目设计原则
4. **模型保留、视图移除**：渠道模型是数据导入和级联删除的基础设施，必须保留；ViewSet 是冗余的表现层，可以安全移除
5. **安全收益**：移除 6 个无认证的裸数据端点，减少潜在的信息泄露面

### 不选择方案 B 的原因

Django Admin 已经为 `AlipayTx`、`WechatTx`、`BocTx` 注册了管理界面，提供搜索、筛选、分页等完整功能。再加一层 API 权限控制是重复建设。

### 不选择方案 C 的原因

TransactionViewSet 当前按 `platform` 筛选已经满足所有前端需求。渠道特有字段（余额、币种、分行）仅用于导入阶段的数据解析，不需要通过 API 暴露给前端。

---

## 影响评估

| 维度 | 影响 |
|---|---|
| 前端 | 无影响 — 前端不调用这些端点 |
| 后端 import | 无影响 — 模型保留、admin 保留；仅删除 views/urls/serializers |
| 数据导入 | 无影响 — `ingest/tasks.py` 直接 ORM 操作渠道模型 |
| 交易删除级联 | 无影响 — `transactions/views.py` 直接 ORM 操作渠道模型 |
| Django Admin | 无影响 — `admin.py` 保留 |
| API 路由表 | 减少 6 个端点（3 list + 3 detail） |
| 测试 | 无影响 — 无测试覆盖这些端点 |
| 回滚 | `git revert` 即可恢复 |

---

## 实施参考（供后续 STAGE_IMPLEMENT 使用）

```bash
# 1. 移除 config/urls.py 中第 8 行
#    path("api/channels/", include("apps.channels.urls"))

# 2. 清空 views.py 或删除文件
# 3. 清空 urls.py 或删除文件
# 4. 删除 serializers.py

# 验证
cd backend && uv run manage.py check  # Django 系统检查
cd frontend && npx tsc --noEmit       # TypeScript 编译检查
```

---

> **文档结束**。本文档作为 TCY-71 的产出物，决策为**移除渠道 API 端点**。
