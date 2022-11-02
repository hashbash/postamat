import streamlit as st
import psycopg2
from os import environ


# Initialize connection.
# Uses st.experimental_singleton to only run once.
@st.experimental_singleton
def init_connection():
    return psycopg2.connect(**st.secrets["postgres"])


# Perform query.
# Uses st.experimental_memo to only rerun when the query changes or after 10 min.
@st.experimental_memo(ttl=10)
def get_data(query: str):
    def run_sql(sql: str):
        with psycopg2.connect(**st.secrets["postgres"],
                              password=environ['POSTAMAT_PG_PASS']) as conn:
            with conn.cursor() as cur:
                cur.execute(sql)
                return cur.fetchall()
    try:  # dirty rerun if expired
        return run_sql(query)
    except psycopg2.InternalError:
        return run_sql(query)

