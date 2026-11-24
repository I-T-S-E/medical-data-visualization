-- =====================================================================
-- 002_widen_cases_content.sql
-- 原因：当前爬虫 CSV 的 content 最大长度 276 字符，超过 cases.content
--       varchar(255)，同步会报 (1406, "Data too long for column 'content'")
-- 说明：一次性迁移，执行前建议已备份 cases；按 001 → 002 顺序执行。
-- =====================================================================

SET NAMES utf8mb4;

-- 病例主表：病情描述放宽为 TEXT
ALTER TABLE cases
  MODIFY COLUMN content TEXT NULL COMMENT '病情描述';

-- 版本快照表：若已创建则同步放宽，避免快照/回滚时截断
SET @has_snapshot := (
  SELECT COUNT(*) FROM information_schema.TABLES
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'cases_snapshot'
);
SET @ddl := IF(
  @has_snapshot > 0,
  'ALTER TABLE cases_snapshot MODIFY COLUMN content TEXT NULL COMMENT ''病情描述''',
  'SELECT ''cases_snapshot not found, skipped'' AS note'
);
PREPARE stmt FROM @ddl;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- 验证：应显示 TEXT / text
SELECT TABLE_NAME, COLUMN_NAME, DATA_TYPE
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND COLUMN_NAME = 'content'
  AND TABLE_NAME IN ('cases', 'cases_snapshot');
