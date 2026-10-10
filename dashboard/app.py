"""Read-only local dashboard. Start through the tray or README command."""
from __future__ import annotations

from collections import Counter, defaultdict
from contextlib import closing
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
import os
import sys

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.config import load_settings
from src.storage import read_only

st.set_page_config(page_title="Desk Guardian", page_icon=":material/monitoring:", layout="wide")
default_config = ROOT / ("config.local.yaml" if (ROOT / "config.local.yaml").exists() else "config.yaml")
settings = load_settings(Path(os.environ.get("DESK_GUARDIAN_CONFIG", default_config)))
local_zone = datetime.now().astimezone().tzinfo


@st.cache_data(ttl=15, max_entries=8)
def load_day(db_path: str, day):
    start = datetime.combine(day, time.min, local_zone).astimezone(timezone.utc)
    end = datetime.combine(day + timedelta(days=1), time.min, local_zone).astimezone(timezone.utc)
    with closing(read_only(Path(db_path))) as db:
        minutes = [dict(row) for row in db.execute(
            "SELECT * FROM minute_stats WHERE ts_minute>=? AND ts_minute<? ORDER BY ts_minute",
            (start.isoformat(timespec="seconds"), end.isoformat(timespec="seconds")))]
        events = [dict(row) for row in db.execute(
            "SELECT ts,type,detail FROM events WHERE ts>=? AND ts<? ORDER BY ts",
            (start.isoformat(timespec="seconds"), end.isoformat(timespec="seconds")))]
        sessions = [dict(row) for row in db.execute(
            "SELECT * FROM focus_sessions WHERE end_ts>? AND start_ts<?",
            (start.isoformat(timespec="seconds"), end.isoformat(timespec="seconds")))]
    return minutes, events, sessions


def local_time(iso):
    return datetime.fromisoformat(iso).astimezone(local_zone)


st.title("Desk Guardian")
st.caption("내 컴퓨터에서만 읽는 자리·자세·집중 기록")
with st.container(horizontal=True, gap="small"):
    st.badge("로컬 전용", icon=":material/lock:", color="green")
    st.badge("15초마다 갱신", icon=":material/sync:", color="gray")
with st.sidebar:
    day = st.date_input("날짜", value=datetime.now().date(), max_value=datetime.now().date())
    st.caption("기록은 15초 간격으로 새로고침됩니다. 브라우저를 새로고침해 최신 값을 보세요.")

if not settings.db_path.exists():
    st.info("아직 측정 기록이 없습니다. 트레이 앱을 실행하면 이곳에 기록이 나타납니다.")
    st.stop()

try:
    minutes, events, sessions = load_day(str(settings.db_path), day)
except Exception:
    st.error("기록을 읽을 수 없습니다. 트레이 앱의 로그를 확인해 주세요.")
    st.stop()

if not minutes and not events:
    st.info("선택한 날짜에 기록이 없습니다.")
    st.stop()

present_minutes = sum(float(row["present_ratio"]) for row in minutes)
scores = [float(row["focus_score"]) for row in minutes if row["focus_score"] is not None]
longest = max(((local_time(row["end_ts"]) - local_time(row["start_ts"])).total_seconds() / 60
               for row in sessions), default=0)
posture_events = [row for row in events if row["type"] == "posture_alert"]
sleep_count = sum(row["type"] == "sleep" for row in events)

with st.container(horizontal=True):
    st.metric("자리 유지", f"{present_minutes / 60:.1f}시간", border=True)
    st.metric("평균 집중 추정치", f"{sum(scores)/len(scores):.0f}점" if scores else "—", border=True)
    st.metric("최장 집중 세션", f"{longest:.0f}분", border=True)
    st.metric("자세 알림", f"{len(posture_events)}회", border=True)
    st.metric("실제 절전", f"{sleep_count}회", border=True)

st.caption("집중 추정치는 정면 응시·입력·앱 전환으로 계산합니다. 영상을 볼 때는 입력이 없어도 70점이 될 수 있고, 정상적인 앱 전환도 감점될 수 있습니다. 생산성 평가 지표로 사용하지 마세요.")

col_left, col_right = st.columns([2, 1])
with col_left:
    with st.container(border=True):
        st.subheader("분별 집중 추정치")
        if minutes:
            fig = go.Figure()
            away = [row for row in minutes if row["label"] == "away"]
            if away:
                fig.add_trace(go.Bar(x=[local_time(row["ts_minute"]) for row in away],
                                     y=[100] * len(away), width=60_000, marker_color="rgba(156,163,175,.22)",
                                     name="자리 비움", hoverinfo="skip"))
            scored = [row for row in minutes if row["focus_score"] is not None]
            fig.add_trace(go.Scatter(x=[local_time(row["ts_minute"]) for row in scored],
                                     y=[row["focus_score"] for row in scored], mode="lines+markers",
                                     line=dict(color="#24a878", width=2), name="집중 추정치"))
            fig.update_layout(height=320, margin=dict(l=10,r=10,t=10,b=10),
                              yaxis=dict(range=[0,100], title="점수"), xaxis_title="시각",
                              legend=dict(orientation="h"), barmode="overlay")
            st.plotly_chart(fig, width="stretch")
        else:
            st.info("분별 기록이 없습니다.")
with col_right:
    with st.container(border=True):
        st.subheader("시간대별 평균")
        by_hour = defaultdict(list)
        for row in minutes:
            if row["focus_score"] is not None:
                by_hour[local_time(row["ts_minute"]).hour].append(row["focus_score"])
        if by_hour:
            frame = pd.DataFrame({"시간": [f"{hour:02d}시" for hour in sorted(by_hour)],
                                  "평균 점수": [sum(by_hour[hour])/len(by_hour[hour]) for hour in sorted(by_hour)]})
            st.bar_chart(frame, x="시간", y="평균 점수", y_label="점수")
        else:
            st.info("점수가 있는 시간이 없습니다.")

with st.container(border=True):
    st.subheader("자세 알림 유형")
    count = Counter(row["detail"] for row in posture_events)
    names = {"distance": "화면과 너무 가까움", "drop": "얼굴 위치 하강", "pitch": "고개 숙임", "roll": "고개 기울임"}
    if count:
        frame = pd.DataFrame({"유형": [names.get(k, k) for k in count], "횟수": list(count.values())})
        st.bar_chart(frame, x="유형", y="횟수")
    else:
        st.caption("자세 알림이 없습니다.")
