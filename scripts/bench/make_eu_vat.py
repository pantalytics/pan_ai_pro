#!/usr/bin/env python3
# Copyright 2025-2026 Pantalytics B.V. All rights reserved.
# SPDX-License-Identifier: Elastic-2.0
"""Generate the EU VAT bench set: fictional vendor bills to a Dutch buyer.

Nine VAT scenarios (see SCENARIOS), vendors in ten countries, labels and
number and date formats in the vendor's language, four layouts. Every
vendor, address and number is made up. The same seed gives the same set.

Usage:
    python scripts/bench/make_eu_vat.py OUT_DIR [--count 150] [--chrome PATH]

Writes OUT_DIR/<id>.pdf (printed by headless Chrome), OUT_DIR/<id>.html and
OUT_DIR/truth.jsonl in the format bench_invoices.py reads. Stdlib only.
"""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import random
import shutil
import subprocess
from pathlib import Path

BUYER = ("Bean Forge B.V.", "Koffiestraat 12", "3011 AB Rotterdam", "NL", "NL850123456B01")

L = {  # labels per language
    "nl": "Factuur|Factuurnummer|Factuurdatum|Vervaldatum|Aan|Omschrijving|Aantal|Prijs|Btw|Bedrag|Subtotaal|Btw|Totaal|Btw-nummer|Betaal binnen 30 dagen op",
    "de": "Rechnung|Rechnungsnummer|Rechnungsdatum|Fällig am|An|Beschreibung|Menge|Einzelpreis|MwSt.|Betrag|Zwischensumme|MwSt.|Gesamtbetrag|USt-IdNr.|Zahlbar innerhalb 30 Tagen auf",
    "fr": "Facture|N° de facture|Date de facture|Échéance|À|Désignation|Qté|Prix unitaire|TVA|Montant|Total HT|TVA|Total TTC|N° TVA|Paiement à 30 jours sur",
    "es": "Factura|Nº de factura|Fecha|Vencimiento|Para|Descripción|Cantidad|Precio|IVA|Importe|Base imponible|IVA|Total|NIF-IVA|Pago a 30 días en",
    "it": "Fattura|Numero fattura|Data fattura|Scadenza|A|Descrizione|Q.tà|Prezzo|IVA|Importo|Imponibile|IVA|Totale|Partita IVA|Pagamento a 30 giorni su",
    "en": "Invoice|Invoice number|Invoice date|Due date|Bill to|Description|Qty|Unit price|VAT|Amount|Subtotal|VAT|Total|VAT number|Please pay within 30 days to",
}
KEYS = "title no date due to desc qty price vat amount subtotal vattotal total vatno pay".split()

# country -> (language, currency, decimal sep, thousands sep, date format, IBAN bank code)
COUNTRY = {
    "NL": ("nl", "EUR", ",", ".", "%d-%m-%Y", "ABNA"),
    "BE": ("nl", "EUR", ",", ".", "%d/%m/%Y", "GEBA"),
    "DE": ("de", "EUR", ",", ".", "%d.%m.%Y", "37040044"),
    "FR": ("fr", "EUR", ",", " ", "%d/%m/%Y", "30004"),
    "ES": ("es", "EUR", ",", ".", "%d/%m/%Y", "2100"),
    "IT": ("it", "EUR", ",", ".", "%d/%m/%Y", "X0542811101"),
    "IE": ("en", "EUR", ".", ",", "%d %B %Y", "AIBK"),
    "GB": ("en", "GBP", ".", ",", "%d %B %Y", "BARC"),
    "US": ("en", "USD", ".", ",", "%m/%d/%Y", None),
    "CH": ("de", "CHF", ".", "'", "%d.%m.%Y", "0076"),
}
IBAN_LEN = {
    "NL": 18,
    "BE": 16,
    "DE": 22,
    "FR": 27,
    "ES": 24,
    "IT": 27,
    "IE": 22,
    "GB": 22,
    "CH": 21,
}

