
    
    

with dbt_test__target as (

  select interval_start_utc as unique_field
  from `my-project-1-480817`.`energy_dw_marts`.`mart_hourly_energy`
  where interval_start_utc is not null

)

select
    unique_field,
    count(*) as n_records

from dbt_test__target
group by unique_field
having count(*) > 1


