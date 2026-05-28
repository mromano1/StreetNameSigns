# StreetNameSigns

This project explores the use of 360-degree imagery, LiDAR point cloud data and machine learning to help identify signs in need of repair. These are the types of sign distress we will be seeking with machine learning.

## Missing sign:
<picture>
 <source media="(prefers-color-scheme: dark)" srcset="readme Images/image001.jpg">
 <source media="(prefers-color-scheme: light)" srcset="readme Images/image001.jpg">
 <img alt="Image001" src="readme Images/image001.jpg" width="300" height="200">
</picture>
 
<picture>
 <source media="(prefers-color-scheme: dark)" srcset="readme Images/image002.jpg">
 <source media="(prefers-color-scheme: light)" srcset="readme Images/image002.jpg">
 <img alt="Image002" src="readme Images/image002.jpg" width="300" height="200">
</picture>
 
<picture>
 <source media="(prefers-color-scheme: dark)" srcset="readme Images/image003.jpg">
 <source media="(prefers-color-scheme: light)" srcset="readme Images/image003.jpg">
 <img alt="Image003" src="readme Images/image003.jpg" width="300" height="200">
</picture>

## Sign bent/damaged:
<picture>
 <source media="(prefers-color-scheme: dark)" srcset="readme Images/image004.jpg">
 <source media="(prefers-color-scheme: light)" srcset="readme Images/image004.jpg">
 <img alt="Image004" src="readme Images/image004.jpg" width="300" height="200">
</picture>

<picture>
 <source media="(prefers-color-scheme: dark)" srcset="readme Images/image005.jpg">
 <source media="(prefers-color-scheme: light)" srcset="readme Images/image005.jpg">
 <img alt="Image005" src="readme Images/image005.jpg" width="300" height="200">
</picture>
 
<picture>
 <source media="(prefers-color-scheme: dark)" srcset="readme Images/image006.jpg">
 <source media="(prefers-color-scheme: light)" srcset="readme Images/image006.jpg">
 <img alt="Image006" src="readme Images/image006.jpg" width="300" height="200">
</picture>

## Old design with white border and all capital letters.
<picture>
 <source media="(prefers-color-scheme: dark)" srcset="readme Images/image007.jpg">
 <source media="(prefers-color-scheme: light)" srcset="readme Images/image007.jpg">
 <img alt="Image007" src="readme Images/image007.jpg" width="300" height="200">
</picture>

<picture>
 <source media="(prefers-color-scheme: dark)" srcset="readme Images/image008.jpg">
 <source media="(prefers-color-scheme: light)" srcset="readme Images/image008.jpg">
 <img alt="Image008" src="readme Images/image008.jpg" width="300" height="200">
</picture>
 
<picture>
 <source media="(prefers-color-scheme: dark)" srcset="readme Images/image009.jpg">
 <source media="(prefers-color-scheme: light)" srcset="readme Images/image009.jpg">
 <img alt="Image009" src="readme Images/image009.jpg" width="300" height="200">
</picture>

## Faded sign:
<picture>
 <source media="(prefers-color-scheme: dark)" srcset="readme Images/image010.jpg">
 <source media="(prefers-color-scheme: light)" srcset="readme Images/image010.jpg">
 <img alt="Image010" src="readme Images/image010.jpg" width="300" height="200">
</picture>

<picture>
 <source media="(prefers-color-scheme: dark)" srcset="readme Images/image011.jpg">
 <source media="(prefers-color-scheme: light)" srcset="readme Images/image011.jpg">
 <img alt="Image011" src="readme Images/image011.jpg" width="300" height="200">
</picture>
 
## Hanging sign:
<picture>
 <source media="(prefers-color-scheme: dark)" srcset="readme Images/image012.jpg">
 <source media="(prefers-color-scheme: light)" srcset="readme Images/image012.jpg">
 <img alt="Image012" src="readme Images/image012.jpg" width="300" height="200">
</picture> 

## Vandalized:
<picture>
 <source media="(prefers-color-scheme: dark)" srcset="readme Images/image013.jpg">
 <source media="(prefers-color-scheme: light)" srcset="readme Images/image013.jpg">
 <img alt="Image013" src="readme Images/image013.jpg" width="300" height="200">
</picture> 
  
## Red Flagged (sign facing wrong direction)
<picture>
 <source media="(prefers-color-scheme: dark)" srcset="readme Images/image014.jpg">
 <source media="(prefers-color-scheme: light)" srcset="readme Images/image014.jpg">
 <img alt="Image014" src="readme Images/image014.jpg" width="300" height="200">
</picture> 

<picture>
 <source media="(prefers-color-scheme: dark)" srcset="readme Images/image015.jpg">
 <source media="(prefers-color-scheme: light)" srcset="readme Images/image015.jpg">
 <img alt="Image015" src="readme Images/image015.jpg" width="300" height="200">
</picture> 

## Incomplete Intersections
In addition, this project identifies any T intersections with fewer than one complete set of signs (two signs total) and any other intersections with fewer than two complete sets of signs, four signs total.  

All street name signs are tracked in NYC DOT's Street Information Management Systems (SIMS) by filtering for “ST” under order type.This data is available online via [NYC Open Data](https://data.cityofnewyork.us/Transportation/Street-Sign-Work-Orders/qt6m-xctn/explore/query/SELECT%0A%20%20%60order_number%60%2C%0A%20%20%60record_type%60%2C%0A%20%20%60order_type%60%2C%0A%20%20%60borough%60%2C%0A%20%20%60on_street%60%2C%0A%20%20%60on_street_suffix%60%2C%0A%20%20%60from_street%60%2C%0A%20%20%60from_street_suffix%60%2C%0A%20%20%60to_street%60%2C%0A%20%20%60to_street_suffix%60%2C%0A%20%20%60side_of_street%60%2C%0A%20%20%60order_completed_on_date%60%2C%0A%20%20%60sign_code%60%2C%0A%20%20%60sign_description%60%2C%0A%20%20%60sign_size%60%2C%0A%20%20%60sign_design_voided_on_date%60%2C%0A%20%20%60sign_location%60%2C%0A%20%20%60distance_from_intersection%60%2C%0A%20%20%60arrow_direction%60%2C%0A%20%20%60facing_direction%60%2C%0A%20%20%60sheeting_type%60%2C%0A%20%20%60support%60%2C%0A%20%20%60sign_notes%60%2C%0A%20%20%60sign_x_coord%60%2C%0A%20%20%60sign_y_coord%60%0AWHERE%20caseless_one_of%28%60order_type%60%2C%20%22ST%22%29/page/filter).

