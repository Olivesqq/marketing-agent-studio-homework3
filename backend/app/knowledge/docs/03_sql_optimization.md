# DuckDB SQL 生成与优化指南

## 安全边界

只允许单条 SELECT 或 WITH 查询。禁止 INSERT、UPDATE、DELETE、DROP、ALTER、CREATE、COPY、ATTACH 和多语句。查询仅可访问白名单业务表与清洗视图，不得投影 mobile_hash。

## 查询优化

先按时间和订单状态过滤，再聚合和连接；避免 SELECT *；大表连接前先缩小数据集；预览结果使用外层 LIMIT；所有候选 SQL 必须先完成 AST 校验和 EXPLAIN，再真实执行。

## 常见修复

Table not found 时检索数据库结构并替换为真实表；字段不存在时检查字段字典；结果为空时核对时间边界和业务阈值；除数使用 NULLIF 防止除零。

