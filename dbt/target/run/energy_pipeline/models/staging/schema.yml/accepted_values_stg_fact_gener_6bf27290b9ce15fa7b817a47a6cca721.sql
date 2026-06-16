
    
    select
      count(*) as failures,
      count(*) != 0 as should_warn,
      count(*) != 0 as should_error
    from (
      
    
  
    
    

with all_values as (

    select
        season as value_field,
        count(*) as n_records

    from `my-project-1-480817`.`energy_dw_staging`.`stg_fact_generation_price`
    group by season

)

select *
from all_values
where value_field not in (
    'Winter','Spring','Summer','Autumn'
)



  
  
      
    ) dbt_internal_test