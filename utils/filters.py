from datetime import datetime, date, timezone, timedelta

WIB = timezone(timedelta(hours=7))


def rupiah_filter(value):
    try:
        if value is None:
            return 'Rp 0'
        num = float(value)
        formatted = f"{num:,.0f}".replace(',', '.')
        return f"Rp {formatted}"
    except (ValueError, TypeError):
        return 'Rp 0'


def format_date_filter(val):
    if not val:
        return '-'
    if isinstance(val, datetime):
        if val.tzinfo is None:
            val = val.replace(tzinfo=timezone.utc).astimezone(WIB)
        else:
            val = val.astimezone(WIB)
        val = val.date()
    if isinstance(val, date):
        months = [
            '', 'Jan', 'Feb', 'Mar', 'Apr', 'Mei', 'Jun',
            'Jul', 'Agt', 'Sep', 'Okt', 'Nov', 'Des'
        ]
        return f"{val.day} {months[val.month]} {val.year}"
    return str(val)


def format_datetime_filter(val):
    if not val:
        return '-'
    if isinstance(val, datetime):
        if val.tzinfo is None:
            val = val.replace(tzinfo=timezone.utc).astimezone(WIB)
        else:
            val = val.astimezone(WIB)
        months = [
            '', 'Jan', 'Feb', 'Mar', 'Apr', 'Mei', 'Jun',
            'Jul', 'Agt', 'Sep', 'Okt', 'Nov', 'Des'
        ]
        return f"{val.day} {months[val.month]} {val.year}, {val.strftime('%H:%M')}"
    return str(val)


def register_filters(app):
    app.add_template_filter(rupiah_filter, 'rupiah')
    app.add_template_filter(format_date_filter, 'format_date')
    app.add_template_filter(format_datetime_filter, 'format_datetime')
