
    
    select
      count(*) as failures,
      count(*) != 0 as should_warn,
      count(*) != 0 as should_error
    from (
      
    
  
    
    



select renewable_share_pct
from `my-project-1-480817`.`energy_dw_marts`.`mart_hourly_energy`
where renewable_share_pct is null



  
  
      
    ) dbt_internal_test