NAMES = {
    "nl": (["De Groot", "Van Dijk", "Bakker", "Visser", "Mulder", "Jansen", "Smit"], ["B.V."]),
    "de": (["Brandt", "Keller", "Hoffmann", "Lindner", "Vogt", "Krämer"], ["GmbH", "KG"]),
    "fr": (["Morel", "Lefèvre", "Garnier", "Rousseau", "Chevalier"], ["SARL", "SAS"]),
    "es": (["Navarro", "Ortega", "Delgado", "Romero"], ["S.L.", "S.A."]),
    "it": (["Ferraro", "Colombo", "Ricci", "Marino"], ["S.r.l.", "S.p.A."]),
    "en": (["Hartley", "Whitmore", "Ashford", "Calloway", "Pembroke"], ["Ltd", "Inc."]),
}
TRADE = {
    "goods": {"nl": "Verpakkingen", "de": "Verpackungen", "fr": "Emballages", "es": "Envases",
              "it": "Imballaggi", "en": "Packaging"},
    "food": {"nl": "Groothandel", "de": "Lebensmittel", "fr": "Alimentation", "es": "Alimentos",
             "it": "Alimentari", "en": "Foods"},
    "service": {"nl": "Diensten", "de": "Dienstleistungen", "fr": "Services", "es": "Servicios",
                "it": "Servizi", "en": "Software"},
    "hotel": {"nl": "Hotel", "de": "Hotel", "fr": "Hôtel", "es": "Hotel", "it": "Hotel", "en": "Hotel"},
}  # fmt: skip

# Catalogue: (kind, {language: description}, price range)
ITEMS = {
    "goods": [
        ({"nl": "Koffiezakken 250 g met ventiel", "de": "Kaffeebeutel 250 g mit Ventil",
          "fr": "Sachets café 250 g avec valve", "es": "Bolsas de café 250 g con válvula",
          "it": "Buste caffè 250 g con valvola", "en": "Coffee bags 250 g with valve"}, (0.12, 0.4)),
        ({"nl": "Verzenddozen 30x20x10", "de": "Versandkartons 30x20x10", "fr": "Cartons d'expédition 30x20x10",
          "es": "Cajas de envío 30x20x10", "it": "Scatole spedizione 30x20x10",
          "en": "Shipping boxes 30x20x10"}, (0.6, 1.8)),
        ({"nl": "Brandertrommel lager", "de": "Röstertrommel-Lager", "fr": "Roulement de tambour torréfacteur",
          "es": "Rodamiento de tambor tostador", "it": "Cuscinetto tamburo tostatrice",
          "en": "Roaster drum bearing"}, (45, 320)),
        ({"nl": "Molen maalschijven set", "de": "Mahlscheiben-Set Mühle", "fr": "Jeu de meules broyeur",
          "es": "Juego de muelas molino", "it": "Set macine macinino", "en": "Grinder burr set"}, (60, 240)),
    ],
    "food": [
        ({"nl": "Biologische melk 1 L", "de": "Bio-Milch 1 L", "fr": "Lait bio 1 L", "es": "Leche ecológica 1 L",
          "it": "Latte biologico 1 L", "en": "Organic milk 1 L"}, (0.9, 1.6)),
        ({"nl": "Groene koffiebonen Brazilië 60 kg", "de": "Rohkaffee Brasilien 60 kg",
          "fr": "Café vert Brésil 60 kg", "es": "Café verde Brasil 60 kg", "it": "Caffè verde Brasile 60 kg",
          "en": "Green coffee Brazil 60 kg"}, (280, 520)),
        ({"nl": "Vanillesiroop 750 ml", "de": "Vanillesirup 750 ml", "fr": "Sirop vanille 750 ml",
          "es": "Sirope de vainilla 750 ml", "it": "Sciroppo vaniglia 750 ml", "en": "Vanilla syrup 750 ml"},
         (4, 9)),
    ],
    "nl_21_extra": [({"nl": "Schoonmaakmiddel espressomachine"}, (8, 25)), ({"nl": "Kantoorbenodigdheden"}, (12, 80))],
    "exempt": [({"nl": "Bedrijfsaansprakelijkheidsverzekering 2027"}, (400, 1400)),
               ({"nl": "Cursus barista niveau 2 (beroepsonderwijs)"}, (250, 900))],
    "nl_rc": [({"nl": "Onderaanneming installatie afzuiging brander"}, (900, 4200)),
              ({"nl": "Schoonmaakwerkzaamheden productiehal (onderaanneming)"}, (300, 1200))],
    "service": [
        ({"en": "Subscription Pro plan, monthly", "de": "Abonnement Pro, monatlich",
          "fr": "Abonnement Pro, mensuel", "es": "Suscripción Pro, mensual", "it": "Abbonamento Pro, mensile"},
         (49, 399)),
        ({"en": "Consultancy roast profiling", "de": "Beratung Röstprofile", "fr": "Conseil profils de torréfaction",
          "es": "Consultoría perfiles de tueste", "it": "Consulenza profili di tostatura"}, (450, 2400)),
    ],
    "hotel": [
        ({"de": "Übernachtung Einzelzimmer", "nl": "Overnachting eenpersoonskamer", "fr": "Nuitée chambre simple"},
         (89, 189), "low"),
        ({"de": "Frühstück", "nl": "Ontbijt", "fr": "Petit-déjeuner"}, (14, 24), "high"),
        ({"de": "Parkplatz", "nl": "Parkeren", "fr": "Parking"}, (12, 25), "high"),
    ],
}  # fmt: skip
FOREIGN_RATES = {"DE": (7, 19), "BE": (6, 21), "FR": (10, 20)}

