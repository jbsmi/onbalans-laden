from datetime import datetime, timedelta


def make_html(now: datetime, prices: list[str]) -> str:
    """prices[0] = nieuwste minuut."""
    rows = []
    for i, p in enumerate(prices):
        t = now - timedelta(minutes=i)
        rows.append(
            f"<tr><td>{i+1}</td><td>{t.hour*60+t.minute+1}</td><td>{t:%H:%M}</td><td>165,0</td><td>0</td>"
            f"<td>0</td><td>0</td><td>{p}</td><td>{p}</td></tr>"
        )
    return (
        "<html><body><table class=\"imbalanceprices\"><tbody>"
        "<tr class=\"header footer\"><td colspan=\"3\">Tijdsindicatie</td><td colspan=\"4\">Geactiveerd vermogen</td><td colspan=\"2\">Prijsvorming</td></tr>"
        "<tr class=\"header footer\"><td>Nummer</td><td>Volgnummer</td><td>Tijd</td><td>Opregelen</td><td>Afregelen</td>"
        "<td>Noodvermogen op</td><td>Noodvermogen af</td><td>Invoeden (€/MWh)</td><td>Afnemen (€/MWh)</td></tr>"
        + "".join(rows)
        + "</tbody></table></body></html>"
    )
