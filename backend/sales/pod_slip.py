"""Proof-of-delivery slip. Not a tax invoice."""

from io import BytesIO

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from core.exceptions import BusinessRuleError

from .models import DeliveryRouteStop


def render_pod_pdf(stop: DeliveryRouteStop) -> bytes:
    if stop.status != DeliveryRouteStop.StopStatus.DELIVERED:
        raise BusinessRuleError("A slip is printed for a delivered stop.")
    route = stop.route
    order = stop.sales_order
    buf = BytesIO()
    pdf = canvas.Canvas(buf, pagesize=A4)
    y = 800
    pdf.setFont("Helvetica-Bold", 14)
    pdf.drawString(40, y, "Proof of delivery")
    pdf.setFont("Helvetica", 11)
    y -= 28
    pdf.drawString(40, y, f"Route {route.number or route.pk}  {route.route_date}")
    y -= 18
    pdf.drawString(40, y, f"Customer {order.customer.name}")
    y -= 18
    pdf.drawString(40, y, f"Received by {stop.received_by_name}")
    y -= 18
    delivered = stop.delivered_at.isoformat() if stop.delivered_at else ""
    pdf.drawString(40, y, f"Delivered at {delivered}")
    y -= 18
    photo_name = ""
    if stop.pod_photo_id and getattr(stop.pod_photo, "file", None):
        photo_name = getattr(stop.pod_photo.file, "name", "") or ""
    pdf.drawString(40, y, f"Photo {photo_name}")
    y -= 28
    pdf.drawString(40, y, "Lines")
    for item in order.items.select_related("product"):
        y -= 16
        pdf.drawString(50, y, f"{item.product.name}  x {item.quantity}")
        if y < 60:
            pdf.showPage()
            y = 800
    pdf.save()
    return buf.getvalue()
