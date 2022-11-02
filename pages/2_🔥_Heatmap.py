import streamlit as st
import leafmap.foliumap as leafmap
from db import get_data


st.set_page_config(layout="wide")

st.title("Heatmap")

feature_list_sql = """
select column_name from information_schema.columns
where table_schema = 'postamat'
and table_catalog = current_database()
and table_name = 'platform_features'
and ordinal_position > 2
and data_type = 'double precision'
"""


column_name = st.selectbox("Feature", [x[0] for x in get_data(feature_list_sql)])
radius = st.slider("Radius", min_value=2, max_value=50, step=2, value=12)

sql = """
select
       st_y(st_centroid(geometry)) lat,
       st_x(st_centroid(geometry)) lon,
       pf.{column_name}
from postamat.platform_features pf,
     postamat.platform_isochrones pi
where 1=1
    and pf.geo_h3_10 = pi.geo_h3_10
    and pf.kind = pi.kind
    and pf.kind = 'walking_5min'
    and pf.{column_name} > 0
"""


m = leafmap.Map(center=[55.7, 37.7], zoom=9, tiles="openstreetmap")
m.add_heatmap(
    get_data(sql.format(column_name=column_name)),
    latitude="lon",
    longitude="lat",
    value="population",
    name="Heat map",
    radius=radius,
)

m.to_streamlit(height=700)
