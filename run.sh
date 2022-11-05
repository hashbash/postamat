#!bin/bash
cd /root/postamat
source /root/streamlit_venv/bin/activate
/root/streamlit_venv/bin/streamlit run /root/postamat/Hello.py --server.port 8099
