
    
    select
      count(*) as failures,
      count(*) != 0 as should_warn,
      count(*) != 0 as should_error
    from (
      
    
  
    
    



select total_generation_mwh
from `my-project-1-480817`.`energy_dw_staging`.`stg_fact_generation_price`
where total_generation_mwh is null



  
  
      
    ) dbt_internal_test