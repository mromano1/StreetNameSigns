# Title Page

TDB

# Introduction

Transportation agencies are increasingly seeking scalable and automated methods for monitoring roadway assets due to the high costs and operational limitations associated with manual inspections. Street signs are critical transportation assets that support roadway safety, traffic operations, navigation, and regulatory enforcement. Damage to street signs—including fading, bending, obstruction, vandalism, and structural deformation—can negatively affect visibility, readability, and compliance with the Manual on Uniform Traffic Control Devices (MUTCD). Traditional inspection methods rely heavily on labor-intensive field surveys, which are difficult to conduct at citywide scales and often result in delayed maintenance responses.

Recent advances in computer vision, geospatial artificial intelligence (GeoAI), and mobile mapping technologies provide new opportunities for automated infrastructure inspection. In particular, deep learning object detection models such as YOLO (You Only Look Once) have demonstrated strong performance in real-time transportation asset recognition tasks. Simultaneously, high-density LiDAR and point cloud datasets enable geometric analysis of roadway infrastructure in three-dimensional space.

This study proposes a multimodal methodology for detecting damaged street signs using street-level imagery, point cloud data, and a YOLO26 object detection framework. The methodology integrates geospatial sign inventories from NYC Open Data with image-based deep learning and LiDAR-derived structural analysis to improve detection accuracy and reduce false positives. The workflow is designed to support scalable asset management operations within large urban transportation agencies such as the New York City Department of Transportation (NYC DOT).

# Methods

# Analysis and Results

# Discussion and Conclusions

This methodology presents a scalable framework for automated street sign damage detection using multimodal geospatial and computer vision data sources. By integrating NYC Open Data sign inventories, street-level imagery, LiDAR-derived point clouds, and YOLO26 deep learning models, the framework enables proactive and data-driven transportation asset management.

The proposed workflow supports improved inspection efficiency, reduced operational costs, and enhanced roadway safety outcomes. The methodology further demonstrates the growing applicability of GeoAI and multimodal sensing technologies within transportation infrastructure management and smart city operations.

# References

- Chen, T., & Ren, J. (2023). *MFL-YOLO: An object detection model for damaged traffic signs*. arXiv. https://doi.org/10.48550/arXiv.2309.06750. Open-access article: https://arxiv.org/pdf/2309.06750.pdf

- Flores-Calero, M., Astudillo, C. A., Guevara, D., Maza, J., Lita, B. S., Defaz, B., Ante, J. S., Zabala-Blanco, D., & Armingol Moreno, J. M. (2024). Traffic sign detection and recognition using YOLO object detection algorithm: A systematic review. *Mathematics, 12*(2), 297. https://doi.org/10.3390/math12020297. Open-access article: https://www.mdpi.com/2227-7390/12/2/297/pdf

Zhang, F., Zhang, L., & Wang, Y. (2023). Extracting traffic signage by combining point clouds and images. *Sensors, 23*(4), 2262. https://doi.org/10.3390/s23042262. Open-access article: https://www.mdpi.com/1424-8220/23/4/2262/pdf

Ahn, Y., Munjy, R., & Li, Z. (2024). *Traffic sign extraction from mobile LiDAR point cloud* (Report No. 24-07; CA-MTI-2354). Mineta Transportation Institute. https://doi.org/10.31979/mti.2024.2354. Open-access article: https://rosap.ntl.bts.gov/view/dot/75693/dot_75693_DS1.pdf

Soilán, M., Riveiro, B., Martínez-Sánchez, J., & Arias, P. (2016). Traffic sign detection in MLS acquired point clouds for geometric and image-based semantic inventory. *ISPRS Journal of Photogrammetry and Remote Sensing, 114*, 92–101. https://doi.org/10.1016/j.isprsjprs.2016.01.019. Open-access article: https://www.researchgate.net/publication/292970949_Traffic_sign_detection_in_MLS_acquired_point_clouds_for_geometric_and_image-based_semantic_inventory

Li, M., Zhang, Y., & Wang, H. (2022). YOLO-based traffic sign recognition algorithm. *Computational Intelligence and Neuroscience*, 2022, Article 6719384. https://doi.org/10.1155/2022/6719384. Open-access article: https://pmc.ncbi.nlm.nih.gov/articles/PMC9365537/pdf/CIN2022-6719384.pdf

Wang, C., Liu, H., & Zhao, Y. (2025). Efficient traffic sign recognition using YOLO for intelligent transportation systems. *Scientific Reports, 15*, Article 98111. https://doi.org/10.1038/s41598-025-98111-y. Open-access article: https://www.nature.com/articles/s41598-025-98111-y.pdf

Zhang, H., Li, Y., & Xu, P. (2025). A traffic sign detection algorithm based on YOLOv8. *Scientific Reports, 15*, Article 88184. https://doi.org/10.1038/s41598-025-88184-0. Open-access article: https://www.nature.com/articles/s41598-025-88184-0.pdf

Liu, C. (2025). *Automated traffic sign recognition using computer vision and deep learning methodologies*. Washington State Transportation Center (TRAC). https://depts.washington.edu/trac/bulkdisk/pdf/946.1.pdf. Open-access article: https://depts.washington.edu/trac/bulkdisk/pdf/946.1.pdf

Zaki, P. S., William, M. M., Soliman, B. K., Alexsan, K. G., Khalil, K., & El-Moursy, M. (2020). *Traffic signs detection and recognition system using deep learning*. arXiv. https://doi.org/10.48550/arXiv.2003.03256. Open-access article: https://arxiv.org/pdf/2003.03256.pdf
