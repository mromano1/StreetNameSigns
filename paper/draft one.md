# Title Page

TDB

# Introduction

Transportation agencies are increasingly seeking scalable and automated methods for monitoring roadway assets due to the high costs and operational limitations associated with manual inspections. Street signs are critical transportation assets that support roadway safety, traffic operations, navigation, and regulatory enforcement. Damage to street signs—including fading, bending, obstruction, vandalism, and structural deformation—can negatively affect visibility, readability, and compliance with the Manual on Uniform Traffic Control Devices (MUTCD). Traditional inspection methods rely heavily on labor-intensive field surveys, which are difficult to conduct at citywide scales and often result in delayed maintenance responses.

Recent advances in computer vision, geospatial artificial intelligence (GeoAI), and mobile mapping technologies provide new opportunities for automated infrastructure inspection. In particular, deep learning object detection models such as YOLO (You Only Look Once) have demonstrated strong performance in real-time transportation asset recognition tasks. Simultaneously, high-density LiDAR and point cloud datasets enable geometric analysis of roadway infrastructure in three-dimensional space.

This study proposes a multimodal methodology for detecting damaged street signs using street-level imagery, point cloud data, and a YOLO26 object detection framework. The methodology integrates geospatial sign inventories from NYC Open Data with image-based deep learning and LiDAR-derived structural analysis to improve detection accuracy and reduce false positives. The workflow is designed to support scalable asset management operations within large urban transportation agencies such as the New York City Department of Transportation (NYC DOT).

# Methods

This study will use a pilot-neighborhood workflow to develop and evaluate a prototype model before expanding to larger areas. The prototype will combine street-level imagery, LiDAR or point cloud data, and NYC DOT sign inventory records where available. The first pilot neighborhood will be selected based on imagery availability, point cloud coverage, visible street name signs, and the likelihood of observing multiple damage categories.

The machine learning task will be treated as object detection plus multi-label damage classification. Each visible street name sign will be annotated with a bounding box, location metadata, and zero or more damage labels. Undamaged signs will be included as negative training examples, although the final prototype output will only return signs with detected damage. Damage categories will include missing signs, bent or damaged signs, old-design signs, faded signs, hanging signs, vandalized signs, signs facing the wrong direction, and incomplete intersections.

The initial model will use a YOLO object detection workflow because YOLO supports bounding-box detection, confidence scores, and annotated visual outputs suitable for weekly demos and the August conference prototype. TensorFlow-based object detection models may be considered as an alternative or comparison path if required by the project team.

The labeled dataset will be split into training and test sets using an 80/20 split. Images from the same intersection or sign location should be kept in the same split when possible to reduce data leakage. Model outputs will be evaluated for sign detection, damage-label accuracy, false positives, and location quality. Confidence intervals will be reported when the test sample size is large enough to make them meaningful.

# Analysis and Results

The first analysis will report progress on the pilot dataset and prototype model rather than citywide performance. Expected outputs include the number of labeled images, the number of annotated signs, the number of examples per damage category, and the number of undamaged negative examples.

The model will produce annotated images and a CSV/table of damaged-sign detections. Each returned record should include the source image or point cloud record, estimated latitude and longitude, bounding box coordinates, damage labels, model confidence, and review notes. Signs with no detected damage will not be included in the final damaged-sign output table.

Evaluation metrics will include detection performance, damage-label precision and recall, and a qualitative review of location accuracy. The analysis will also identify categories with insufficient examples so the scope can expand as more data are collected.

# Discussion and Conclusions

This methodology presents a scalable framework for automated street sign damage detection using multimodal geospatial and computer vision data sources. By integrating NYC Open Data sign inventories, street-level imagery, LiDAR-derived point clouds, and YOLO26 deep learning models, the framework enables proactive and data-driven transportation asset management.

The proposed workflow supports improved inspection efficiency, reduced operational costs, and enhanced roadway safety outcomes. The methodology further demonstrates the growing applicability of GeoAI and multimodal sensing technologies within transportation infrastructure management and smart city operations.

