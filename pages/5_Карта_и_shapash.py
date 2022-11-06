import streamlit as st
from utils import *

# ui
st.set_page_config(layout="wide")
st.sidebar.subheader("Параметры")


# ui по районам
st.write(
    "<style>div.row-widget.stRadio > div{flex-direction:row;}</style>",
    unsafe_allow_html=True,
)
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
    help="Выберите необходимую модель размещения. Логика моделей и разница между ними описана в презентации.",
    index=1,
)

#
take_top = st.sidebar.slider(
    "Кол-во постаматов для размещения", min_value=1, max_value=1000, step=1, value=60
)
score_filter = st.sidebar.slider(
    "Скор модели", min_value=0.0, max_value=100.0, value=(20.0, 100.0)
)


object_types = get_object_types()
object_types_choise = st.sidebar.multiselect(
    "Объекты для размещения", object_types, object_types[:5]
)

# модель на хексагонах
model_h3 = get_model_h3_predictions(
    model_type_choise, district_type_choise, list(districts["district"])
)

# модель на домах
model_output = get_model_output(
    model_type_choise,
    district_type_choise,
    list(districts["district"]),
    score_filter,
    object_types_choise,
    take_top,
)
postamats = get_postamats(list(districts["district"]), district_type_choise)


# правая часть ui
st.write(
    "<style>div.block-container{padding-top:2rem;}</style>", unsafe_allow_html=True
)
st.subheader("Карта")
map_obj = compose_map(postamats, districts, model_output, model_h3)
if map_obj is None:
    st.text("Не нашлось постаматов под данные фильтры")
    st.stop()

map_obj.to_streamlit(height=700)

st.subheader("Отчёт о покрытии")
coverage_report = calculate_coverage(
    model_type_choise,
    district_type_choise,
    list(districts["district"]),
    score_filter,
    object_types_choise,
    take_top,
)
# CSS to inject contained in a string
hide_table_row_index = """
            <style>
            thead tr th:first-child {display:none}
            tbody th {display:none}
            </style>
            """
st.markdown(hide_table_row_index, unsafe_allow_html=True)
st.table(coverage_report)


def make_clickable(text, geo):
    return f'<a target="_self" href="/Детализация_по_зданию?geo={geo}&model_type={model_type_choise}&take_top={take_top}&district_type={district_type_choise}&districts={districts_choise}&score_filter={score_filter}&object_types={object_types_choise}">{text}</a>'


model_output["Адрес"] = model_output.apply(
    lambda row: make_clickable(row["Адрес"], row["geo_h3_10"]), axis=1
)

st.subheader("Реестр подходящих объектов")
model_output_for_report = create_reesrt(model_output)
st.write(model_output_for_report.to_html(escape=False), unsafe_allow_html=True)


def get_df_for_report(input_df: pd.DataFrame) -> pd.DataFrame:
    df = input_df.copy()
    df = df.drop(["geometry", "floors_ground_count", "rn"], axis=1)
    df = df.rename(
        columns={
            "address_name": "Адрес",
            "purpose_name": "Тип",
            "prediction": "Скор модели",
        }
    )
    return df


def create_pdf_report():

    # img_data = m._to_png()
    # img = Image.open(io.BytesIO(img_data))

    with open("src/report_1.html") as f:
        html_text = f.read()

    df = get_df_for_report(model_output)
    html_text = html_text.format(
        dt=pd.Timestamp.now(),
        model_name=model_type_choise,
        adm_type=district_type_choise,
        loaction_text=", ".join(districts_choise),
        postamat_count=take_top,
        object_type_filter=", ".join(object_types_choise),
        df=df.to_html(index=False),
    )
    pdfkit.from_string(html_text, "/tmp/report.pdf")


create_report_button = st.sidebar.button(
    label="Сформировать отчет", on_click=create_pdf_report
)

if create_report_button:
    with open("/tmp/report.pdf", "rb") as file:
        download_button = st.sidebar.download_button(
            label="Скачать отчёт [PDF]",
            file_name="report.pdf",
            data=file,
            mime="application/octet-stream",
        )

    def convert_df(df):
        return df.to_csv().encode("utf-8")

    csv = convert_df(get_df_for_report(model_output))
    st.sidebar.download_button(
        label="Скачать отчет [MS Excel]",
        data=csv,
        file_name="report.csv",
        mime="text/csv",
    )
