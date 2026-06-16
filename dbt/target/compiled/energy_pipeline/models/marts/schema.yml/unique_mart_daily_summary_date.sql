
    
    

with dbt_test__target as (

  select date as unique_field
  from `my-project-1-480817`.`energy_dw_marts`.`mart_daily_summary`
  where date is not null

)

select
    unique_field,
    count(*) as n_records

from dbt_test__target
group by unique_field
having count(*) > 1


