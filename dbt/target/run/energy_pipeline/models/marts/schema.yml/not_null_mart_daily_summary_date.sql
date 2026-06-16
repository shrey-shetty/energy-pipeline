
    
    select
      count(*) as failures,
      count(*) != 0 as should_warn,
      count(*) != 0 as should_error
    from (
      
    
  
    
    



select date
from `my-project-1-480817`.`energy_dw_marts`.`mart_daily_summary`
where date is null



  
  
      
    ) dbt_internal_test