NOTICE = {
    "exempt": {"nl": "Vrijgesteld van btw op grond van artikel 11 Wet OB 1968."},
    "reverse_charge_domestic": {"nl": "Btw verlegd naar {buyer_vat} (artikel 12 lid 5 Wet OB)."},
    "intra_eu_goods": {
        "nl": "Intracommunautaire levering, vrijgesteld van btw (art. 39bis WBTW). Btw-nr. afnemer: {buyer_vat}",
        "de": "Steuerfreie innergemeinschaftliche Lieferung gemäß § 4 Nr. 1b UStG. USt-IdNr. Empfänger: {buyer_vat}",
        "fr": "Exonération de TVA, article 262 ter I du CGI. N° TVA client : {buyer_vat}",
        "es": "Entrega intracomunitaria exenta, art. 25 Ley 37/1992. NIF-IVA cliente: {buyer_vat}",
        "it": "Operazione non imponibile art. 41 D.L. 331/1993. P.IVA cliente: {buyer_vat}",
    },
    "intra_eu_services": {
        "en": "Reverse charge: VAT to be accounted for by the recipient, Art. 196 Directive 2006/112/EC.",
        "de": "Steuerschuldnerschaft des Leistungsempfängers (Reverse Charge).",
        "fr": "Autoliquidation, article 283-2 du CGI.",
        "es": "Inversión del sujeto pasivo, art. 84 Ley 37/1992.",
        "it": "Inversione contabile, art. 7-ter D.P.R. 633/1972.",
    },
    "non_eu": {"en": "Export of goods/services outside the UK/EU: no VAT charged.",
               "de": "Export, nicht steuerbar in der Schweiz."},
}  # fmt: skip

# code: (vendor countries, catalogue kinds, treatment, NL rate or None, bill count share)
SCENARIOS = {
    "nl_21": (["NL"], ["goods", "nl_21_extra"], "standard", 21),
    "nl_9": (["NL"], ["food"], "standard", 9),
    "nl_mixed": (["NL"], ["food", "goods"], "standard", None),
    "nl_exempt": (["NL"], ["exempt"], "exempt", 0),
    "nl_reverse_charge": (["NL"], ["nl_rc"], "reverse_charge_domestic", 0),
    "eu_goods": (["BE", "DE", "FR", "ES", "IT"], ["goods", "food"], "intra_eu_goods", 0),
    "eu_services": (["IE", "DE", "FR", "ES", "IT"], ["service"], "intra_eu_services", 0),
    "non_eu": (["GB", "US", "CH"], ["goods", "service"], "non_eu", 0),
    "foreign_vat": (["DE", "BE", "FR"], ["hotel"], "foreign_vat", None),
}
LAYOUTS = ("classic", "modern", "compact", "letter")


