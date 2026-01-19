# Snowflake Schema Reference for Agents

This document provides complete schema information for all Snowflake tables that agents can query. Agents should use this information to build custom SQL queries using the `execute_custom_snowflake_query` tool.

## Available Tables

### 1. `reports.reporting_revamp.ALL_PERFORMANCE_AGG`
**Purpose**: Main performance data table - daily metrics at IO and line item level.

**Granularity**: Daily (one row per day per insertion_order per line_item)

**Columns**:
- `advertiser` (VARCHAR): Advertiser name - **ALWAYS filter to 'Quiz'**
- `date` (DATE): Date of metrics (YYYY-MM-DD format)
- `insertion_order` (VARCHAR): Insertion order name (IO/campaign level)
- `line_item` (VARCHAR): Line item name (tactic level) - NULL for IO-level aggregations
- `spend_gbp` (DECIMAL): Daily spend in British Pounds (£)
- `impressions` (INTEGER): Number of impressions
- `clicks` (INTEGER): Number of clicks
- `total_conversions_pm` (DECIMAL): Total conversions (post-click + post-view)
- `total_revenue_gbp_pm` (DECIMAL): Total revenue in British Pounds (£)

**Common Query Patterns**:
```sql
-- IO-level performance (aggregate by insertion_order)
SELECT 
    insertion_order,
    SUM(spend_gbp) as TOTAL_SPEND,
    SUM(impressions) as TOTAL_IMPRESSIONS,
    SUM(clicks) as TOTAL_CLICKS,
    SUM(total_conversions_pm) as TOTAL_CONVERSIONS,
    SUM(total_revenue_gbp_pm) as TOTAL_REVENUE
FROM reports.reporting_revamp.ALL_PERFORMANCE_AGG
WHERE advertiser = 'Quiz'
    AND date >= '2026-01-01'
    AND date <= '2026-01-31'
GROUP BY insertion_order
ORDER BY TOTAL_SPEND DESC

-- Line item level (audience/tactic analysis)
SELECT 
    insertion_order,
    line_item,
    SUM(spend_gbp) as TOTAL_SPEND,
    SUM(impressions) as TOTAL_IMPRESSIONS,
    SUM(clicks) as TOTAL_CLICKS
FROM reports.reporting_revamp.ALL_PERFORMANCE_AGG
WHERE advertiser = 'Quiz'
    AND date >= '2026-01-01'
    AND line_item IS NOT NULL
GROUP BY insertion_order, line_item
ORDER BY TOTAL_SPEND DESC
```

**Calculated Metrics** (compute in analysis):
- CTR = (clicks / impressions) * 100
- CPC = spend_gbp / clicks
- CPA = spend_gbp / total_conversions_pm
- ROAS = total_revenue_gbp_pm / spend_gbp
- CVR = (total_conversions_pm / clicks) * 100

---

### 2. `reports.reporting_revamp.creative_name_agg`
**Purpose**: Creative asset performance data - by creative name and size.

**Granularity**: Daily (one row per day per insertion_order per creative_name per creative_size)

**Columns**:
- `advertiser` (VARCHAR): Advertiser name - **ALWAYS filter to 'Quiz'**
- `date` (DATE): Date of metrics (YYYY-MM-DD format)
- `insertion_order` (VARCHAR): Insertion order name
- `creative` (VARCHAR): Full creative identifier (may include suffixes)
- `creative_size` (VARCHAR): Ad size/format (e.g., "300x250", "728x90", "970x250")
- `spend_gbp` (DECIMAL): Daily spend in British Pounds (£)
- `impressions` (INTEGER): Number of impressions
- `clicks` (INTEGER): Number of clicks
- `total_conversions_pm` (DECIMAL): Total conversions
- `total_revenue_gbp_pm` (DECIMAL): Total revenue in British Pounds (£)

**Note**: The `creative` column may include suffixes. To get creative name without suffix, use:
```sql
REGEXP_REPLACE(creative, '_[^_]*$', '') AS creative_name
```

**Common Query Patterns**:
```sql
-- Creative performance by name
SELECT 
    REGEXP_REPLACE(creative, '_[^_]*$', '') AS creative_name,
    SUM(spend_gbp) as TOTAL_SPEND,
    SUM(impressions) as TOTAL_IMPRESSIONS,
    SUM(clicks) as TOTAL_CLICKS,
    SUM(total_conversions_pm) as TOTAL_CONVERSIONS
FROM reports.reporting_revamp.creative_name_agg
WHERE advertiser = 'Quiz'
    AND date >= '2026-01-01'
GROUP BY creative_name
ORDER BY TOTAL_SPEND DESC

-- Creative performance by size
SELECT 
    creative_size,
    SUM(spend_gbp) as TOTAL_SPEND,
    SUM(impressions) as TOTAL_IMPRESSIONS,
    SUM(clicks) as TOTAL_CLICKS
FROM reports.reporting_revamp.creative_name_agg
WHERE advertiser = 'Quiz'
    AND date >= '2026-01-01'
GROUP BY creative_size
ORDER BY TOTAL_SPEND DESC
```

