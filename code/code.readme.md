# Code Workflow

This folder will contain scripts and notebooks for the street name sign damage detection prototype. The first implementation should prioritize a complete small pipeline over broad citywide coverage.

## Prototype goal

Build a working model workflow that can:

- detect street name signs in imagery;
- classify all visible damage categories on each detected sign;
- connect each damaged sign to a location;
- suppress signs with no detected damage from the final output;
- export annotated images and a CSV/table for review.

## Default model path

Use YOLO as the first model path because it supports object detection, bounding boxes, confidence scores, and demo-friendly annotated image outputs. TensorFlow object detection models can be evaluated later if the team prefers TensorFlow or needs a comparison baseline.

The model task should be treated as detection plus multi-label damage classification. A sign may have more than one damage label.

## Planned pipeline

1. **Collect source data**
   - Select the pilot neighborhood.
   - Build a list of candidate addresses or latitude/longitude points.
   - Query Google Street View metadata before downloading imagery.
   - Gather imagery, LiDAR or point cloud references, and location metadata for locations with available panoramas.
   - Link records to NYC DOT SIMS/Open Data where possible.

2. **Prepare annotations**
   - Label each visible street name sign with a bounding box.
   - Add zero or more damage labels.
   - Keep undamaged signs as negative examples for training.
   - Store image/source ID and location metadata with every annotation.

3. **Split data**
   - Use an 80/20 train/test split for the first prototype.
   - Keep signs from the same location in the same split when possible to reduce leakage.
   - Track category counts so rare damage labels are visible.

4. **Train model**
   - Start with a pretrained YOLO model and fine-tune on the labeled pilot dataset.
   - Save model configuration, class labels, training command, and resulting weights.
   - Record dataset version and training date for reproducibility.

5. **Evaluate model**
   - Report sign detection performance.
   - Report damage-label precision, recall, and false positives.
   - Include confidence intervals when the test set is large enough for them to be meaningful.
   - Review location quality separately from visual detection quality.

6. **Export demo outputs**
   - Save annotated images showing detected damaged signs.
   - Export a CSV/table with image/source ID, location, damage labels, confidence, and notes.
   - Exclude undamaged detections from the final damaged-sign output table.

## Expected output table

| Field | Description |
| --- | --- |
| `source_id` | Image, frame, point cloud tile, or source record ID. |
| `latitude` | Latitude for the detected or estimated sign location. |
| `longitude` | Longitude for the detected or estimated sign location. |
| `bbox_xmin` | Left edge of the sign bounding box. |
| `bbox_ymin` | Top edge of the sign bounding box. |
| `bbox_xmax` | Right edge of the sign bounding box. |
| `bbox_ymax` | Bottom edge of the sign bounding box. |
| `damage_labels` | One or more detected damage categories. |
| `confidence` | Model confidence score or combined score. |
| `notes` | Human review notes, uncertainty, or source-data issues. |

## Google Street View metadata workflow

Use metadata requests to check image availability before collecting training images. A metadata request should include either `location` or `pano`, plus the project API key. Prefer `location` for stored project records because panorama IDs can change.

Example metadata URL shape:

```text
https://maps.googleapis.com/maps/api/streetview/metadata?location=LAT,LON&key=YOUR_API_KEY
```

Save these fields when they are returned:

| Field | Use |
| --- | --- |
| `status` | Confirms whether imagery exists or why the request failed. |
| `location.lat` | Latitude of the matched panorama. |
| `location.lng` | Longitude of the matched panorama. |
| `pano_id` | Current panorama ID; useful but not permanent. |
| `date` | Image capture date when available. |
| `copyright` | Required source/copyright metadata. |

Handle these metadata statuses during collection:

| Status | Action |
| --- | --- |
| `OK` | Save metadata and consider the location for image download. |
| `ZERO_RESULTS` | Skip the point or retry with a nearby location. |
| `NOT_FOUND` | Check whether the address or coordinate is valid. |
| `OVER_QUERY_LIMIT` | Stop collection and resume later or reduce request rate. |
| `REQUEST_DENIED` | Confirm the API key and Street View Static API access. |
| `INVALID_REQUEST` | Check for missing parameters. |
| `UNKNOWN_ERROR` | Retry later. |

## Downloading pilot images

Use `collect_streetview.py` after the Google API key is available. The script reads candidate locations, checks Street View metadata, downloads images only when metadata status is `OK`, and saves a metadata table for labeling.

By default, the script downloads eight headings per location: `0`, `45`, `90`, `135`, `180`, `225`, `270`, and `315` degrees. This means 13 locations will produce up to 104 images. To override the headings, set `STREETVIEW_HEADINGS`.

1. Copy the example candidate file:

```bash
cp data/candidate_locations.example.csv data/candidate_locations.csv
```

2. Edit `data/candidate_locations.csv` so each row has a unique `location_id` and a `location` value. The `location` can be either `"latitude,longitude"` or an address.

3. Export the API key in the terminal:

```bash
export GOOGLE_MAPS_API_KEY="PASTE_KEY_HERE"
```

4. Run the collector:

```bash
python code/collect_streetview.py data/candidate_locations.csv
```

Optional custom headings:

```bash
STREETVIEW_HEADINGS="0,45,90,135,180,225,270,315" python code/collect_streetview.py data/candidate_locations.csv
```

5. Review the outputs:

```text
data/streetview/metadata.csv
data/streetview/images/
```

Only rows with metadata status `OK` should have downloaded image paths.

## Runnable prototype preparation

Use `pipeline.py` after image collection to prepare the files needed for labeling, training, and review outputs. It does not train YOLO by itself; it creates the annotation, split, and YOLO dataset files that a YOLO training command can consume.

1. Create an annotation template from downloaded Street View metadata:

```bash
python code/pipeline.py init-annotations --metadata data/streetview/metadata.csv --output data/annotations.csv
```

2. Fill `data/annotations.csv` with bounding boxes, damage labels, undamaged flags, and optional confidence notes. Damage labels use semicolons for multi-label signs:

```text
faded;bent_or_damaged
```

Supported damage labels:

```text
missing_sign
bent_or_damaged
old_design
faded
hanging
vandalized
wrong_direction
incomplete_intersection
```

3. Validate the labeled annotations:

```bash
python code/pipeline.py validate data/annotations.csv
```

4. Create an 80/20 train/test split grouped by `location_id`:

```bash
python code/pipeline.py split data/annotations.csv --output-dir data/splits
```

5. Export a YOLO-ready dataset:

```bash
python code/pipeline.py export-yolo data/splits/annotations_with_split.csv --output-dir data/yolo
```

The export writes images, labels, and `data/yolo/data.yaml`. Undamaged signs are exported as `street_name_sign`; damaged signs are exported under their damage label. If one sign has multiple damage labels, the same bounding box is written once per damage class.

6. Train and validate a YOLO model after installing `ultralytics`:

```bash
python code/train_yolo.py --data data/yolo/data.yaml --epochs 50
```

Training outputs are written under `runs/street-name-signs/`.

7. Export the damaged-sign review table for the demo:

```bash
python code/pipeline.py export-demo data/splits/annotations_with_split.csv --output data/demo_outputs/damaged_signs.csv
```

## Open implementation questions

- Which exact Google imagery, LiDAR, or point cloud source will be used for the pilot?
- Who will provide the Google API key and confirm usage limits?
- Can sign coordinates be extracted directly, or must they be estimated from source metadata?
- Which damage categories are required for the August demo?
- What minimum demo format is expected: annotated images, CSV/table, map markers, or all three?
- What accuracy threshold is acceptable for a first conference prototype?
