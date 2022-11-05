import streamlit as st
import kepler_folimap as leafmap1
import pandas as pd
from db import get_data
from shapely.wkt import loads
from shapely import wkb
import pdfkit
import io
from PIL import Image


def get_sql_list_as_string(items):
    """
    """
    if len(items) == 0:
        return "('random_string')"
    return f"""{tuple(items) if len(items)> 1 else f"('{items[0]}')"}"""

def get_districts(district_type_choise) -> pd.DataFrame:
    """
        Получение геометрии районов
    """
    districts_sql = f"""
        select {"adm_name" if district_type_choise == "Районы" else "okrug_name"}
                , ST_AsText(geometry)
        from postamat.{"adm_zones" if district_type_choise == "Районы" else "adm_okr_zones"}
    """
    districts = get_data(districts_sql)
    districts = pd.DataFrame(districts, columns=["district", "geometry"])
    districts = districts.sort_values(by = 'district')
    districts["geometry"] = districts["geometry"].apply(loads).astype(str)

    return districts

def get_postamats(districs_: list) -> pd.DataFrame:
    """
        Получение списка массива постаматов по заданному району
        :param districs_ - список районов
    """

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
    postamats = pd.DataFrame(
        postamats, columns=["point_lat", "point_lon", "name"])
    return postamats

def get_model_types() -> list:
    """
        Получение списка моделей, которыми можно пользоваться
    """
    model_types_sql = "select distinct model_type from postamat.platform_model"
    model_types = [x[0] for x in get_data(model_types_sql)]
    return model_types

def get_object_types():
    """
        Получение списка объектов, доступных для оптимизации (мфц, жилые дома и так далее)
    """
    object_types_sql = "select distinct purpose_name from postamat.all_objects"
    object_types = [x[0] for x in get_data(object_types_sql)]
    return object_types

def get_model_h3_predictions(model_type_choise: str, district_type_choise: str, districs_: list)->pd.DataFrame:
    """
        Получение предсказаний модели на выбранные районы
        :param model_type_choise - список районов        
        :param district_type_choise - список районов  
        :param districs_ - список районов
    """
    model_h3 = pd.DataFrame(
        get_data(f"""
        select m.predictions, d.geometry 
        from postamat.platform_model m
        join postamat.platform_domain d on d.geo_h3_10 = m.geo_h3_10
        where 1=1
            and model_type in ('{model_type_choise}')
            and {'adm_name' if district_type_choise == 'Районы' else 'okrug_name'} in {get_sql_list_as_string(districs_)}"""
                 ),
        columns=["Значение модели", "geometry"]
    )
    model_h3['geometry'] = model_h3['geometry'].apply(
        lambda x: wkb.loads(x, hex=True)).astype(str)
    return model_h3

def get_model_output(model_type_choise: str, district_type_choise: str, districs_: list) -> pd.DataFrame:
    model_output_sql = f"""
        with all_togeather as 
        ( 
            select case when address_name is null or address_name ='' then name else address_name end as address_name
                , ST_AsText(pc.geometry) as geometry
                , ST_AsText(ST_Centroid(pc.geometry)) as pt
                , ST_X(ST_AsText(ST_Centroid(pc.geometry))) as lon
                , ST_Y(ST_AsText(ST_Centroid(pc.geometry))) as lat
                , purpose_name
                , case when purpose_name = 'киоск печати' then m.predictions + 60 
		            when purpose_name = 'МФЦ' then m.predictions + 50
		            when purpose_name = 'библиотека' then m.predictions + 40 
		            when purpose_name = 'дом культуры' then m.predictions + 30 
		            when purpose_name = 'спортивный объект' then m.predictions + 20
		            when purpose_name = 'жилой дом' then m.predictions + 10 end as prediction_corrected  
                , floors_ground_count
                , d.adm_name
                , d.okrug_name
                , model_type
                , m.predictions*100 as predictions
                , row_number() over (partition by h.geo_h3_9 order by predictions desc, floors_ground_count desc) as rn
            from postamat.platform_model m
            join postamat.platform_domain d on d.geo_h3_10 = m.geo_h3_10
            join postamat.all_objects pc on pc.geo_h3_10 = m.geo_h3_10
            join postamat.h3_10_9 h on h.geo_h3_10 = d.geo_h3_10
            where 1=1
                and model_type = '{model_type_choise}'
                and {'adm_name' if district_type_choise == 'Районы' else 'okrug_name'} in {get_sql_list_as_string(districs_)}
                and m.predictions*100 >  {score_filter[0]} and m.predictions*100  < {score_filter[1]}
                and purpose_name in {get_sql_list_as_string(object_types_choise)}     
        )
        select * from all_togeather
        where 1=1
            and rn=1
        order by prediction_corrected desc   
        limit {take_top}
    """
    # print(model_output_sql)

    model_output = pd.DataFrame(
        get_data(model_output_sql),
        columns=["Адрес", "geometry", 'Координата', "lon", "lat", 'Тип объекта размещения', 'prediction_corrected', "Число этажей",
                 'Округ', 'Район', 
                  'Модель рассчёта', 'Значение модели', "rn"]
    )
    model_output = model_output.reset_index()
    model_output = model_output.drop(['prediction_corrected'], axis = 1)
    model_output['Номер'] = model_output['index']+1   
    return model_output

