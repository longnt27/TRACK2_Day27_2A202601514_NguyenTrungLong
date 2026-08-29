with completed_orders as (
    select *
    from {{ ref('stg_orders') }}
    where status = 'completed'
),
active_customers as (
    -- SCD dimensions occasionally contain duplicate active versions during a
    -- bad load. Revenue grain must not multiply because of that dimension bug.
    select distinct customer_id
    from {{ ref('stg_customers') }}
    where is_active = true
)
select
    o.order_date,
    count(*) as completed_order_rows,
    sum(o.amount_usd) as daily_revenue
from completed_orders o
left join active_customers c
    on o.customer_id = c.customer_id
group by 1
order by 1
