
    
    

with all_values as (

    select
        price_band as value_field,
        count(*) as n_records

    from `my-project-1-480817`.`energy_dw_marts`.`mart_hourly_energy`
    group by price_band

)

select *
from all_values
where value_field not in (
    'Negative','Low (0–50)','Medium (50–100)','High (100–200)','Very High (>200)'
)


