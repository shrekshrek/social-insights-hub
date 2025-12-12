-- 清理 AI 分析任务记录
-- 运行方式: psql -d your_database -f cleanup_analysis_jobs.sql

-- 1. 删除 aggregation 类型的记录（聚合分析不涉及 LLM，不应出现在 AI 分析列表中）
DELETE FROM analysis_jobs WHERE analysis_type = 'aggregation';

-- 2. 将旧的 topic_normalization 类型更新为 opinion_normalization
UPDATE analysis_jobs 
SET analysis_type = 'opinion_normalization' 
WHERE analysis_type = 'topic_normalization';

-- 查看清理后的结果
SELECT analysis_type, COUNT(*) as count 
FROM analysis_jobs 
GROUP BY analysis_type 
ORDER BY analysis_type;

