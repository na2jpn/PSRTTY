"""Shared numeric references; all display prose lives in language/*.json.

Ranges are operating examples or selected plan segments, never dial limits.
Source selection and exclusions: docs/RTTY_FREQUENCY_GUIDE_SOURCES.md.
"""
from html import escape
from .i18n import tr

REGIONS = ('japan', 'r1', 'r2', 'r3')
BANDS = ('1.8/1.9', '3.5', '7', '10', '14', '18', '21', '24', '28', '50', '144', '430')
CHECKED = '2026-10-09'
# band, frequency reference, category, localized note IDs
ROWS = {
    'japan': (
        ('1.8/1.9', '1.830–1.845 / 1.9075–1.9125', 'plan', ('no_centre', 'japan160')),
        ('3.5', '3.599–3.612', 'practice', ('shared',)),
        ('7', '7.035–7.080', 'practice', ('japan7lower', 'japan7')),
        ('10', '10.120–10.150', 'plan', ('warc', 'avoid', 'no_centre')),
        ('14', '14.080–14.120', 'practice', ('beacons', 'avoid')),
        ('18', '18.080–18.110', 'plan', ('warc', 'beacons', 'avoid', 'no_centre')),
        ('21', '21.080–21.120', 'practice', ('shared',)),
        ('24', '24.900–24.930', 'plan', ('warc', 'beacons', 'avoid', 'no_centre')),
        ('28', '28.080–28.120', 'practice', ('shared',)),
        ('50', '50.070–51.000', 'plan', ('no_centre', 'vhf')),
        ('144', '144.100–144.500', 'plan', ('no_centre', 'vhf')),
        ('430', '430.100–430.700', 'plan', ('no_centre', 'uhf')),
        ('1200', '1293.000–1294.000', 'plan', ('japan1200', 'no_centre')),
    ),
    'r1': (
        ('1.8/1.9', '1.838–1.840 / 1.840–1.843', 'plan', ('r1_160',)),
        ('3.5', '3.580–3.600', 'practice', ('r1_80', 'shared')),
        ('7', '7.040–7.060', 'practice', ('r1_40', 'japan7')),
        ('10', '10.130–10.150', 'plan', ('warc', 'avoid')),
        ('14', '14.080–14.099', 'practice', ('r1_beacon', 'shared')),
        ('18', '18.095–18.109', 'plan', ('warc', 'r1_beacon', 'avoid')),
        ('21', '21.080–21.120', 'practice', ('shared',)),
        ('24', '24.915–24.929', 'plan', ('warc', 'r1_beacon', 'avoid')),
        ('28', '28.080–28.120', 'practice', ('shared',)),
        ('50', '50.300–50.400', 'plan', ('no_centre', 'vhf')),
        ('144', '144.600', 'centre', ('shared', 'uhf')),
        ('430', '—', 'local', ('no_centre', 'uhf')),
    ),
    'r2': (
        ('1.8/1.9', '1.800–1.810', 'plan', ('no_centre', 'avoid')),
        ('3.5', '3.570–3.600', 'plan', ('avoid', 'shared')),
        ('7', '7.040 / 7.080–7.125', 'plan', ('shared', 'japan7')),
        ('10', '10.130–10.140', 'plan', ('warc', 'avoid')),
        ('14', '14.070–14.095', 'plan', ('avoid', 'shared')),
        ('18', '18.100–18.105', 'plan', ('warc', 'avoid')),
        ('21', '21.070–21.110', 'plan', ('avoid', 'shared')),
        ('24', '24.920–24.925', 'plan', ('warc', 'shared')),
        ('28', '28.070–28.150', 'plan', ('avoid', 'shared')),
        ('50', '50.600–50.800', 'plan', ('no_centre', 'shared')),
        ('144', '145.500–145.800', 'plan', ('no_centre', 'uhf')),
        ('430', '432.100–432.300 / 432.400–433.000', 'plan', ('no_centre', 'uhf')),
    ),
    'r3': (
        ('1.8/1.9', '1.830–1.840', 'plan', ('no_centre', 'avoid')),
        ('3.5', '3.535–3.600', 'plan', ('no_centre', 'avoid', 'shared')),
        ('7', '7.040', 'centre', ('r3_40', 'japan7')),
        ('10', '10.130–10.150', 'plan', ('warc', 'avoid')),
        ('14', '14.070–14.110', 'plan', ('r3_beacon', 'beacons', 'avoid')),
        ('18', '18.095–18.110', 'plan', ('warc', 'r3_beacon', 'beacons', 'avoid')),
        ('21', '21.070–21.125', 'plan', ('avoid', 'shared')),
        ('24', '24.915–24.930', 'plan', ('warc', 'r3_beacon', 'beacons', 'avoid')),
        ('28', '28.070–28.150', 'plan', ('avoid', 'shared')),
        ('50', '50.100–50.500', 'plan', ('no_centre', 'vhf')),
        ('144', '—', 'local', ('no_centre', 'vhf', 'uhf')),
        ('430', '—', 'local', ('no_centre', 'uhf')),
    ),
}

