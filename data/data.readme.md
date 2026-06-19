# Data Workflow

This folder will document the data sources, pilot area, annotation rules, and dataset splits for the street name sign damage detection prototype.

## Data goals

The first dataset should support a small, complete model demo by August. It should include enough labeled examples to train and test a model that detects street name signs, identifies damage categories, and returns sign locations.

## Planned data sources

- **Street-level imagery:** primary visual source for sign detection and visible damage labeling.
- **Google Street View metadata:** availability check for candidate image locations, including matched coordinates, panorama ID, photo date, copyright, and request status.
- **LiDAR or point cloud data:** source for 3D location, sign geometry, orientation, and structural context if available.
- **NYC DOT SIMS/Open Data:** inventory and work-order context for street name signs, filtered for street name sign records where applicable.
- **Manual review:** human annotation for bounding boxes, damage labels, no-damage examples, and uncertainty notes.

The exact Google imagery, LiDAR, or point cloud source still needs to be confirmed with the project team, including access permissions, API key ownership, usage limits, and whether source metadata includes usable coordinates.

## Pilot neighborhood selection

Choose one neighborhood for the first prototype. The neighborhood should have:

- accessible imagery and LiDAR or point cloud coverage;
- enough visible street name signs for labeling;
- examples of several damage categories;
- manageable geographic size for weekly progress;
- clear source metadata for estimating sign location.

The first neighborhood choice should be documented before labeling begins.

## Damage categories

Use the categories already shown in the project README:

- missing sign;
- bent or damaged sign;
- old design with white border and all capital letters;
- faded sign;
- hanging sign;
- vandalized sign;
- red flagged or facing wrong direction;
- incomplete intersection.

Labels are multi-label. A single sign can have more than one damage category. Signs with no visible damage should be labeled as undamaged negative examples for training, even though the final damaged-sign output should not return them.

## Annotation schema

| Field | Required | Description |
| --- | --- | --- |
| `annotation_id` | Yes | Unique ID for the annotation. |
| `source_id` | Yes | Image, frame, point cloud tile, or source record ID. |
| `image_path` | Yes | Relative path or source URI for the image used in labeling. |
| `request_location` | Yes | Original address or latitude/longitude used to request Street View metadata. |
| `pano_id` | No | Current Google Street View panorama ID, if available; do not use as the only permanent identifier. |
| `image_date` | No | Street View image date when returned by metadata. |
| `copyright` | No | Copyright/source text returned by metadata. |
| `metadata_status` | Yes | Google metadata status, such as `OK` or `ZERO_RESULTS`. |
| `latitude` | Yes | Sign latitude if known or estimated. |
| `longitude` | Yes | Sign longitude if known or estimated. |
| `location_method` | Yes | Direct source metadata, point cloud estimate, inventory match, or manual estimate. |
| `bbox_xmin` | Yes | Left edge of the sign bounding box. |
| `bbox_ymin` | Yes | Top edge of the sign bounding box. |
| `bbox_xmax` | Yes | Right edge of the sign bounding box. |
| `bbox_ymax` | Yes | Bottom edge of the sign bounding box. |
| `damage_labels` | Yes | List of damage categories; empty only for undamaged signs. |
| `is_undamaged` | Yes | True when the sign is intentionally labeled as a negative example. |
| `confidence_notes` | No | Notes about blur, occlusion, uncertain location, or uncertain damage type. |
| `annotator` | No | Person or process that created the annotation. |

## Train/test split

Use an 80/20 train/test split for the first prototype. When possible, keep images from the same intersection or sign location in the same split so the model is tested on locations it has not already seen.

Track the number of examples per damage category before training. If a category has too few examples, mark it as a future expansion category rather than forcing it into the first model.

## Street View collection notes

Use Google Street View metadata requests before downloading images. Metadata checks are useful for confirming whether imagery exists at a candidate location and for recording matched latitude/longitude, image date, panorama ID, and copyright. Image downloads should happen only after the metadata status is `OK`.

Do not rely on panorama ID as the only saved location reference because panorama IDs can change over time. Save the original request address or coordinates so a changed panorama can be refreshed later.

## First deliverable checklist

- Confirm the exact imagery and LiDAR or point cloud source.
- Confirm Google API key access and usage limits.
- Pick and document the pilot neighborhood.
- Run metadata checks for candidate locations before downloading images.
- Create a small labeled sample with bounding boxes, damage labels, and location fields.
- Include undamaged signs as negative examples.
- Prepare the 80/20 split plan.
- Produce a data workflow diagram or table that can be shown in the next weekly update.
