# StreetNameSigns

This project explores the use of 360-degree imagery, LiDAR point cloud data and machine learning to help identify street name signs in need of repair. The near-term goal is to build a working conference prototype by August that can detect damaged street name signs, return their locations, and report all damage categories found on each sign.

The first prototype will focus on a small pilot neighborhood rather than citywide coverage. YOLO is the default model path because it supports object detection and demo-ready annotated outputs. TensorFlow-based object detection models remain an alternative if the project team decides to standardize on that toolchain.

## Project links

- Project repository: https://github.com/mromano1/StreetNameSigns
- Contributors:
  - Bilal: https://github.com/BilalBennour7
  - Karim: https://github.com/knabahi

## Prototype workflow

1. Select a pilot neighborhood with available imagery, LiDAR or point cloud coverage, and enough visible street name signs for labeling.
2. Query Google Street View metadata for candidate locations to confirm imagery availability, coordinates, panorama ID, image date, and copyright.
3. Download only the images needed for the pilot dataset after metadata checks pass.
4. Annotate street name signs with bounding boxes, location metadata, and one or more damage labels.
5. Train a YOLO object detection model using an 80/20 train/test split.
6. Evaluate detections, damage labels, location quality, and confidence scores.
7. Export only damaged signs as annotated images and a CSV/table with location, damage labels, and confidence.

```text
Candidate locations + LiDAR/point cloud + SIMS inventory
        |
        v
Google Street View metadata checks
        |
        v
Pilot image collection
        |
        v
Sign annotation: bounding box + location + damage labels
        |
        v
YOLO training and evaluation
        |
        v
Damaged sign outputs: annotated images + location table
```

## Damage labeling approach

Damage labeling is multi-label. A single sign can have more than one issue, such as being both faded and bent. Undamaged signs should still be included as negative examples during training, but the final demo output should suppress signs with no detected damage.

## Street View metadata

Google Street View metadata requests can be used before downloading images. The metadata request checks whether imagery exists near a location and can return latitude, longitude, panorama ID, image date, copyright, and request status. Metadata requests are free, while Street View image requests consume quota.

Store the original address or latitude/longitude used for the request. Panorama IDs can change over time, so they should not be treated as permanent identifiers.

These are the types of sign distress we will be seeking with machine learning.

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

All street name signs are tracked in NYC DOT's Street Information Management Systems (SIMS) by filtering for “ST” under order type. This data is available online via [NYC Open Data](https://data.cityofnewyork.us/Transportation/Street-Sign-Work-Orders/qt6m-xctn/about_data).