SOURCES = {
    'jarl_plan': ('JARL — 2025-07-17', 'https://www.jarl.org/Japanese/A_Shiryo/A-3_Band_Plan/bandplan20250717.pdf'),
    'jarl_rtty': ('JARL — RTTY', 'https://www.jarl.org/Japanese/1_Tanoshimo/1-1_Contest/RTTY_nyumon.html'),
    'jarl_digital': ('JARL — FT8 / JT65', 'https://www.jarl.org/Japanese/1_Tanoshimo/1-1_Contest/frequency.html'),
    'japan_ft8': ('JA1ZLO — FT8 7.041 MHz', 'https://ja1zlo.u-tokyo.org/allja1/37rule/'),
    'r1_hf': ('IARU R1 — HF', 'https://www.iaru-r1.org/reference/band-plans/hf-bandplan/'),
    'r1_vhf': ('IARU R1 — VHF Handbook 10.03', 'https://www.iaru-r1.org/wp-content/uploads/2026/02/VHF_Handbook_V10_03_final.pdf'),
    'rsgb': ('RSGB — 2026', 'https://rsgb.services/public/bandplans/docs/260125_rsgb_band_plan_2026.pdf'),
    'n1mm': ('N1MM — RTTY', 'https://n1mmwp.hamdocs.com/manual-operating/digital-modes/'),
    'r2': ('IARU R2', 'https://www.iaru-r2.org/en/reference/band-plans/'),
    'arrl': ('ARRL — USA', 'https://www.arrl.org/band-plan'),
    'r3': ('IARU R3 — R3-004 Rev.2 (2024-11)', 'https://www.iaru-r3.org/wp-content/uploads/2025/01/R3-004-Band-Plans-IARU-Region-3.pdf'),
    'r3_proposal': ('IARU R3 — 2026-04-04', 'https://www.iaru-r3.org/2026/proposal-from-r3-hf-band-plan-committee/'),
}
REGION_SOURCES = {
    'japan': ('jarl_plan', 'jarl_rtty', 'jarl_digital', 'japan_ft8'),
    'r1': ('r1_hf', 'rsgb', 'r1_vhf', 'n1mm', 'japan_ft8'),
    'r2': ('r2', 'arrl', 'japan_ft8'),
    'r3': ('r3', 'r3_proposal', 'japan_ft8'),
}
# Examples of USB dial settings, not entire occupied bands or an exhaustive list.
FT8_DIALS = (
    ('1.8/1.9', '1.840'), ('3.5', '3.573'), ('7', '7.041 / 7.074'),
    ('10', '10.136'), ('14', '14.074'), ('18', '18.100'),
    ('21', '21.074'), ('24', '24.915'), ('28', '28.074'), ('50', '50.313'),
)

def text(key):
    return escape(tr('freq.' + key))

def paragraph(key):
    return '<p>' + text(key) + '</p>'

def sources_html(ids):
    links = ''.join('<li><a href="' + escape(SOURCES[k][1], quote=True) + '">' + escape(SOURCES[k][0]) + '</a></li>' for k in ids)
    return '<h3>' + text('sources') + '</h3>' + paragraph('checked') + '<ul>' + links + '</ul>'

def page_html(region=None):
    html = '<h2>' + text('year') + '</h2>'
    if region is None:
        html += ''.join(paragraph(k) for k in ('scope', 'meaning', 'rules', 'contest', 'sideband', 'bounds', 'ft8'))
        html += '<table><tr><th>' + text('band') + '</th><th>FT8 — USB / MHz</th></tr>'
        html += ''.join('<tr><td>' + escape(b) + ' MHz</td><td>' + escape(f) + '</td></tr>' for b, f in FT8_DIALS) + '</table>'
        html += paragraph('japan7') + paragraph('beacons')
        return html + sources_html(('r3', 'jarl_digital', 'japan_ft8', 'jarl_rtty', 'rsgb'))
    html += '<h3>' + text(region) + '</h3>' + paragraph(region + '_intro') + paragraph('meaning')
    html += '<table><tr>' + ''.join('<th>' + text(k) + '</th>' for k in ('band', 'frequency', 'kind', 'notes')) + '</tr>'
    for band, frequency, kind, notes in ROWS[region]:
        html += '<tr><td>' + escape(band) + ' MHz</td><td>' + escape(frequency) + '</td><td>' + text(kind) + '</td><td>' + '<br>'.join(text(n) for n in notes) + '</td></tr>'
    html += '</table>'
    html += ''.join(paragraph(k) for k in ('japan7', 'sideband', 'ft8', 'beacons', 'bounds', 'contest', 'rules'))
    return html + sources_html(REGION_SOURCES[region])
