
    
    select
      count(*) as failures,
      count(*) != 0 as should_warn,
      count(*) != 0 as should_error
    from (
      
    
  
    
    



select renewable_share_bucket
from `my-project-1-480817`.`energy_dw_marts`.`mart_renewable_price_correlation`
where renewable_share_bucket is null



  
  
      
    ) dbt_internal_test