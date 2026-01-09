"""
Example Dagster Project Using Lambda Components

This shows how to structure a real Dagster project that loads
Lambda-backed assets and jobs from YAML components.
"""

import dagster as dg

# Load all component YAML files from the components directory
# This automatically discovers and loads all .yaml files
defs = dg.Definitions.from_yaml_directory("components")

# Alternative: Load specific component files
# defs = dg.Definitions(
#     assets=[
#         dg.Definitions.from_yaml_file("components/daily_metrics.yaml").assets,
#         dg.Definitions.from_yaml_file("components/regional_reports.yaml").assets,
#     ],
#     jobs=[
#         dg.Definitions.from_yaml_file("components/etl_pipeline.yaml").jobs,
#     ],
# )
