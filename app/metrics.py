from datetime import date, timedelta

from flask import Blueprint, redirect, request, url_for

from app.db import db
from app.models import BodyMetric
from app.parsing import parse_weight

bp = Blueprint("metrics", __name__)


def week_start_for(day: date) -> date:
    """这个日期所在那一周的周一。"""
    return day - timedelta(days=day.weekday())


@bp.post("/metrics/<iso_date>")
def save_metric(iso_date: str):
    try:
        day = date.fromisoformat(iso_date)
    except ValueError:
        return "无效日期", 400

    week_start = week_start_for(day)
    weight = parse_weight(request.form.get("weight"))
    if weight is None:
        return "体重没填对", 400

    metric = BodyMetric.query.filter_by(week_start=week_start).one_or_none()
    if metric is None:
        metric = BodyMetric(week_start=week_start, weight_kg=weight)
        db.session.add(metric)
    metric.weight_kg = weight
    metric.body_fat_pct = parse_weight(request.form.get("body_fat"))
    metric.note = (request.form.get("note") or "").strip() or None
    db.session.commit()

    return redirect(
        url_for("calendar.index", month=week_start.strftime("%Y-%m")), code=303
    )
