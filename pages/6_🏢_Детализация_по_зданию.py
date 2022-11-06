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

# if "map" not in st.session_state:
#     st.text("Посчитай модель")
#     st.stop()

st.set_page_config(layout="wide")
params = st.experimental_get_query_params()

hexagon = params.get("geo", ["8a11aa78689ffff"])[0]
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


# # правая часть ui
# st.write(
#     "<style>div.block-container{padding-top:2rem;}</style>", unsafe_allow_html=True
# )
st.subheader("Карта")
map_obj = compose_map(
    postamats, districts, model_output, model_h3, center=h3.h3_to_geo(hexagon), zoom=25
)
if map_obj is None:
    st.text("Не нашлось постаматов под данные фильтры")
    st.stop()

map_obj.to_streamlit(height=700)


st.experimental_set_query_params()


data_sql = """
select *
from postamat.model_msk_predictions
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
    get_data(data_sql), columns=["geo_h3_10"] + features + ["prediction", "model_type"]
)

data = data.drop(columns="model_type").reset_index(drop=True)


# st.write(data)
data = data[data["geo_h3_10"] == hexagon]
model = pickle.load(open("models/postamat_cb_model.sav", "rb"))

xpl = SmartExplainer(
    model=pickle.load(open("models/postamat_cb_model.sav", "rb")),
)

threshold = 0.5
xpl.compile(data[features], y_pred=(data["prediction"] > threshold).apply(int))
st.write(xpl.to_pandas(proba=True))


# Падает вот тут
xpl.generate_report(
    "./report.html",
    "project_info.yaml",
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


# model.calc_feature_statistics(
#     data[features], target=[0] * len(data), feature=features, plot_file="./plot.html"
# )

# components.html(" ".join(open("./plot.html").readlines()), height=500)
