-- =====================================================================
-- 001_realtime.sql
-- 任务(2) 数据库实时更新：增量去重 + 同步批次/日志
-- 适用：MySQL 8.x，数据库 medicalinfo
-- 说明：本脚本为一次性迁移，请在业务低峰期执行，执行前务必备份 cases 表。
--       若你的库名不是 medicalinfo，请先 USE 你的库名，或去掉下面的 USE 语句。
-- =====================================================================

-- USE medicalinfo;
SET NAMES utf8mb4;

-- ---------------------------------------------------------------------
-- 1. cases 扩展字段
-- ---------------------------------------------------------------------
ALTER TABLE cases
  ADD COLUMN content_hash CHAR(64) NULL COMMENT '业务字段 SHA-256 去重哈希',
  ADD COLUMN source_code VARCHAR(32) DEFAULT 'crawler' COMMENT '数据来源标识',
  ADD COLUMN batch_id BIGINT NULL COMMENT '最近写入批次号',
  ADD COLUMN updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  ADD KEY idx_cases_batch (batch_id),
  ADD KEY idx_cases_source (source_code);

-- ---------------------------------------------------------------------
-- 2. 回填 content_hash（与 SyncService.compute_hash 保持一致）
--    字段顺序：type|gender|age|time|content|docName|docHospital|department|
--              detailUrl|height|weight|illDuration|allergy
-- ---------------------------------------------------------------------
UPDATE cases
SET content_hash = SHA2(
  CONCAT_WS('|',
    COALESCE(type, ''),
    COALESCE(gender, ''),
    COALESCE(age, ''),
    COALESCE(time, ''),
    COALESCE(content, ''),
    COALESCE(docName, ''),
    COALESCE(docHospital, ''),
    COALESCE(department, ''),
    COALESCE(detailUrl, ''),
    COALESCE(height, ''),
    COALESCE(weight, ''),
    COALESCE(illDuration, ''),
    COALESCE(allergy, '')
  ),
  256
)
WHERE content_hash IS NULL;

-- ---------------------------------------------------------------------
-- 3. 去重：同一 content_hash 保留 id 最小的一条
--    否则后续唯一索引会创建失败
-- ---------------------------------------------------------------------
DELETE c1
FROM cases c1
JOIN cases c2
  ON c1.content_hash = c2.content_hash
 AND c1.id > c2.id;

-- ---------------------------------------------------------------------
-- 4. content_hash 置为 NOT NULL 并建立唯一索引（幂等 upsert 的关键）
-- ---------------------------------------------------------------------
ALTER TABLE cases
  MODIFY COLUMN content_hash CHAR(64) NOT NULL COMMENT '业务字段 SHA-256 去重哈希',
  ADD UNIQUE KEY uk_cases_hash (content_hash);

-- ---------------------------------------------------------------------
-- 5. 同步批次表
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sync_batches (
  id BIGINT NOT NULL AUTO_INCREMENT,
  source_code VARCHAR(32) NOT NULL COMMENT '数据源标识',
  status VARCHAR(20) NOT NULL COMMENT 'running/success/failed',
  inserted INT NOT NULL DEFAULT 0 COMMENT '新增条数',
  updated INT NOT NULL DEFAULT 0 COMMENT '更新条数',
  skipped INT NOT NULL DEFAULT 0 COMMENT '跳过条数',
  error_message TEXT NULL COMMENT '失败原因',
  started_at DATETIME NOT NULL COMMENT '开始时间',
  finished_at DATETIME NULL COMMENT '结束时间',
  PRIMARY KEY (id),
  KEY idx_source_started (source_code, started_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='数据同步批次';

-- ---------------------------------------------------------------------
-- 6. 同步日志表
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sync_logs (
  id BIGINT NOT NULL AUTO_INCREMENT,
  batch_id BIGINT NULL COMMENT '关联批次',
  level VARCHAR(16) NOT NULL COMMENT 'INFO/WARN/ERROR',
  message TEXT NOT NULL COMMENT '日志内容',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_batch (batch_id),
  KEY idx_created (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='数据同步日志';

-- ---------------------------------------------------------------------
-- 7. 迁移结果验证（应满足 hashed = total，distinct_hash = total）
-- ---------------------------------------------------------------------
SELECT
  COUNT(*) AS total,
  COUNT(content_hash) AS hashed,
  COUNT(DISTINCT content_hash) AS distinct_hash
FROM cases;

-- =====================================================================
-- 回滚（如需，请逐条执行；先确认业务可接受数据回退）
-- ---------------------------------------------------------------------
-- DROP TABLE IF EXISTS sync_logs;
-- DROP TABLE IF EXISTS sync_batches;
-- ALTER TABLE cases
--   DROP INDEX uk_cases_hash,
--   DROP INDEX idx_cases_batch,
--   DROP INDEX idx_cases_source,
--   DROP COLUMN updated_at,
--   DROP COLUMN batch_id,
--   DROP COLUMN source_code,
--   DROP COLUMN content_hash;
-- =====================================================================
