import streamlit as st
import psycopg2


# Initialize connection.
# Uses st.experimental_singleton to only run once.
@st.experimental_singleton
def init_connection():
    return psycopg2.connect(**st.secrets["postgres"])


# Perform query.
# Uses st.experimental_memo to only rerun when the query changes or after 10 min.
@st.experimental_memo(ttl=10)
def get_data(query: str):
    with init_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query)
            return cur.fetchall()
