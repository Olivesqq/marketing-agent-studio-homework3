# 电商营销域数据库结构

## dim_user 用户维表

字段包括 user_id、vip_level、geo_city、churn_score、marketing_consent、mobile_hash、register_date、last_active_date。任何营销圈选必须满足 marketing_consent = TRUE。mobile_hash 属于敏感字段，不得出现在导出结果。

## fact_order 订单事实表

字段包括 order_id、user_id、pay_time、payment_amount、order_status、category。分析必须先按 order_id 去重，再过滤空金额、非正金额和非 completed 订单。推荐读取 clean_order_valid 视图。

## fact_user_activity 行为事实表

字段包括 event_id、user_id、event_time、event_type，可用于计算浏览、搜索、加购和收藏等意向信号。

## fact_campaign_touch 触达事实表

字段包括 touch_id、user_id、campaign_id、variant_id、send_time、delivered、opened、clicked、converted。默认频控为任意用户 7 天最多 2 次营销触达。

## dim_offer 权益维表

字段包括 offer_id、offer_name、threshold_amount、discount_amount、valid_days、cost_cap。优惠金额不得超过 cost_cap。

