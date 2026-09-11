"""Streamlit frontend for the Crop Pest & Disease platform.

Pages (chosen by role in the sidebar):
  🔎 Scan crop      — upload photo + field context -> detections + localized advisory
  🌦 Risk forecast  — weather-based per-pest risk for a village/GPS point
  📝 Field report   — farmer/extension observations without a photo
  ✅ Expert review  — confirm/reject AI scans, review field reports
  📊 Dashboard      — officials: hotspots, trend, top pests

Talks to the FastAPI backend over HTTP, so it needs no ML stack of its own.
Run:  streamlit run streamlit_app.py      (API_URL env var or sidebar field)
"""
from __future__ import annotations

import colorsys
import io
import os
from datetime import datetime

import requests
import streamlit as st
from PIL import Image, ImageDraw, ImageFont

API_URL = os.environ.get("API_URL", "http://127.0.0.1:8000").rstrip("/")
MAX_MB = 20

st.set_page_config(page_title="Crop Health Platform", page_icon="🌾", layout="wide")

# Role -> visible pages
ROLE_PAGES = {
    "👨‍🌾 Farmer": ["🔎 Scan crop", "🌦 Risk forecast", "📝 Field report"],
    "🧑‍🔬 Extension worker": [
        "🔎 Scan crop",
        "🌦 Risk forecast",
        "📝 Field report",
        "✅ Expert review",
        "📊 Dashboard",
    ],
    "🏛 Official": ["📊 Dashboard", "✅ Expert review"],
}
ROLES = list(ROLE_PAGES)

CROPS = ["rice", "wheat", "tomato", "potato", "cotton", "maize", "chilli", "okra", "sugarcane", "other"]
STAGES = ["seedling", "vegetative", "flowering", "fruiting", "panicle", "tillering", "maturity"]
LANGS = {"English": "en", "हिन्दी (Hindi)": "hi", "मराठी (Marathi)": "mr", "தமிழ் (Tamil)": "ta", "తెలుగు (Telugu)": "te"}


# ---------------------------------------------------------------- helpers ---
def color_for(name: str) -> tuple[int, int, int]:
    h = 0
    for ch in name:
        h = (h * 31 + ord(ch)) % 360
    r, g, b = colorsys.hsv_to_rgb(h / 360.0, 0.85, 0.6)
    return int(r * 255), int(g * 255), int(b * 255)