def compose_map(postamats, districts, model_output, model_h3):
    """
        Отрисовка карты
        :parmam postamats - массив с текущей сетью постаматов (конкуренты)
        :parmam districts - полигон с выбранными границами районов
        :parmam model_output - результат оптимизации - на объектах
        :parmam model_h3 - результат оптимизации - на хексагонах - подложка
    """
    if len(model_output) == 0:
        st.text("Не нашлось постаматов под данные фильтры")
        return

    with open('data.txt', 'r') as f:
        cfg = f.read()
        cfg = eval(cfg)

    m = leafmap1.Map(center=[postamats['point_lat'].mean(
    ), postamats['point_lon'].mean()], zoom=9, config=cfg)
    if len(postamats) > 0:
        m.add_data(postamats, 'Постаматы')

    if len(model_output) > 0:
        m.add_data(model_output, 'Модель')

    if len(model_h3) > 0:
        m.add_data(model_h3, 'Модель(hex)')

    if len(districts) > 0:
        m.add_data(districts, 'Районы')
    m.to_streamlit(height=700)


def calculate_coverage(model_type_choise: str, district_type_choise: str, districs_: list):
    """Расчёт покрытия шаговой доступностью по выбранным постаматам"""
    sql = f"""
        with good_locations as 
        (
            with all_togeather as 
            ( 
                select address_name
                    , pc.geo_h3_10
                    , pc.geometry
                    , purpose_name
                    , floors_ground_count
                    , m.predictions*100 as predictions
                    , row_number() over (partition by pc.geo_h3_10 order by purpose_name asc, predictions desc, floors_ground_count desc) as rn
                from postamat.platform_model m
                join postamat.platform_domain d on d.geo_h3_10 = m.geo_h3_10
                join postamat.all_objects pc on pc.geo_h3_10 = m.geo_h3_10
                where 1=1
                    and model_type = '{model_type_choise}'
                    and {'adm_name' if district_type_choise == 'Районы' else 'okrug_name'} in {get_sql_list_as_string(districs_)}
                    and m.predictions*100 >  {score_filter[0]} and m.predictions*100  < {score_filter[1]}
                    and purpose_name in {get_sql_list_as_string(object_types_choise)}      
            )
            select * from all_togeather
            where 1=1
                and rn=1
            order by predictions desc
            limit {take_top}
        )
        , model_results as 
        ( -- хексагоны с хорошими постаматами
            select distinct pc.geo_h3_10
            from postamat.platform_model m
            join postamat.platform_domain d on d.geo_h3_10 = m.geo_h3_10
            join good_locations pc on pc.geo_h3_10 = m.geo_h3_10
            where 1=1
                and model_type = '{model_type_choise}'
                and {'adm_name' if district_type_choise == 'Районы' else 'okrug_name'} in {get_sql_list_as_string(districs_)}
        )
        , all_population as 
        ( -- население в выбранном регионе
            select distinct pra.geometry as point_geom
                , peop_id
            from postamat.platform_domain pd 
            join (SELECT * FROM postamat.platform_isochrones pi2 where kind = 'walking_5min') iso
                on pd.geo_h3_10 = iso.geo_h3_10
            join postamat.popul_msk_raw_all pra
                on ST_Contains(iso.geometry, pra.geometry)
            where {'adm_name' if district_type_choise == 'Районы' else 'okrug_name'} in {get_sql_list_as_string(districs_)}
        )
        , sum_population as 
        (
            select sum(peop_id) as area_population
            from all_population
        )
        , filter_isochrones as 
        ( 
            select distinct 
                --iso.*
                pra.geometry as point_geom
                , pra.peop_id
            from model_results mr
            join (SELECT * FROM postamat.platform_isochrones pi2 where kind = 'walking_5min') iso 
                  on mr.geo_h3_10 = iso.geo_h3_10
            join postamat.popul_msk_raw_all pra
                  on ST_Contains(iso.geometry, pra.geometry)
        )
        , sum_covered_people as 
        ( 
            select sum(iso.peop_id) as covered_people
            from filter_isochrones iso
        )
        select scv.covered_people
            , sp.area_population
            , round(scv.covered_people / sp.area_population, 2) as perc
        from sum_covered_people scv
        cross join sum_population sp    
    """
    coverage_output = pd.DataFrame(
        get_data(sql),
        columns=["Покрытое население в шаговой доступности", "Общее население в шаговой доступности в выбранной локации", "Процент покрытия в выбранной локации"],
    )
    return coverage_output


