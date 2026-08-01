"""渠道交易记录 ViewSet。

ADR-008 决策：6 个渠道 API 端点已移除（alipay/wechat/boc list+detail）。
models + admin 保留，前端查询统一走 /api/transactions/。
"""
