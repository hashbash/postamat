import kepler_folimap as leafmap1
import json
import geopandas
import pandas as pd
from db import get_data
from shapely.wkt import loads
from shapely import wkb
import pdfkit
import io


def get_sql_list_as_string(items):
    """ """
    if len(items) == 0:
        return "('random_string')"
    return f"""{tuple(items) if len(items)> 1 else f"('{items[0]}')"}"""


def get_districts(district_type) -> pd.DataFrame:
    """
    Получение геометрии районов
    :param district_type - тип районов (Районы или Округа)
    """
    districts_sql = f"""
        select {"adm_name" if district_type == "Районы" else "okrug_name"}
                , ST_AsText(geometry)
        from postamat.{"adm_zones" if district_type == "Районы" else "adm_okr_zones"}
    """
    districts = get_data(districts_sql)
    districts = pd.DataFrame(districts, columns=["district", "geometry"])
    districts = districts.sort_values(by="district")
    districts["geometry"] = districts["geometry"].apply(loads).astype(str)

    return districts


def get_postamats(districs_: list, district_type: str) -> pd.DataFrame:
    """
    Получение списка массива постаматов по заданному району
    :param districs_ - список районов
    :param district_type - тип районов (Районы или Округа)
    """

    postamat_sql = f"""
        select point_lat
            , point_lon
            , name 
        from postamat.platform_companies m
        join postamat.platform_domain d on d.geo_h3_10 = m.geo_h3_10
        where 1=1
            and rubric = 'Постаматы'
            and {'adm_name' if district_type == 'Районы' else 'okrug_name'} in {get_sql_list_as_string(districs_)}"""
    postamats = get_data(postamat_sql)
    postamats = pd.DataFrame(postamats, columns=["point_lat", "point_lon", "name"])
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


def get_model_h3_predictions(
    model_type_choise: str, district_type_choise: str, districs_: list
) -> pd.DataFrame:
    """
    Получение предсказаний модели на выбранные районы
    :param model_type_choise - список районов
    :param district_type_choise - список районов
    :param districs_ - список районов
    """
    model_h3 = pd.DataFrame(
        get_data(
            f"""
        select m.predictions, d.geometry 
        from postamat.platform_model m
        join postamat.platform_domain d on d.geo_h3_10 = m.geo_h3_10
        where 1=1
            and model_type in ('{model_type_choise}')
            and {'adm_name' if district_type_choise == 'Районы' else 'okrug_name'} in {get_sql_list_as_string(districs_)}"""
        ),
        columns=["Значение модели", "geometry"],
    )
    model_h3["geometry"] = (
        model_h3["geometry"].apply(lambda x: wkb.loads(x, hex=True)).astype(str)
    )
    return model_h3


def get_model_output(
    model_type_choise: str,
    district_type_choise: str,
    districs_: list,
    score_filter: tuple,
    object_types_choise: list,
    take_top: int,
) -> pd.DataFrame:
    model_output_sql = f"""
        with all_togeather as 
        ( 
            select case when address_name is null or address_name ='' then name else address_name end as address_name
                , pc.geo_h3_10
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
        order by prediction_corrected desc   
        limit {take_top}
    """

    model_output = pd.DataFrame(
        get_data(model_output_sql),
        columns=[
            "Адрес",
            "geo_h3_10",
            "geometry",
            "Координата",
            "lon",
            "lat",
            "Тип объекта размещения",
            "prediction_corrected",
            "Число этажей",
            "Округ",
            "Район",
            "Модель рассчёта",
            "Значение модели",
            "rn",
        ],
    )
    model_output = model_output.reset_index()
    model_output = model_output.drop(["prediction_corrected"], axis=1)
    model_output["Номер"] = model_output["index"] + 1
    return model_output


def compose_map(postamats, districts, model_output, model_h3, center=None, zoom=9):
    """
    Отрисовка карты
    :param postamats - массив с текущей сетью постаматов (конкуренты)
    :param districts - полигон с выбранными границами районов
    :param model_output - результат оптимизации - на объектах
    :param model_h3 - результат оптимизации - на хексагонах - подложка
    :param center - координаты центра карты
    :param zoom - масштаб карты
    """
    if center is None:
        center = [postamats["point_lat"].mean(), postamats["point_lon"].mean()]
    if len(model_output) == 0:
        return None

    with open("data.txt", "r") as f:
        cfg = f.read()
        cfg = eval(cfg)

    m = leafmap1.Map(
        center=center,
        zoom=zoom,
        config=cfg,
    )
    if len(postamats) > 0:
        m.add_data(postamats, "Постаматы")

    if len(model_output) > 0:
        m.add_data(model_output, "Модель")

    if len(model_h3) > 0:
        m.add_data(model_h3, "Модель(hex)")

    if len(districts) > 0:
        m.add_data(districts, "Районы")
    # m.to_streamlit(height=700)
    return m


def calculate_coverage(
    model_type_choise: str,
    district_type_choise: str,
    districs_: list,
    score_filter: tuple,
    object_types_choise: list,
    take_top: int,
):
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
        columns=[
            "Покрытое население в шаговой доступности",
            "Общее население в шаговой доступности в выбранной локации",
            "Процент покрытия в выбранной локации",
        ],
    )
    return coverage_output


def create_reesrt(model_output: pd.DataFrame) -> pd.DataFrame:
    """
    Формирование реестра объектов
    """

    model_output_for_report = model_output[
        [
            "Номер",
            "Округ",
            "Район",
            "Тип объекта размещения",
            "Координата",
            "Адрес",
            "Модель рассчёта",
            "Значение модели",
        ]
    ].copy()
    return model_output_for_report