def iban(country: str, rng: random.Random) -> str | None:
    bank = COUNTRY[country][5]
    if not bank:
        return None
    body = bank + "".join(
        rng.choice("0123456789") for _ in range(IBAN_LEN[country] - 4 - len(bank))
    )
    digits = "".join(str(int(c, 36)) for c in body + country + "00")
    return f"{country}{98 - int(digits) % 97:02d}{body}"


def vat_no(country: str, rng: random.Random) -> str:
    d = lambda n: "".join(rng.choice("0123456789") for _ in range(n))  # noqa: E731
    return {
        "NL": f"NL{d(9)}B01", "BE": f"BE0{d(9)}", "DE": f"DE{d(9)}", "FR": f"FR{d(2)}{d(9)}",
        "ES": f"ESB{d(8)}", "IT": f"IT{d(11)}", "IE": f"IE{d(7)}WH", "GB": f"GB{d(9)}",
        "US": f"EIN {d(2)}-{d(7)}", "CH": f"CHE-{d(3)}.{d(3)}.{d(3)} MWST",
    }[country]  # fmt: skip


def money(x: float, country: str) -> str:
    dec, thou = COUNTRY[country][2], COUNTRY[country][3]
    s = f"{x:,.2f}".replace(",", "\x00").replace(".", dec).replace("\x00", thou)
    return s


def make_bill(n: int, scenario: str, rng: random.Random) -> tuple[dict, str]:
    countries, kinds, treatment, rate = SCENARIOS[scenario]
    country = rng.choice(countries)
    lang, cur = COUNTRY[country][0], COUNTRY[country][1]
    lab = dict(zip(KEYS, L[lang].split("|"), strict=True))
    trade = (
        "hotel" if scenario == "foreign_vat" else ("service" if "service" in kinds else kinds[0])
    )
    trade = "goods" if trade in ("nl_21_extra", "exempt", "nl_rc") else trade
    last, forms = NAMES[lang]
    name = f"{rng.choice(last)} {TRADE.get(trade, TRADE['goods'])[lang]} {rng.choice(forms)}"
    vat = vat_no(country, rng)
    bank = iban(country, rng)
    date = dt.date(2026, 1, 5) + dt.timedelta(days=rng.randrange(300))
    due = date + dt.timedelta(days=30)
    ref = rng.choice(["{y}-{n:04d}", "INV{y}{n:05d}", "F{n:06d}", "{n:05d}/{y}", "RE-{y}-{n:03d}"])
    ref = ref.format(y=date.year, n=rng.randrange(1, 99999))
    lines = []
    pool = [(kind, i) for kind in kinds for i in range(len(ITEMS[kind]))]
    picks = rng.sample(pool, rng.randint(1, min(5, len(pool))))
    if scenario == "nl_mixed":  # both rates on the bill
        food = [p for p in pool if p[0] == "food"]
        other = [p for p in pool if p[0] != "food"]
        rest = [p for p in picks if p in food or p in other][:3]
        picks = [*dict.fromkeys([rng.choice(food), rng.choice(other), *rest])]
    picks = [(kind, ITEMS[kind][i]) for kind, i in picks]
    for kind, item in picks:
        desc = item[0].get(lang) or item[0].get("nl") or item[0]["en"]
        price = round(rng.uniform(*item[1]), 2)
        if scenario == "foreign_vat":
            qty = rng.choice([1, 1, 2, 3])
        else:
            qty = (
                rng.choice([1, 1, 1, 2, 3, 5, 10, 25, 50, 100])
                if price < 50
                else rng.choice([1, 1, 2])
            )
        if scenario == "foreign_vat":
            low, high = FOREIGN_RATES[country]
            line_rate = low if item[2] == "low" else high
        elif rate is None:  # nl_mixed
            line_rate = 9 if kind == "food" else 21
        else:
            line_rate = rate
        lines.append({"description": desc, "quantity": float(qty), "unit_price": price,
                      "tax_rate": float(line_rate), "net": round(qty * price, 2)})  # fmt: skip
    untaxed = round(sum(x["net"] for x in lines), 2)
    by_rate: dict[float, float] = {}
    for x in lines:
        by_rate[x["tax_rate"]] = by_rate.get(x["tax_rate"], 0) + x["net"]
    vat_by_rate = {r: round(b * r / 100, 2) for r, b in by_rate.items()}
    tax = round(sum(vat_by_rate.values()), 2)
    total = round(untaxed + tax, 2)
    notice = NOTICE.get(treatment, {})
    notice = (notice.get(lang) or notice.get("en") or notice.get("nl") or "").format(
        buyer_vat=BUYER[4]
    )
    truth = {
        "id": f"euvat-{n:03d}", "file": f"euvat-{n:03d}.pdf", "scenario": scenario,
        "vendor_name": name, "vendor_vat": vat, "vendor_country": country,
        "invoice_ref": ref, "invoice_date": date.isoformat(), "due_date": due.isoformat(),
        "currency": cur, "untaxed": untaxed, "tax": tax, "total": total, "iban": bank,
        "vat_treatment": treatment,
        "lines": [{k: x[k] for k in ("description", "quantity", "unit_price", "tax_rate")} for x in lines],
    }  # fmt: skip
    layout = LAYOUTS[n % len(LAYOUTS)]
    return truth, render(truth, lab, layout, notice, country)


