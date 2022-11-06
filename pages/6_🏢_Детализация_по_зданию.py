import streamlit as st
from shapash import SmartExplainer
from shapash.explainer.smart_predictor import SmartPredictor
import streamlit.components.v1 as components
import pickle
from db import get_data
import streamlit as st
import pandas as pd
import kepler_folimap as leafmap1
import h3
from utils import *
import os


st.set_page_config(layout="wide")
params = st.experimental_get_query_params()

hexagon = params.get("geo", ["8a11aa786807fff"])[0]
model_type = params.get("model_type", ["Бинарная модель"])[0]
take_top = int(params.get("take_top", ["50"])[0])
district_type = params.get("district_type", ["Районы"])[0]
districts = eval(params.get("districts", ["['Академический']"])[0])
districts = pd.DataFrame(districts, columns=["district"])
score_filter = eval(params.get("score_filter", ["(0,50)"])[0])
object_types = eval(
    params.get(
        "object_types",
        ["['жилой дом', 'спортивный объект', 'библиотека', 'киоск печати', 'МФЦ']"],
    )[0]
)


model_h3 = get_model_h3_predictions(
    model_type, district_type, list(districts["district"])
)

# модель на домах
model_output = get_model_output(
    model_type,
    district_type,
    list(districts["district"]),
    score_filter,
    object_types,
    take_top,
)
postamats = get_postamats(list(districts["district"]), district_type)
st.subheader("Карта")
map_obj = compose_map(
    postamats, districts, model_output, model_h3, center=h3.h3_to_geo(hexagon), zoom=11
)
if map_obj is None:
    st.text("Не нашлось постаматов под данные фильтры")
    st.stop()

map_obj.to_streamlit(height=700)


st.experimental_set_query_params()


data_sql = """
SELECT bm.geo_h3_10, 
	bm.population_walking_5min, 
	bm.apteki_walking_5min, 
	bm.stroitelnye_materialy_walking_10min, 
	bm.platezhnye_terminaly_walking_5min, bm.detskie_sady_walking_10min, 
	bm.lekarstvennye_preparaty_walking_5min, 
	bm.cnt_evening, 
	bm.mjagkaja_mebel_walking_10min, 
	bm.supermarkety_walking_5min, 
	bm.uslugi_po_uhodu_za_resnitsami__brovjami_walking_5min, bm.target,
	mmp.predictions 
FROM postamat.train_binary_model bm
join postamat.model_msk_predictions mmp on mmp.geo_h3_10 = bm.geo_h3_10  
"""

features = [
    "population_walking_5min",
    "apteki_walking_5min",
    "stroitelnye_materialy_walking_10min",
    "platezhnye_terminaly_walking_5min",
    "detskie_sady_walking_10min",
    "lekarstvennye_preparaty_walking_5min",
    "cnt_evening",
    "mjagkaja_mebel_walking_10min",
    "supermarkety_walking_5min",
    "uslugi_po_uhodu_za_resnitsami__brovjami_walking_5min",
]
data = pd.DataFrame(
    get_data(data_sql), columns=["geo_h3_10"] + features + ["target", "prediction"]
)

model = pickle.load(open("models/postamat_cb_model.sav", "rb"))

xpl = SmartExplainer(
    model=model,
)

threshold = 0.5
xpl.compile(
    data[features],
    y_target=data["target"],
    y_pred=(data["prediction"] > threshold).apply(int),
)

st.subheader("Вывод shapash")
shapash_output = xpl.to_pandas(proba=True)


xpl.generate_report(
    "./shapash_report.html",
    "project_info.yaml",
    x_train=data[features],
    y_train=data["target"],
    metrics=[
        {
            "path": "sklearn.metrics.mean_absolute_error",
            "name": "Mean absolute error",
        },
        {
            "path": "sklearn.metrics.mean_squared_error",
            "name": "Mean squared error",
        },
    ],
)

with open("./shapash_report.html") as shapash_file:
    components.html(" ".join(shapash_file.readlines()), height=500)
os.remove("./shapash_report.html")


st.subheader("Вывод catboost")
model.calc_feature_statistics(
    data[features],
    target=data["target"],
    feature=features,
    plot_file="./catboost_plot.html",
)
with open("./catboost_plot.html") as catboost_file:
    components.html(" ".join(catboost_file.readlines()), height=500)
os.remove("./catboost_plot.html")