The first conference prototype is expected to demonstrate feasibility rather than full production readiness. A successful August demo should show a small but complete pipeline from data selection and annotation to model inference and mapped or tabular damaged-sign outputs. Future work will expand the pilot area, increase the number of labeled examples, compare model families, and improve location estimation using point cloud geometry.

# References

1. Chen, T., & Ren, J. (2023). *MFL-YOLO: An object detection model for damaged traffic signs*. arXiv. https://doi.org/10.48550/arXiv.2309.06750. Open-access article: https://arxiv.org/pdf/2309.06750.pdf

2. Flores-Calero, M., Astudillo, C. A., Guevara, D., Maza, J., Lita, B. S., Defaz, B., Ante, J. S., Zabala-Blanco, D., & Armingol Moreno, J. M. (2024). Traffic sign detection and recognition using YOLO object detection algorithm: A systematic review. *Mathematics, 12*(2), 297. https://doi.org/10.3390/math12020297. Open-access article: https://www.mdpi.com/2227-7390/12/2/297/pdf

3. Zhang, F., Zhang, L., & Wang, Y. (2023). Extracting traffic signage by combining point clouds and images. *Sensors, 23*(4), 2262. https://doi.org/10.3390/s23042262. Open-access article: https://www.mdpi.com/1424-8220/23/4/2262/pdf

4. Ahn, Y., Munjy, R., & Li, Z. (2024). *Traffic sign extraction from mobile LiDAR point cloud* (Report No. 24-07; CA-MTI-2354). Mineta Transportation Institute. https://doi.org/10.31979/mti.2024.2354. Open-access article: https://rosap.ntl.bts.gov/view/dot/75693/dot_75693_DS1.pdf

5. Soilán, M., Riveiro, B., Martínez-Sánchez, J., & Arias, P. (2016). Traffic sign detection in MLS acquired point clouds for geometric and image-based semantic inventory. *ISPRS Journal of Photogrammetry and Remote Sensing, 114*, 92–101. https://doi.org/10.1016/j.isprsjprs.2016.01.019. Open-access article: https://www.researchgate.net/publication/292970949_Traffic_sign_detection_in_MLS_acquired_point_clouds_for_geometric_and_image-based_semantic_inventory

6. Li, M., Zhang, Y., & Wang, H. (2022). YOLO-based traffic sign recognition algorithm. *Computational Intelligence and Neuroscience*, 2022, Article 6719384. https://doi.org/10.1155/2022/6719384. Open-access article: https://pmc.ncbi.nlm.nih.gov/articles/PMC9365537/pdf/CIN2022-6719384.pdf

7. Wang, C., Liu, H., & Zhao, Y. (2025). Efficient traffic sign recognition using YOLO for intelligent transportation systems. *Scientific Reports, 15*, Article 98111. https://doi.org/10.1038/s41598-025-98111-y. Open-access article: https://www.nature.com/articles/s41598-025-98111-y.pdf

8. Zhang, H., Li, Y., & Xu, P. (2025). A traffic sign detection algorithm based on YOLOv8. *Scientific Reports, 15*, Article 88184. https://doi.org/10.1038/s41598-025-88184-0. Open-access article: https://www.nature.com/articles/s41598-025-88184-0.pdf

9. Liu, C. (2025). *Automated traffic sign recognition using computer vision and deep learning methodologies*. Washington State Transportation Center (TRAC). https://depts.washington.edu/trac/bulkdisk/pdf/946.1.pdf. Open-access article: https://depts.washington.edu/trac/bulkdisk/pdf/946.1.pdf

10. Zaki, P. S., William, M. M., Soliman, B. K., Alexsan, K. G., Khalil, K., & El-Moursy, M. (2020). *Traffic signs detection and recognition system using deep learning*. arXiv. https://doi.org/10.48550/arXiv.2003.03256. Open-access article: https://arxiv.org/pdf/2003.03256.pdf