---

### 3. `reports.multi_agent.DV360_BUDGETS_QUIZ`
**Purpose**: Budget data for Quiz advertiser - monthly budget segments.

**Granularity**: Monthly segments (one row per month per insertion order)

**Important**: This table contains **ONLY Quiz advertiser** budgets - no advertiser column needed.

**Columns**:
- `INSERTION_ORDER_ID` (VARCHAR): Unique insertion order ID
- `IO_NAME` (VARCHAR): Insertion order name (e.g., "Quiz for Jan", "QuizClothing_UK_PROG_DV360_PRS")
- `IO_STATUS` (VARCHAR): Insertion order status (e.g., "ENTITY_STATUS_ACTIVE")
- `SEGMENT_NUMBER` (INTEGER): Monthly segment number (1, 2, 3...)
- `BUDGET_AMOUNT` (DECIMAL): Total budget for this monthly segment (in GBP/£)
- `SEGMENT_START_DATE` (DATE): Start date of monthly segment
- `SEGMENT_END_DATE` (DATE): End date of monthly segment
- `DAYS_IN_SEGMENT` (INTEGER): Number of days in segment
- `AVG_DAILY_BUDGET` (DECIMAL): Average daily budget for the segment (in GBP/£)
- `SEGMENT_STATUS` (VARCHAR): Budget segment status (e.g., "CURRENT")

**Common Query Patterns**:
```sql
-- All budgets for a specific month
SELECT 
    IO_NAME,
    BUDGET_AMOUNT,
    SEGMENT_START_DATE,
    SEGMENT_END_DATE,
    AVG_DAILY_BUDGET
FROM reports.multi_agent.DV360_BUDGETS_QUIZ
WHERE EXTRACT(MONTH FROM SEGMENT_START_DATE) = 1 
    AND EXTRACT(YEAR FROM SEGMENT_START_DATE) = 2026
ORDER BY SEGMENT_START_DATE DESC

-- Total budget across all IOs
SELECT 
    IO_NAME,
    SUM(BUDGET_AMOUNT) as TOTAL_BUDGET
FROM reports.multi_agent.DV360_BUDGETS_QUIZ
GROUP BY IO_NAME
ORDER BY TOTAL_BUDGET DESC

-- Current month budgets
SELECT * 
FROM reports.multi_agent.DV360_BUDGETS_QUIZ
WHERE SEGMENT_START_DATE <= CURRENT_DATE()
    AND SEGMENT_END_DATE >= CURRENT_DATE()
ORDER BY SEGMENT_START_DATE DESC
```

---

## Snowflake SQL Syntax Notes

### Date Functions
- Use `EXTRACT(MONTH FROM date_column)` and `EXTRACT(YEAR FROM date_column)` for month/year filtering
- Use `CURRENT_DATE()` for today's date
- Date comparisons: `date >= '2026-01-01'` (use YYYY-MM-DD format)

### Aggregations
- `SUM()` for totals
- `COUNT(DISTINCT column)` for unique counts
- `AVG()` for averages
- Always use `GROUP BY` when aggregating

### Filtering
- **ALWAYS filter `advertiser = 'Quiz'`** for `ALL_PERFORMANCE_AGG` and `creative_name_agg`
- **NO advertiser filter needed** for `DV360_BUDGETS_QUIZ` (already Quiz-specific)
- Use `LIKE '%pattern%'` for partial string matching
- Use `IS NOT NULL` to exclude NULL values

### Ordering
- Always include `ORDER BY` for consistent results
- Common: `ORDER BY date DESC`, `ORDER BY spend_gbp DESC`, `ORDER BY SEGMENT_START_DATE DESC`

---

## Currency

**All financial values are in BRITISH POUNDS (GBP/£)**:
- `spend_gbp` - Spend in GBP
- `total_revenue_gbp_pm` - Revenue in GBP
- `BUDGET_AMOUNT` - Budget in GBP
- `AVG_DAILY_BUDGET` - Daily budget in GBP

Always format amounts as £X,XXX.XX or specify "GBP" when presenting results.

---

## Agent-Specific Table Usage

### Performance Agent
- **Primary Table**: `reports.reporting_revamp.ALL_PERFORMANCE_AGG`
- **Focus**: IO-level aggregations (group by `insertion_order`)
- **Metrics**: Impressions, clicks, conversions, spend, revenue, CTR, ROAS

### Audience Agent
- **Primary Table**: `reports.reporting_revamp.ALL_PERFORMANCE_AGG`
- **Focus**: Line item level (group by `insertion_order`, `line_item`)
- **Metrics**: Segment performance, audience comparison

### Creative Agent
- **Primary Table**: `reports.reporting_revamp.creative_name_agg`
- **Focus**: Creative name and size performance
- **Metrics**: Creative-level CTR, CVR, spend, impressions

### Budget Agent
- **Primary Table**: `reports.multi_agent.DV360_BUDGETS_QUIZ`
- **Focus**: Monthly budget segments
- **Metrics**: Budget amounts, pacing, daily averages