CSS = """
body{font-family:Helvetica,Arial,sans-serif;font-size:10.5pt;color:#222;margin:0}
.page{padding:18mm 16mm} table{width:100%;border-collapse:collapse;margin-top:8mm}
th,td{padding:4px 6px;text-align:left} td.n,th.n{text-align:right}
.tot{width:45%;margin-left:auto} .tot td{border:0} .notice{margin-top:6mm;font-style:italic}
.foot{margin-top:12mm;font-size:8.5pt;color:#555;border-top:1px solid #ccc;padding-top:3mm}
.classic th{border-bottom:2px solid #222} .classic td{border-bottom:1px solid #ddd}
.modern .band{background:#1f3a5f;color:#fff;padding:8mm 16mm;margin:-18mm -16mm 8mm}
.modern th{background:#eef2f7} .compact{font-size:9pt} .compact .page{padding:10mm}
.compact table{margin-top:4mm} .letter .addr{margin-top:22mm;margin-left:95mm}
.row{display:flex;justify-content:space-between} h1{font-size:20pt;margin:0 0 4mm}
"""


def render(t: dict, lab: dict, layout: str, notice: str, country: str) -> str:
    e = html.escape
    fmt = COUNTRY[country][4]
    d = lambda iso: dt.date.fromisoformat(iso).strftime(fmt)  # noqa: E731
    m = lambda x: money(x, country)  # noqa: E731
    sign = {"EUR": "€", "GBP": "£", "USD": "$", "CHF": "CHF"}[t["currency"]]
    rc = t["vat_treatment"] not in ("standard", "foreign_vat")
    rows = "".join(
        f"<tr><td>{e(x['description'])}</td><td class=n>{m(x['quantity']).rstrip('0').rstrip(',.')}"
        f"</td><td class=n>{m(x['unit_price'])}</td>"
        f"<td class=n>{'0%' if rc else f'{x["tax_rate"]:g}%'}</td>"
        f"<td class=n>{m(round(x['quantity'] * x['unit_price'], 2))}</td></tr>"
        for x in t["lines"]
    )
    rates: dict[float, float] = {}
    for x in t["lines"]:
        rates[x["tax_rate"]] = rates.get(x["tax_rate"], 0) + round(
            x["quantity"] * x["unit_price"], 2
        )
    vat_rows = "".join(
        f"<tr><td>{lab['vattotal']} {r:g}%</td><td class=n>{sign} {m(round(b * r / 100, 2))}</td></tr>"
        for r, b in sorted(rates.items())
    )
    seller = f"<b>{e(t['vendor_name'])}</b><br>{lab['vatno']}: {e(t['vendor_vat'])}" + (
        f"<br>IBAN: {e(t['iban'])}" if t["iban"] else "<br>Account 000123456789, routing 021000021"
    )
    buyer = "<br>".join(e(x) for x in BUYER[:3]) + f"<br>{lab['vatno']}: {BUYER[4]}"
    meta = (
        f"{lab['no']}: <b>{e(t['invoice_ref'])}</b><br>{lab['date']}: {d(t['invoice_date'])}"
        f"<br>{lab['due']}: {d(t['due_date'])}"
    )
    head = f"<div class=row><div>{seller}</div><div>{meta}</div></div>"
    if layout == "modern":
        head = f"<div class=band><h1>{lab['title']}</h1>{e(t['vendor_name'])}</div>" + (
            f"<div class=row><div>{lab['to']}:<br>{buyer}</div><div>{meta}</div></div>"
        )
        buyer_block = ""
    elif layout == "letter":
        head = f"<b>{e(t['vendor_name'])}</b><div class=addr>{buyer}</div><h1>{lab['title']}</h1>{meta}"
        buyer_block = ""
    else:
        buyer_block = f"<p>{lab['to']}:<br>{buyer}</p>"
        head = f"<h1>{lab['title']}</h1>" + head
    foot = f"<div class=foot>{seller.replace('<br>', ' · ')}</div>" if layout == "letter" else ""
    pay = f"<p>{lab['pay']} {e(t['iban'])}</p>" if t["iban"] else ""
    return f"""<!doctype html><html><head><meta charset=utf-8><style>{CSS}</style></head>
<body class={layout}><div class=page>{head}{buyer_block}
<table><tr><th>{lab["desc"]}</th><th class=n>{lab["qty"]}</th><th class=n>{lab["price"]}</th>
<th class=n>{lab["vat"]}</th><th class=n>{lab["amount"]}</th></tr>{rows}</table>
<table class=tot><tr><td>{lab["subtotal"]}</td><td class=n>{sign} {m(t["untaxed"])}</td></tr>{vat_rows}
<tr><td><b>{lab["total"]}</b></td><td class=n><b>{sign} {m(t["total"])}</b></td></tr></table>
<div class=notice>{e(notice)}</div>{pay}{foot}</div></body></html>"""


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("out", type=Path)
    ap.add_argument("--count", type=int, default=150)
    ap.add_argument("--seed", type=int, default=2026)
    default_chrome = shutil.which("google-chrome") or "/opt/pw-browsers/chromium"
    ap.add_argument("--chrome", default=default_chrome)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    rng = random.Random(args.seed)
    names = list(SCENARIOS)
    truths = []
    for n in range(args.count):
        truth, page = make_bill(n, names[n % len(names)], rng)
        src = args.out / f"{truth['id']}.html"
        src.write_text(page)
        pdf = args.out / truth["file"]
        cmd = [args.chrome, "--headless", "--no-sandbox", "--disable-gpu", "--no-pdf-header-footer"]
        subprocess.run([*cmd, f"--print-to-pdf={pdf}", src.resolve().as_uri()], check=True,
                       capture_output=True, timeout=60)  # fmt: skip
        truths.append(truth)
    with (args.out / "truth.jsonl").open("w") as f:
        f.writelines(json.dumps(t, ensure_ascii=False) + "\n" for t in truths)
    print(f"{len(truths)} bills in {args.out}")


if __name__ == "__main__":
    main()
