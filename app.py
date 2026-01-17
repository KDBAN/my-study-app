import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import random
import datetime
import os

# --- 구글 시트 연결 설정 ---
# 주의: secrets.json 파일이 같은 폴더에 있어야 함
SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
SHEET_NAME = "StudyData" # 구글 시트 파일 이름

@st.cache_resource
def connect_google_sheet():
    creds_dict = dict(st.secrets["gcp_service_account"])
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, SCOPE)
    client = gspread.authorize(creds)
    sheet = client.open(SHEET_NAME).sheet1
    return sheet

# --- 데이터 관리 함수 ---
def load_data():
    try:
        sheet = connect_google_sheet()
        data = sheet.get_all_records()
        # 데이터 타입 보정 (문자열 -> 숫자)
        for item in data:
            item['tried'] = int(item['tried']) if item['tried'] != '' else 0
            item['correct'] = int(item['correct']) if item['correct'] != '' else 0
        return data
    except Exception as e:
        st.error(f"데이터 로드 실패: {e}")
        return []

def add_data_to_sheet(new_item):
    sheet = connect_google_sheet()
    # 리스트 순서: subject, q, a, img, tried, correct
    row = [new_item['subject'], new_item['q'], new_item['a'], "", 0, 0]
    sheet.append_row(row)

def update_data_in_sheet(row_idx, col_name, value):
    # row_idx는 0부터 시작하지만 엑셀은 2행부터 데이터가 시작하므로 +2
    sheet = connect_google_sheet()
    
    col_map = {'subject': 1, 'q': 2, 'a': 3, 'img': 4, 'tried': 5, 'correct': 6}
    col_num = col_map[col_name]
    
    sheet.update_cell(row_idx + 2, col_num, value)

def delete_data_from_sheet(row_idx):
    sheet = connect_google_sheet()
    sheet.delete_row(row_idx + 2)

# --- 세션 상태 초기화 ---
if 'data' not in st.session_state:
    st.session_state.data = load_data()

# 데이터가 비었으면 다시 로드 시도
if not st.session_state.data:
    st.session_state.data = load_data()

if 'current_q' not in st.session_state:
    st.session_state.current_q = None
if 'show_answer' not in st.session_state:
    st.session_state.show_answer = False

# --- 메인 화면 ---
st.title("☁️ 구글 연동 암기장")

with st.sidebar:
    menu = st.radio("메뉴", ["홈 (공부하기)", "문제 추가", "목록/관리"])
    st.divider()
    study_mode = st.radio("모드", ["스마트 (틀린거)", "랜덤"])
    if st.button("🔄 데이터 새로고침"):
        st.session_state.data = load_data()
        st.rerun()

# --- 1. 홈 ---
if menu == "홈 (공부하기)":
    subjects = sorted(list(set([d['subject'] for d in st.session_state.data])))
    subjects.insert(0, "ALL")
    
    sel_subj = st.selectbox("과목", subjects)
    
    if st.button("문제 뽑기"):
        st.session_state.show_answer = False
        candidates = st.session_state.data if sel_subj == "ALL" else [d for d in st.session_state.data if d['subject'] == sel_subj]
        
        if not candidates:
            st.error("문제가 없습니다.")
        else:
            if "랜덤" in study_mode:
                st.session_state.current_q = random.choice(candidates)
            else:
                weights = [max(5, 100 - (int(x['correct']/x['tried']*100) if x['tried']>0 else 0)) for x in candidates]
                st.session_state.current_q = random.choices(candidates, weights=weights, k=1)[0]
            
            # 인덱스 찾기
            # 주의: 리스트 내 딕셔너리 비교가 까다로울 수 있어 간단히 내용으로 찾음 (중복 문제 시 이슈 가능성 있음)
            st.session_state.q_index = st.session_state.data.index(st.session_state.current_q)
            st.rerun()

    if st.session_state.current_q:
        q = st.session_state.current_q
        st.info(f"[{q['subject']}] {q['q']}")
        
        if not st.session_state.show_answer:
            if st.button("정답 확인"):
                st.session_state.show_answer = True
                st.rerun()
        
        if st.session_state.show_answer:
            st.success(f"정답: {q['a']}")
            
            c1, c2 = st.columns(2)
            with c1:
                if st.button("O 맞음"):
                    idx = st.session_state.q_index
                    # 메모리 업데이트
                    st.session_state.data[idx]['tried'] += 1
                    st.session_state.data[idx]['correct'] += 1
                    # 구글 시트 업데이트 (속도 느림 주의)
                    update_data_in_sheet(idx, 'tried', st.session_state.data[idx]['tried'])
                    update_data_in_sheet(idx, 'correct', st.session_state.data[idx]['correct'])
                    st.toast("저장됨!")
                    st.session_state.show_answer = False
                    st.session_state.current_q = None
                    st.rerun()
            with c2:
                if st.button("X 틀림"):
                    idx = st.session_state.q_index
                    st.session_state.data[idx]['tried'] += 1
                    update_data_in_sheet(idx, 'tried', st.session_state.data[idx]['tried'])
                    st.toast("저장됨!")
                    st.session_state.show_answer = False
                    st.session_state.current_q = None
                    st.rerun()

# --- 2. 추가 ---
elif menu == "문제 추가":
    with st.form("add"):
        s = st.text_input("과목")
        q = st.text_area("문제")
        a = st.text_area("정답")
        if st.form_submit_button("저장"):
            new = {'subject': s, 'q': q, 'a': a}
            add_data_to_sheet(new) # 구글 시트에 저장
            st.session_state.data = load_data() # 데이터 다시 불러오기
            st.success("추가되었습니다!")

# --- 3. 관리 ---
elif menu == "목록/관리":
    st.write("구글 시트의 데이터입니다.")
    st.dataframe(st.session_state.data)
    st.caption("수정/삭제는 구글 스프레드시트에서 직접 하는 것이 더 빠르고 정확합니다.")