def create_reesrt(model_output: pd.DataFrame) -> pd.DataFrame:
    """
        Формирование реестра объектов
    """

    model_output_for_report = model_output[['Номер', 'Округ', 'Район', 'Тип объекта размещения', 'Координата',
        'Адрес', 'Модель рассчёта', 'Значение модели']].copy()
    return model_output_for_report

# ui
st.set_page_config(layout="wide")
st.sidebar.subheader('Параметры')


# ui по районам
st.write('<style>div.row-widget.stRadio > div{flex-direction:row;}</style>', unsafe_allow_html=True)
district_type_choise = st.sidebar.radio("", ("Районы", "Округа"))
districts = get_districts(district_type_choise)

districts_choise = st.sidebar.multiselect(
    district_type_choise,
    districts["district"].values,
    [districts["district"].values[0]],
)
districts = districts[districts["district"].isin(districts_choise)]

# ui по параметрам модели
model_type_choise = st.sidebar.selectbox(
    "Модель",
    get_model_types(),
    help='Выберите необходимую модель размещения. Логика моделей и разница между ними описана в презентации.',
    index=1
)

#
take_top = st.sidebar.slider(
    "Кол-во постаматов для размещения", min_value=1, max_value=1000, step=1, value=60)
score_filter = st.sidebar.slider(
    "Скор модели", min_value=0.0, max_value=100.0, value=(20.0, 100.0))


object_types = get_object_types()
object_types_choise = st.sidebar.multiselect(
    "Объекты для размещения", object_types, object_types[:5]
)

# модель на хексагонах
model_h3 = get_model_h3_predictions(
    model_type_choise, district_type_choise, list(districts['district']))

# модель на домах
model_output = get_model_output(model_type_choise, district_type_choise, list(districts['district']))
postamats = get_postamats(list(districts['district']))



# правая часть ui
st.write('<style>div.block-container{padding-top:2rem;}</style>', unsafe_allow_html=True)
st.subheader("Карта")
compose_map(postamats, districts, model_output, model_h3)


st.subheader("Отчёт о покрытии")
report  = calculate_coverage(model_type_choise, district_type_choise, list(districts['district']))
# CSS to inject contained in a string
hide_table_row_index = """
            <style>
            thead tr th:first-child {display:none}
            tbody th {display:none}
            </style>
            """
st.markdown(hide_table_row_index, unsafe_allow_html=True)
st.table(report)

st.subheader("Реестр подходящих объектов")
st.table(create_reesrt(model_output))


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

