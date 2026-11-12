# Viva guide

Place story uses equal weights, observed temperatures by dominant land type, and five hotspot actions. The cooling scenario and held-out neighbourhood checks are in About. Questions 2, 5–7 and 9 also cover methods from the earlier expert dashboard.

1. **What does a high exposure score mean?** A cell combines relatively high heat, NO₂ or green deficit with a relatively high residential population rank. Ranks are recalculated for the selected area and time window. The score is a screening measure, with no physical dose unit.

2. **Why use Landsat for the map and MODIS for trends?** Landsat resolves finer surface patterns. Its native thermal observations are roughly 100 m even when supplied on a 30 m grid. MODIS provides a consistent 8-day record of daytime and nighttime surface temperatures at about 1 km. Cloud gaps affect both.

3. **Can a 250 m cell reveal street-level NO₂?** Sentinel-5P measures a tropospheric column in mol/m² over a much larger footprint. Several planner cells can share essentially the same observation. Estimating breathing-level concentration would require additional data and modeling.

4. **How are the grid, population and missing cells handled?** Square cells in a local metric projection are clipped to the circular ROI. Earth Engine processes at most 500 cells per batch. Native-grid WorldPop counts are summed with fractional edge support. A masked population stays missing; a valid zero remains zero. Coverage is area-weighted, so small boundary fragments do not count as full squares.

5. **What makes a hotspot robust?** The earlier dashboard computed equal, heat-forward, air-forward and green-deficit-forward scores. Each forward scheme doubles one factor’s weight. A cell qualifies when its population-weighted score reaches the top quintile under every scheme. Spearman correlations summarize agreement between rankings.

6. **How do you check whether the forest generalizes?** The target is observed LST. Predictors are Dynamic World fractions, NDVI, NDBI, MNDWI, elevation and slope. Entire 2 km blocks are held out together across up to five folds. Pooled held-out R² and RMSE measure spatial predictive skill. NO₂ and the exposure score are excluded from the predictors.

7. **How should a per-cell SHAP value be read?** A signed contribution shifts the fitted prediction above or below the model baseline in °C. Contributions plus baseline reproduce the fitted LST. The global summary averages absolute contributions over up to 2,000 cells. Shared information between predictors limits causal interpretation.

8. **What does “convert 25%” mean, and how uncertain is the result?** If bare cover is 40%, the transfer is 10 percentage points of cell area. Tree cover rises by the same amount, preserving the composition. The model compares the paired predictions with other inputs fixed. A 95% interval summarizes 100 spatial-block bootstrap refits. Site access, tree survival and real cooling still need field evidence.

9. **How are seasonality, missing months and lockdown handled?** STL estimates the annual seasonal cycle. Short interior gaps can support STL fitting, while Sen’s slope and Mann–Kendall use observed deseasonalized months. Slopes are annualized using calendar spacing. Shading marks 2020 as context; lockdown timing varied, and the analysis does not estimate its causal effect.

10. **What can you demonstrate if Earth Engine is unavailable?** Both city presets contain satellite-derived observations in Parquet. The story, numbered map, land-type and monthly charts, planting estimates and two-place comparison work offline after installation. Live requests add authentication, input and grid limits, bounded batches, cache limits, a shared cooldown and bounded retries. WorldPop’s fixed 2020 baseline and variable live latency remain limitations.

**Why compare the hottest tenth with its own area?** Central Delhi and Bengaluru have different climates. Subtracting each place’s average highlights local contrast. Compare also checks Landsat against MODIS in the same summer months; central Delhi differed by 7.5 °C with six valid MODIS months.
