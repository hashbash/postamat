import streamlit as st
# import leafmap.kepler as leafmap1
import kepler_folimap as leafmap1
import json
import geopandas
import pandas as pd
from db import get_data
from shapely.wkt import loads
from shapely import wkb
import pdfkit
import io
from PIL import Image


def get_sql_list_as_string(items):
    if len(items) == 0:
        return "('random_string')"
    return f"""{tuple(items) if len(items)> 1 else f"('{items[0]}')"}"""


def get_districts():
    district_type_choise = "Районы"
    districts_sql = f"""select {"adm_name" if district_type_choise == "Районы" else "okrug_name"}, ST_AsText(geometry)
    from postamat.{"adm_zones" if district_type_choise == "Районы" else "adm_okr_zones"}
    """
    districts = get_data(districts_sql)
    districts = pd.DataFrame(districts, columns=["district", "geometry"])
    districts["geometry"] = districts["geometry"].apply(loads).astype(str)
    return districts


def get_postamats(districs_):
    postamat_sql = f"""
        select point_lat
            , point_lon
            , name 
        from postamat.platform_companies m
        join postamat.platform_domain d on d.geo_h3_10 = m.geo_h3_10
        where 1=1
            and rubric = 'Постаматы'
            and {'adm_name' if district_type_choise == 'Районы' else 'okrug_name'} in {get_sql_list_as_string(districs_)}"""
    postamats = get_data(postamat_sql)
    postamats = pd.DataFrame(postamats, columns=["point_lat", "point_lon", "name"])
    return postamats


def get_model_types():
    model_types_sql = "select distinct model_type from postamat.platform_model"
    model_types = [x[0] for x in get_data(model_types_sql)]
    return model_types



def get_model_h3_predictions(model_type_choise:str, district_type_choise:str, districs_:list):
    model_h3 = pd.DataFrame(
    get_data(f"""
        select m.predictions, d.geometry 
        from postamat.platform_model m
        join postamat.platform_domain d on d.geo_h3_10 = m.geo_h3_10
        where 1=1
            and model_type in ('{model_type_choise}')
            and {'adm_name' if district_type_choise == 'Районы' else 'okrug_name'} in {get_sql_list_as_string(districs_)}"""
            ),
    columns=[
        "predictions",
        "geometry"
    ]
    )
    model_h3['geometry'] = model_h3['geometry'].apply(lambda x: wkb.loads(x, hex=True)).astype(str)
    return model_h3


def get_object_types():
    object_types_sql = "select distinct purpose_name  from postamat.all_objects"
    object_types = [x[0].lower() for x in get_data(object_types_sql)]
    return object_types


st.set_page_config(layout="wide")
st.title("Лучшие локации для постаматов")

st.sidebar.subheader('Параметры')

district_types = ("Районы", "Округа")
district_type_choise = st.sidebar.radio("", district_types)



districts = get_districts()
districts_choise = st.sidebar.multiselect(
    district_type_choise,
    districts["district"].values,
    [districts["district"].values[0]],
)
districts = districts[districts["district"].isin(districts_choise)]


model_type_choise = st.sidebar.selectbox(
    "Модель",
    get_model_types(),
    help='Выберите необходимую модель размещения. Логика моделей и разница между ними описана в презентации.'
)

#
take_top = st.sidebar.slider(
    "Кол-во постаматов для размещения", min_value=1, max_value=1000, step=1, value=50)
score_filter = st.sidebar.slider(
    "Скор модели", min_value=0.0, max_value=100.0, value=(50.0, 100.0))


object_types = get_object_types()
object_types_choise = st.sidebar.multiselect(
    "Объекты для размещения (NOT IMPLEMENTED)", object_types, object_types[:3]
)


def compose_map(postamats, districts, model_output, model_h3):

    if len(model_output) == 0:
        st.text("Не нашлось постаматов под данные фильтры")
        return

    with open('data.json', 'r') as f:
        cfg = json.load(f)

    
    m = leafmap1.Map(center=[postamats['point_lat'].mean(), postamats['point_lon'].mean()], zoom=9, config = cfg)
    if len(postamats) > 0:
        m.add_data(postamats, 'Постаматы')

    if len(model_output) > 0:
        m.add_data(model_output, 'Модель')
        
    if len(model_h3) > 0:
        m.add_data(model_h3, 'Модель(hex)')        

    if len(districts) > 0:
        m.add_data(districts, 'Районы')
    m.to_streamlit(height=700)



model_output_sql = f"""with good_locations as 
(
 select ST_AsText(geometry) as geometry
    , cast(id as bigint) as id
    , geo_h3_10
    , address_name
    , case when purpose_name = 'Жилой дом' or t.structure_info_apartments_count > 10 then 4
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
, all_togeather as 
( 
    select m.predictions*100 as predictions
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
        and m.predictions*100 >  {score_filter[0]}and m.predictions*100  < {score_filter[1]}
        and LOWER(obj_type_) in {get_sql_list_as_string(object_types_choise)}     
)
select * from all_togeather
where 1=1
    and rn <= {take_top}
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



model_h3 = get_model_h3_predictions(model_type_choise, district_type_choise, list(districts['district']))
postamats = get_postamats(list(districts['district']))

compose_map(postamats,districts,model_output, model_h3)



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

# m.to_streamlit(height=700)
