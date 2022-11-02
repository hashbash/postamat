import streamlit as st
import leafmap.foliumap as leafmap
import geopandas
import pandas as pd
from db import get_data
from shapely.wkt import loads
import pdfkit
import io
from PIL import Image


st.title("Лучшие локации для постаматов")

st.sidebar.subheader('Параметры')

district_types = ("Районы", "Округа")
district_type_choise = st.sidebar.radio("", district_types)

districts_sql = f"""select {"adm_name" if district_type_choise == "Районы" else "okrug_name"}, ST_AsText(geometry)
from postamat.{"adm_zones" if district_type_choise == "Районы" else "adm_okr_zones"}
"""
districts = get_data(districts_sql)
districts = pd.DataFrame(districts, columns=["district", "geometry"])
districts["geometry"] = districts["geometry"].apply(loads)
districts = geopandas.GeoDataFrame(districts, geometry="geometry", crs="EPSG:4326")

districts_choise = st.sidebar.multiselect(
    district_type_choise,
    districts["district"].values,
    [districts["district"].values[0]],
)
districts = districts[districts["district"].isin(districts_choise)]

model_types_sql = "select distinct model_type from postamat.platform_model"
model_types = [x[0] for x in get_data(model_types_sql)]
model_type_choise = st.sidebar.selectbox(
    "Модель",
    model_types,
    help='Выберите необходимую модель размещения. Логика моделей и разница между ними описана в презентации.'
)

take_top = st.sidebar.slider("Кол-во постаматов для размещения", min_value=1, max_value=1000, step=1, value=50)

object_types_sql = "select distinct purpose_name  from postamat.all_objects"
object_types = [x[0].lower() for x in get_data(object_types_sql)]
object_types_choise = st.sidebar.multiselect(
    "Объекты для размещения (NOT IMPLEMENTED)", object_types, object_types[:3]
)


m = leafmap.Map(center=[55.7, 37.7], zoom=9, tiles="stamentoner", label_visibility='collapse')
m.add_basemap(basemap="OpenStreetMap")
district_style = {"fill": True, "fillOpacity": 0.3}
if len(districts) > 0:
    m.add_gdf(
        districts,
        layer_name="Districts",
        fill_colors=["red", "green", "blue", "grey"],
        style=district_style,
    )


def get_sql_list_as_string(items):
    if len(items) == 0:
        return "('random_string')"
    return f"""{tuple(items) if len(items)> 1 else f"('{items[0]}')"}"""


model_output_sql = f"""with good_locations as 
(
 select ST_AsText(geometry) as geometry
  , cast(id as bigint) as id
  , geo_h3_10
  , address_name
  , case when purpose_name = 'Жилой дом' or t.structure_info_apartments_count > 10then 4
    when purpose_name = 'Киоск' then 1 end as obj_priority_
  , purpose_name as obj_type_
  , floors_ground_count
  from postamat.platform_buildings t
 where purpose_name in ( 'Жилой дом', 'Киоск') or t.structure_info_apartments_count > 10
 union all 
 select ST_AsText(geometry) as geometry
  , cast(id as bigint) as id
  , geo_h3_10
  , '' as address_name
  , case when rubric = 'МФЦ' then 2
    when rubric = 'Библиотеки' then 3 end as obj_priority_
  , rubric as obj_type_
  , 0 as floors_ground_count  
  from postamat.platform_companies
 where rubric in ('МФЦ', 'Библиотеки') 
)
select m.predictions
 , ST_AsText(pc.geometry) as geometry
 , obj_type_
 , address_name
 , floors_ground_count
 , row_number() over (order by obj_priority_ asc, predictions desc, floors_ground_count desc) as rn
from postamat.platform_model m
join postamat.platform_domain d on d.geo_h3_10 = m.geo_h3_10
join good_locations pc on pc.geo_h3_10 = m.geo_h3_10
where 1=1
 and model_type = '{model_type_choise}'
 and {'adm_name' if district_type_choise == 'Районы' else 'okrug_name'} in {get_sql_list_as_string(list(districts['district']))}
 and LOWER(obj_type_) in {get_sql_list_as_string(object_types_choise)}
"""

model_output = pd.DataFrame(
    get_data(model_output_sql),
    columns=[
        "prediction",
        "geometry",
        "obj_type_",
        "address_name",
        "floors_ground_count",
        "rn",
    ],
)

model_output["geometry"] = model_output["geometry"].apply(loads)
model_output = geopandas.GeoDataFrame(
    model_output, geometry="geometry", crs="EPSG:4326"
).sort_values(by="prediction", ascending=False)


object_style = {
    "color": "#000000",
    "fill": True,
    "fillOpacity": 1,
}

# st.text(model_output.columns)
# st.dataframe(model_output.to_numpy())
if len(model_output) > 0:
    m.add_gdf(
        model_output[:take_top],
        layer_name="Model",
        fill_colors=["black"],
        style=object_style,
    )
else:
    st.text("Не нашлось постаматов под данные фильтры")


def create_pdf_report():

    # img_data = m._to_png()
    # img = Image.open(io.BytesIO(img_data))

    with open('src/report_1.html') as f:
        html_text = f.read()

    html_text = html_text.format(
        dt=pd.Timestamp.now(),
        model_name=model_type_choise,
        adm_type=district_type_choise,
        loaction_text=', '.join(districts_choise),
        postamat_count=take_top,
        object_type_filter=', '.join(object_types_choise),
        map_img=''
    )
    pdfkit.from_string(html_text, '/tmp/report.pdf')


create_report_button = st.sidebar.button(
    label='Сформировать отчет',
    on_click=create_pdf_report
)

if create_report_button:
    with open("/tmp/report.pdf", "rb") as file:
        download_button = st.sidebar.download_button(
            label="Скачать отчёт [pdf]",
            file_name='report.pdf',
            data=file,
            mime='application/octet-stream'
        )

m.to_streamlit(height=700)
