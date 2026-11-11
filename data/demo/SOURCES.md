# Offline Earth Engine snapshots

Delhi airport district (28.55° N, 77.10° E) and central Bengaluru (12.97° N, 77.59° E) each cover a 5 km radius on a 500 m clipped grid. Cell files contain the live summer extraction for 2019–2021. Monthly files contain all 36 months in the same years. The application computes scores and fits models locally from these observations.

Cell measurements use USGS Landsat 8/9 Collection 2 surface temperature, Copernicus Sentinel-5P OFFL NO₂, harmonized Sentinel-2 surface reflectance with Google Cloud Score+, Dynamic World, 2020 WorldPop counts and NASA SRTM terrain. Monthly temperatures come from Terra MOD11A2. [Earth Engine Data Catalog](https://developers.google.com/earth-engine/datasets)

Dynamic World is produced by Google in partnership with National Geographic Society and the World Resources Institute and contains modified Copernicus Sentinel data. [Dynamic World attribution](https://developers.google.com/earth-engine/datasets/catalog/GOOGLE_DYNAMICWORLD_V1) · [WorldPop](https://developers.google.com/earth-engine/datasets/catalog/WorldPop_GP_100m_pop)