def draw_boxes(img: Image.Image, detections: list[dict]) -> Image.Image:
    img = img.convert("RGB")
    draw = ImageDraw.Draw(img)
    w = img.size[0]
    try:
        font = ImageFont.truetype("DejaVuSans-Bold.ttf", max(14, w // 38))
    except OSError:
        font = ImageFont.load_default()
    lw = max(2, w // 320)
    for det in detections:
        b = det["bbox"]
        x, y, bw, bh = b["x"], b["y"], b["width"], b["height"]
        color = color_for(det["class_name"])
        draw.rectangle([x, y, x + bw, y + bh], outline=color, width=lw)
        label = f"{det['class_name']} {det['confidence'] * 100:.0f}%"
        tb = draw.textbbox((0, 0), label, font=font)
        tw, th = tb[2] - tb[0], tb[3] - tb[1]
        ty = y - th - 6 if y - th - 6 >= 0 else y
        draw.rectangle([x, ty, x + tw + 8, ty + th + 8], fill=color)
        draw.text((x + 4, ty + 2), label, fill="white", font=font)
    return img


def api_get(path: str, **kw):
    return requests.get(API_URL + path, timeout=30, **kw)


def fmt(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return iso


# ------------------------------------------------------------ advisory UI ---
def show_advisory(class_name: str, confidence: float | None, lang: str) -> None:
    """Render the localized advisory panel for one detected class."""
    try:
        params = {"class_name": class_name, "lang": lang}
        if confidence is not None:
            params["confidence"] = confidence
        resp = api_get("/api/advisory", params=params)
        if resp.status_code == 404:
            st.caption(f"No advisory content for {class_name}.")
            return
        resp.raise_for_status()
        adv = resp.json()
    except Exception as e:  # noqa: BLE001
        st.warning(f"Advisory unavailable: {e}")
        return

    st.markdown(f"### 🌱 {adv['name']}")
    if adv.get("referral"):
        ref = adv["referral"]
        st.warning(f"**{ref['title']}** — {ref['text']}")
    with st.expander("✅ Management steps (IPM)", expanded=True):
        for step in adv.get("management", []):
            st.markdown(f"- {step}")
    with st.expander("⚠️ Safe pesticide use"):
        for tip in adv.get("safety", []):
            st.markdown(f"- {tip}")
    follow = adv.get("followup_days")
    if follow:
        st.info(f"🔁 Follow-up: re-scan or inspect again in **{follow} days**.")


# ------------------------------------------------------------- page: scan ---
def page_scan(lang: str) -> None:
    st.title("🔎 Scan a crop")
    st.caption("Upload a crop photo with field context — get detections, advisories and history.")

    col1, col2, col3 = st.columns(3)
    with col1:
        location = st.text_input("Village / town", key="scan_loc", help="Used for risk history & hotspots")
    with col2:
        crop = st.selectbox("Crop", ["—"] + CROPS)
    with col3:
        stage = st.selectbox("Growth stage", ["—"] + STAGES)

    use_gps = st.checkbox("Use GPS coordinates instead of village name")
    lat = lon = None
    if use_gps:
        gc1, gc2 = st.columns(2)
        lat = gc1.number_input("Latitude", value=23.25, format="%.4f")
        lon = gc2.number_input("Longitude", value=77.40, format="%.4f")

    uploaded = st.file_uploader("Crop photo", type=["jpg", "jpeg", "png", "webp"])
    if uploaded is None:
        return
    if uploaded.size > MAX_MB * 1024 * 1024:
        st.error(f"Image larger than the {MAX_MB} MB limit.")
        return
    if not st.button("Detect pests & diseases", type="primary"):
        return

    files = {"file": (uploaded.name, uploaded.getvalue(), uploaded.type or "image/jpeg")}
    form = {
        "location_name": location or None,
        "crop": None if crop == "—" else crop,
        "crop_stage": None if stage == "—" else stage,
    }
    if use_gps:
        form["latitude"], form["longitude"] = lat, lon
    form = {k: v for k, v in form.items() if v is not None}

    try:
        resp = requests.post(API_URL + "/api/detect", files=files, data=form, timeout=180)
        data = resp.json()
        if resp.status_code not in (200, 201):
            st.error(f"Detection failed ({resp.status_code}): {data.get('detail', data)}")
            return
    except requests.ConnectionError:
        st.error(f"Could not reach the API at {API_URL}. Start it with `uvicorn app.main:app`.")
        return
    except Exception as e:  # noqa: BLE001
        st.error(f"Detection error: {e}")
        return

    dets = data.get("detections", [])
    if data.get("status") == "affected":
        st.error(f"⚠ Pests / disease found ({len(dets)})")
    else:
        st.success("✓ Looks healthy — no pests detected")

    img = Image.open(io.BytesIO(uploaded.getvalue()))
    st.image(draw_boxes(img, dets), use_container_width=True)
    where = data.get("location_name") or (f"{data.get('latitude'):.3f}, {data.get('longitude'):.3f}" if data.get("latitude") is not None else "—")
    st.caption(
        f"scan #{data.get('id')} · model {data.get('model_version')} · "
        f"{data.get('image_width')}×{data.get('image_height')} · {where}"
        + (f" · {data.get('crop')} / {data.get('crop_stage')}" if data.get("crop") else "")
    )
    if dets:
        rows = [
            {
                "class": d["class_name"],
                "confidence": f"{d['confidence'] * 100:.1f}%",
                "x": round(d["bbox"]["x"], 1),
                "y": round(d["bbox"]["y"], 1),
                "w": round(d["bbox"]["width"], 1),
                "h": round(d["bbox"]["height"], 1),
            }
            for d in dets
        ]
        st.subheader("Detections")
        st.dataframe(rows, use_container_width=True, hide_index=True)

    # Localized advisory for every detected class (most confident first).
    st.divider()
    st.subheader(f"🧭 Advisory ({LANGS_INVERT.get(lang, lang)})")
    seen: set[str] = set()
    for d in sorted(dets, key=lambda d: d["confidence"], reverse=True):
        if d["class_name"] in seen:
            continue
        seen.add(d["class_name"])
        show_advisory(d["class_name"], d["confidence"], lang)


LANGS_INVERT = {v: k for k, v in LANGS.items()}


# ----------------------------------------------------- page: risk forecast ---
def page_risk() -> None:
    st.title("🌦 Weather-based risk forecast")
    st.caption("Pest/disease risk from the 3-day weather outlook + recent outbreaks near the location.")

    c1, c2, c3 = st.columns([2, 1, 1])
    location = c1.text_input("Village / town", key="risk_loc")
    crop = c2.selectbox("Crop", ["—"] + CROPS, key="risk_crop")
    stage = c3.selectbox("Stage", ["—"] + STAGES, key="risk_stage")

    if st.button("Get forecast", type="primary"):
        params = {}
        if location:
            params["location"] = location
        else:
            st.warning("Enter a village or town name.")
            return
        if crop != "—":
            params["crop"] = crop
        if stage != "—":
            params["crop_stage"] = stage
        try:
            resp = api_get("/api/risk", params=params)
            if resp.status_code != 200:
                st.error(f"Risk forecast failed: {resp.json().get('detail', resp.status_code)}")
                return
            risk = resp.json()
        except Exception as e:  # noqa: BLE001
            st.error(f"Request failed: {e}")
            return

        level_emoji = {"low": "🟢", "medium": "🟡", "high": "🟠", "severe": "🔴"}
        st.markdown(
            f"### Overall risk: {level_emoji.get(risk['overall_level'], '⚪')} "
            f"**{risk['overall_level'].upper()}**"
            + ("  _(cached weather — offline)_ " if risk.get("weather_stale") else "")
        )
        ws = risk.get("weather_summary") or {}
        m1, m2, m3 = st.columns(3)
        m1.metric("🌧 Rain (window)", f"{ws.get('rain_mm', '—')} mm")
        m2.metric("💧 Humidity", f"{ws.get('humidity_mean', '—')} %")
        m3.metric("🌡 Max temp", f"{ws.get('temp_max', '—')} °C")

        if risk.get("per_pest"):
            st.subheader("Per-pest risk")
            for p in risk["per_pest"]:
                emoji = level_emoji.get(p["level"], "⚪")
                with st.expander(f"{emoji} {p['target']} — {p['level']} (score {p['score']})"):
                    for driver in p["drivers"]:
                        st.markdown(f"- {driver}")
        else:
            st.info("No pest rules matched the current weather — risk is low.")
        if risk.get("history_driver"):
            st.caption(f"📍 {risk['history_driver']}")


# ---------------------------------------------------- page: field report ---
def page_report() -> None:
    st.title("📝 Field report")
    st.caption("Record what you see in the field — no photo needed. Reports feed risk forecasts and hotspots.")

    with st.form("report_form", clear_on_submit=True):
        c1, c2 = st.columns(2)
        role = c1.selectbox("I am a…", ["farmer", "extension", "expert"])
        name = c2.text_input("Name (optional)")
        location = st.text_input("Village / town")
        c3, c4 = st.columns(2)
        crop = c3.selectbox("Crop", ["—"] + CROPS)
        stage = c4.selectbox("Growth stage", ["—"] + STAGES)
        c5, c6 = st.columns(2)
        observed = c5.text_input("Pest / disease seen (optional)")
        severity = c6.select_slider("Severity", ["low", "medium", "high", "severe"], value="medium")
        notes = st.text_area("Notes (symptoms, affected area, …)")
        submitted = st.form_submit_button("Submit report", type="primary")

    if not submitted:
        return
    if not location and st.session_state.get("report_lat") is None:
        st.warning("Enter at least a village name.")
        return
    payload = {
        "reporter_role": role,
        "reporter_name": name or None,
        "location_name": location or None,
        "crop": None if crop == "—" else crop,
        "crop_stage": None if stage == "—" else stage,
        "observed_class": observed or None,
        "severity": severity,
        "notes": notes or None,
    }
    payload = {k: v for k, v in payload.items() if v is not None}
    try:
        resp = requests.post(API_URL + "/api/reports", json=payload, timeout=30)
        if resp.status_code == 201:
            st.success(f"✓ Report #{resp.json()['id']} saved. Thank you!")
        else:
            st.error(f"Failed ({resp.status_code}): {resp.json().get('detail', resp.text)}")
    except Exception as e:  # noqa: BLE001
        st.error(f"Request failed: {e}")


# --------------------------------------------------- page: expert review ---
def page_review() -> None:
    st.title("✅ Expert review")
    st.caption("Confirm or correct AI scans. Confirmed data trains the next model (export script).")

    tab_scans, tab_reports = st.tabs(["🖼 AI scans", "📝 Field reports"])

    with tab_scans:
        try:
            resp = api_get("/api/reviews/pending")
            resp.raise_for_status()
            queue = resp.json().get("items", [])
        except Exception as e:  # noqa: BLE001
            st.error(f"Could not load queue: {e}")
            return
        if not queue:
            st.success("Queue is empty — every scan has been reviewed. 🎉")
            return

        labels = {
            f"#{it['scan']['id']} · {it['scan']['filename']} · {it['scan']['detection_count']} det": it
            for it in queue
        }
        pick = st.selectbox("Scan to review", list(labels))
        item = labels[pick]
        scan = item["scan"]

        try:
            detail = api_get(f"/api/scans/{scan['id']}").json()
            img_bytes = api_get(f"/api/scans/{scan['id']}/image").content
            img = Image.open(io.BytesIO(img_bytes))
            st.image(draw_boxes(img, detail.get("detections", [])), use_container_width=True)
        except Exception as e:  # noqa: BLE001
            st.warning(f"Could not load image: {e}")
            detail = {"detections": []}

        if detail.get("detections"):
            st.dataframe(
                [
                    {"class": d["class_name"], "confidence": f"{d['confidence'] * 100:.1f}%"}
                    for d in detail["detections"]
                ],
                use_container_width=True,
                hide_index=True,
            )

        c1, c2 = st.columns(2)
        reviewer = c1.text_input("Your name", key="rev_name")
        correct_to = c2.text_input("Correct class (optional, e.g. rice_blast)")

        b1, b2, b3, _ = st.columns([1, 1, 1, 2])
        verdict_payload = {
            "scan_id": scan["id"],
            "reviewer_name": reviewer or None,
            "corrected_class": correct_to or None,
        }
        if b1.button("✅ Confirm", type="primary"):
            requests.post(API_URL + "/api/reviews", json={**verdict_payload, "verdict": "confirmed"}, timeout=30)
            st.success("Confirmed — added to training export.")
            st.rerun()
        if b2.button("❌ Reject"):
            requests.post(API_URL + "/api/reviews", json={**verdict_payload, "verdict": "rejected"}, timeout=30)
            st.warning("Rejected — kept as background sample.")
            st.rerun()
        if b3.button("🔬 Needs lab"):
            requests.post(API_URL + "/api/reviews", json={**verdict_payload, "verdict": "needs_lab"}, timeout=30)
            st.info("Flagged for laboratory diagnosis.")
            st.rerun()

    with tab_reports:
        try:
            resp = api_get("/api/reports?limit=50")
            resp.raise_for_status()
            reports = resp.json().get("items", [])
        except Exception as e:  # noqa: BLE001
            st.error(f"Could not load reports: {e}")
            return
        if not reports:
            st.info("No field reports yet.")
            return
        for r in reports:
            sev = {"low": "🟢", "medium": "🟡", "high": "🟠", "severe": "🔴"}.get(r["severity"], "⚪")
            where = r.get("location_name") or (f"{r['latitude']:.3f}, {r['longitude']:.3f}" if r.get("latitude") is not None else "—")
            head = f"{sev} #{r['id']} · {where} · {r.get('crop') or '?'} · {r.get('observed_class') or 'unidentified'}"
            with st.expander(head):
                st.markdown(
                    f"**{r['reporter_role']}** {r.get('reporter_name') or 'anonymous'} · "
                    f"{fmt(r['created_at'])} · status: {r['status']} · reviews: {r['review_count']}"
                )
                if r.get("notes"):
                    st.markdown(f"> {r['notes']}")
                if r["status"] == "open":
                    verdict = st.radio("Verdict", ["confirmed", "rejected", "needs_lab"], key=f"v{r['id']}", horizontal=True)
                    if st.button("Submit review", key=f"sub{r['id']}"):
                        requests.post(
                            API_URL + "/api/reviews",
                            json={"field_report_id": r["id"], "verdict": verdict, "reviewer_name": reviewer or None},
                            timeout=30,
                        )
                        st.rerun()


# ------------------------------------------------------ page: dashboard ---
def page_dashboard() -> None:
    st.title("📊 Officials dashboard")
    st.caption("Surveillance overview: hotspots, trends and the most pressing pests.")

    try:
        stats = api_get("/api/stats/summary").json()
        hotspots = api_get("/api/hotspots?days=14").json()
    except Exception as e:  # noqa: BLE001
        st.error(f"Could not load dashboard data: {e}")
        return

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Total scans", stats["total_scans"])
    m2.metric("Affected", stats["affected_scans"])
    m3.metric("Field reports", stats["total_reports"], delta=f"{stats['open_reports']} open")
    m4.metric("Confirmed", stats["confirmed_detections"])
    m5.metric("Rejected", stats["rejected_reviews"])

    st.subheader("14-day scan trend")
    trend = stats.get("trend_14d", [])
    if trend:
        chart_data = {p["date"]: {"scans": p["total"], "affected": p["affected"]} for p in trend}
        st.bar_chart(chart_data)

    c1, c2 = st.columns(2)
    with c1:
        st.subheader("🔝 Top pests (affected scans)")
        if stats.get("top_targets"):
            st.dataframe(
                [
                    {
                        "target": t["target"],
                        "detections": t["hits"],
                        "avg conf": f"{t['avg_confidence'] * 100:.0f}%",
                    }
                    for t in stats["top_targets"]
                ],
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.caption("No affected scans yet.")
    with c2:
        st.subheader("🔥 Hotspots (14 days)")
        cells = hotspots.get("cells", [])
        if cells:
            import pandas as pd

            map_df = pd.DataFrame(
                [
                    {
                        "lat": c["center_lat"],
                        "lon": c["center_lon"],
                        "size": max(c["affected"], 1),
                    }
                    for c in cells
                ]
            )
            st.map(map_df, size="size")
            st.dataframe(
                [
                    {
                        "center": f"{c['center_lat']:.2f}, {c['center_lon']:.2f}",
                        "scans": c["total"],
                        "affected": c["affected"],
                        "reports": c["reports"],
                        "top pest": c["top_target"] or "—",
                    }
                    for c in cells[:15]
                ],
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.caption("No located scans/reports in the last 14 days.")


# ------------------------------------------------------------------ main ---
def main() -> None:
    global API_URL  # noqa: PLW0603
    with st.sidebar:
        st.title("🌾 Crop Health")
        role = st.radio("Sign in as", ROLES, key="role", index=0)
        st.divider()

        api = st.text_input("API URL", value=API_URL)
        if api.rstrip("/") != API_URL:
            API_URL = api.rstrip("/")
            st.rerun()

        lang_label = st.selectbox("Advisory language", list(LANGS), index=0)

        try:
            h = api_get("/api/health").json()
            if h.get("model_loaded"):
                st.success(f"Model: {h.get('model_version')} · {h.get('device')}")
                if h.get("fallback_in_use"):
                    st.warning("Fallback model — train a pest model for real results.")
            else:
                st.error(f"Model not loaded: {h.get('error')}")
        except requests.ConnectionError:
            st.error("API unreachable — start with `uvicorn app.main:app`")
        except Exception as e:  # noqa: BLE001
            st.error(f"Health check failed: {e}")

        st.divider()
        st.subheader("Recent scans")
        try:
            items = api_get("/api/scans?limit=10").json().get("items", [])
            if not items:
                st.caption("No scans yet.")
            else:
                for it in items:
                    mark = "⚠️" if it["status"] == "affected" else "✅"
                    st.caption(f"{mark} #{it['id']} · {it['filename'][:18]} · {it['detection_count']} det")
        except Exception:  # noqa: BLE001
            st.caption("History unavailable (API down).")

    page = st.radio(
        "Go to",
        ROLE_PAGES[role],
        label_visibility="collapsed",
        horizontal=True,
    )
    lang = LANGS[lang_label]

    if page == "🔎 Scan crop":
        page_scan(lang)
    elif page == "🌦 Risk forecast":
        page_risk()
    elif page == "📝 Field report":
        page_report()
    elif page == "✅ Expert review":
        page_review()
    elif page == "📊 Dashboard":
        page_dashboard()


if __name__ == "__main__":
    main()
