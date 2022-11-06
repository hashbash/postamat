import streamlit as st


st.set_page_config(page_title='Постаматы')


st.title('Сервис для размещения постаматов')
st.info('Удобный сервис для выбора локаций для постаматов для проекта Лидеры цифровой трансформации')

st.header('Презентация')
st.download_button(file_name='Презентация Geo XYZ.pdf',
                   data='src/presentation.pdf',
                   label='Скачать презентацию [pdf]')

st.header('Ссылки')

st.write('Репозиторий интерфейса: https://github.com/hashbash/postamat')
st.write('Репозиторий модели: https://github.com/GavrilinEugene/postamat_recomendation_system')
st.write('Репозиторий API: https://github.com/hashbash/postamat-api')

st.header('Документация')

st.write('Сопроводительная документация: https://docs.google.com/document/d/1v01o1oNmxaOsYtHOlh2oVsj4Nu0acvkeK6rWu7V'
         'E7U8/edit#heading=h.ldjxqtfx6gee')
st.write('Документация API (swagger): http://135.181.97.90:8098/docs')

