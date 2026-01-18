import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import random
import datetime
import os
import requests # 이미지 전송용

# --- 설정 ---
# 구글 시트 연결 설정
SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
SHEET_NAME = "StudyData"

# ImgBB API 키 (이미지 저장소)
IMGBB_KEY = "c7d34c614079feca31b8cce16ece746c"

@st.cache_resource
def connect_google_sheet():
    # 1. Secrets 정보를 가져옵니다.
    creds_dict = dict(st.secrets["gcp_service_account"])
    
    # 2. 에러 원인 해결! 글자 '\n'을 진짜 줄바꿈으로 강제 변환합니다.
    if "private_key" in creds_dict:
        creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
    
    # 3. 구글 시트에 연결합니다.
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, SCOPE)
    client = gspread.authorize(creds)
    sheet = client.open(SHEET_NAME).sheet1
    return sheet

# --- 기능 함수들 ---

# ImgBB에 이미지를 올리고 URL을 받아오는 함수
def upload_to_imgbb(file):
    try:
        url = "https://api.imgbb.com/1/upload"
        payload = {"key": IMGBB_KEY}
        files = {"image": file.getvalue()}
        response = requests.post(url, data=payload, files=files)
        result = response.json()
        if result["success"]:
            return result["data"]["url"] # 사진 주소 반환
        else:
            return None
    except Exception as e:
        st.error(f"이미지 업로드 오류: {e}")
        return None

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
    # 이미지가 없으면 빈칸("")으로 들어갑니다.
    row = [new_item['subject'], new_item['q'], new_item['a'], new_item.get('img', ""), 0, 0]
    sheet.append_row(row)

def update_data_in_sheet(row_idx, col_name, value):
    # row_idx는 0부터 시작하지만 엑셀은 2행부터 데이터가 시작하므로 +2
    sheet = connect_google_sheet()
    col_map = {'subject': 1, 'q': 2, 'a': 3, 'img': 4, 'tried': 5, 'correct': 6}
    col_num = col_map[col_name]
    sheet.update_cell(row_idx + 2, col_num, value)

# --- 세션 상태 초기화 ---
if 'data' not in st.session_state: st.session_state.data = load_data()
if not st.session_state.data: st.session_state.data = load_data()
if 'current_q' not in st.session_state: st.session_state.current_q = None
if 'show_answer' not in st.session_state: st.session_state.show_answer = False

# --- 메인 화면 ---
st.title("☁️ 구글 연동 암기장 (이미지 지원)")

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
            try:
                st.session_state.q_index = st.session_state.data.index(st.session_state.current_q)
            except:
                st.session_state.q_index = 0
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
            
            # 이미지가 있으면 보여주기
            if q.get('img') and str(q['img']).startswith('http'):
                st.image(q['img'], caption="참고 이미지")
            
            c1, c2 = st.columns(2)
            with c1:
                if st.button("O 맞음"):
                    idx = st.session_state.q_index
                    st.session_state.data[idx]['tried'] += 1
                    st.session_state.data[idx]['correct'] += 1
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
    st.info("💡 폰에서 접속하면 카메라로 바로 찍어 올릴 수 있습니다!")
    with st.form("add"):
        s = st.text_input("과목")
        q = st.text_area("문제")
        a = st.text_area("정답")
        img_file = st.file_uploader("이미지 첨부 (선택)", type=['png', 'jpg', 'jpeg'])
        
        if st.form_submit_button("저장"):
            img_url = ""
            # 이미지가 있으면 업로드 시도
            if img_file:
                with st.spinner("이미지 업로드 중..."):
                    uploaded_url = upload_to_imgbb(img_file)
                    if uploaded_url:
                        img_url = uploaded_url
                    else:
                        st.warning("이미지 업로드 실패. 텍스트만 저장합니다.")
            
            new = {'subject': s, 'q': q, 'a': a, 'img': img_url}
            add_data_to_sheet(new) # 구글 시트에 저장
            st.session_state.data = load_data() # 데이터 다시 불러오기
            st.success("추가되었습니다!")

# --- 3. 관리 ---
elif menu == "목록/관리":
    st.write("구글 시트의 데이터입니다.")
    st.dataframe(st.session_state.data)
    st.caption("수정/삭제는 구글 스프레드시트에서 직접 하는 것이 더 빠르고 정확합니다.")
