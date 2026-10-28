import io
import re
import zipfile
import pandas as pd
import streamlit as st

st.set_page_config(page_title='PxQ | Commissioni comparatori', page_icon='📊', layout='wide', initial_sidebar_state='expanded')
st.markdown('''
<style>
:root{--brand:#3345d9;--brand2:#7968ee;--ink:#172033;--muted:#667085;--line:#e5e8f0;--canvas:#f6f7fb}
.stApp{background:var(--canvas);color:var(--ink)}
.block-container{max-width:1440px;padding-top:1.5rem;padding-bottom:3rem}
[data-testid="stSidebar"]{background:#fff;border-right:1px solid var(--line)}
.hero{padding:1.45rem 1.7rem;border-radius:20px;color:#fff;margin-bottom:1.25rem;background:linear-gradient(120deg,#2638d7 0%,#5f55e9 58%,#8b75f4 100%);box-shadow:0 12px 32px rgba(37,54,216,.18)}
.hero h1{margin:0;font-size:2rem;letter-spacing:-.04em;color:#fff}.hero p{margin:.4rem 0 0;opacity:.9}
.section-kicker{color:var(--brand);font-size:.78rem;font-weight:800;letter-spacing:.09em;text-transform:uppercase;margin:.2rem 0 .7rem}
[data-testid="stMetric"]{background:#fff;border:1px solid var(--line);border-radius:16px;padding:1rem 1.1rem;box-shadow:0 4px 18px rgba(23,32,51,.05);min-height:104px}
[data-testid="stMetricLabel"]{color:var(--muted);font-weight:650}[data-testid="stMetricValue"]{color:var(--ink);font-weight:780;letter-spacing:-.03em}
div[data-testid="stVerticalBlockBorderWrapper"]{background:#fff;border:1px solid var(--line);border-radius:17px;box-shadow:0 5px 18px rgba(23,32,51,.045)}
.stButton>button,.stDownloadButton>button{border-radius:10px;min-height:2.55rem;font-weight:680;border:1px solid #d6dbe7}.stDownloadButton>button{width:100%;background:#fff}
.stButton>button:hover,.stDownloadButton>button:hover{border-color:var(--brand);color:var(--brand)}
[data-testid="stProgress"]>div>div>div{background:linear-gradient(90deg,var(--brand),var(--brand2))}
[data-testid="stDataFrame"]{background:#fff;border:1px solid var(--line);border-radius:14px;overflow:hidden}
div[data-testid="stExpander"]{background:#fff;border:1px solid var(--line);border-radius:14px}
h1,h2,h3{color:var(--ink);letter-spacing:-.025em}hr{border-color:var(--line)}
@media(max-width:900px){.block-container{padding-left:1rem;padding-right:1rem}.hero h1{font-size:1.55rem}}

.app-footer-spacer{height:0}
.app-footer{margin-top:clamp(3rem, 18vh, 12rem);padding:1.15rem 1.35rem;border-top:1px solid var(--line);display:flex;align-items:center;justify-content:center;gap:.6rem;color:var(--muted);font-size:.88rem;background:rgba(255,255,255,.72);border-radius:14px}
.app-footer-empty{margin-top:clamp(8rem, 35vh, 24rem)}
.app-footer strong{color:var(--ink);font-weight:700}
.app-footer img{height:34px;width:auto;display:block;object-fit:contain}

.light-metric{background:#fff;border:1px solid var(--line);border-radius:14px;padding:.82rem 1rem;min-height:92px;box-shadow:0 3px 12px rgba(23,32,51,.035)}
.light-metric-label{color:var(--muted);font-size:.86rem;font-weight:500;margin-bottom:.38rem}
.light-metric-value{color:#344054;font-size:1.38rem;font-weight:400;letter-spacing:-.02em;line-height:1.15}

/* Uploader compatto: l'intera dropzone resta cliccabile e accetta drag & drop. */
[data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] {
  position:relative!important;
  min-height:64px!important;
  padding:0!important;
  border:2px dashed #b9c0d3!important;
  border-radius:12px!important;
  background:#fbfcff!important;
  cursor:pointer!important;
  overflow:hidden!important;
}
[data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"]:hover {
  border-color:var(--brand)!important;
  background:#f4f5ff!important;
}
[data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"]::after {
  content:"Trascina o premi";
  position:absolute;
  inset:0;
  display:flex;
  align-items:center;
  justify-content:center;
  color:var(--ink);
  font-size:.9rem;
  font-weight:650;
  pointer-events:none;
}
[data-testid="stSidebar"] [data-testid="stFileUploaderDropzoneInstructions"],
[data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] button,
[data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] svg {
  opacity:0!important;
}
[data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] button {
  position:absolute!important;
  inset:0!important;
  width:100%!important;
  height:100%!important;
  z-index:2!important;
  cursor:pointer!important;
}

.quarter-track{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:.55rem;margin:.9rem 0 .45rem}
.quarter-segment{height:12px;border-radius:999px;background:#e5e7eb;border:1px solid #d0d5dd;position:relative}
.quarter-segment.is-ok{background:#22a06b;border-color:#168a59}
.quarter-segment.is-ko{background:#d92d20;border-color:#b42318}
.quarter-segment.is-pending{background:#e5e7eb;border-color:#d0d5dd}
.quarter-labels{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:.55rem;margin-bottom:.8rem}
.quarter-label{text-align:center;font-size:.76rem;color:var(--muted);line-height:1.25}
.quarter-label strong{display:block;color:var(--ink);font-size:.78rem}
.quarter-legend{display:flex;gap:1rem;flex-wrap:wrap;margin:.2rem 0 .4rem;font-size:.76rem;color:var(--muted)}
.quarter-dot{display:inline-block;width:.58rem;height:.58rem;border-radius:50%;margin-right:.3rem;vertical-align:-.02rem}
.quarter-dot.ok{background:#22a06b}.quarter-dot.ko{background:#d92d20}.quarter-dot.pending{background:#e5e7eb;border:1px solid #cfd4dc}

/* Evidenzia l'ultima colonna Totali nelle tabelle dell'Overview. */
[data-testid="stDataFrame"] [role="columnheader"]:last-child,
[data-testid="stDataFrame"] [role="gridcell"]:last-child {
  font-weight:700!important;
}
.annual-status{margin:.85rem 0 .35rem}
.annual-status-title{font-size:.78rem;color:var(--muted);margin-bottom:.3rem;font-weight:650}
.annual-status-bar{height:12px;border-radius:999px;border:1px solid #d0d5dd}
.annual-status-bar.is-ok{background:#22a06b;border-color:#168a59}
.annual-status-bar.is-ko{background:#d92d20;border-color:#b42318}
.annual-status-label{margin-top:.3rem;font-size:.78rem;font-weight:700}
.annual-status-label.is-ok{color:#168a59}.annual-status-label.is-ko{color:#b42318}
</style>
<div class="hero"><h1>PxQ | Commissioni comparatori</h1><p>Calcolo, controllo e reportistica delle commissioni partner</p></div>
''',unsafe_allow_html=True)

DEFAULT_COMPETENCE = pd.Timestamp('2026-09-01')

FOOTER_LOGO_DATA = "data:image/png;base64,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"


def render_footer(empty_state=False):
    footer_class = "app-footer app-footer-empty" if empty_state else "app-footer"
    st.markdown(
        f"""
        <div class="app-footer-spacer"></div>
        <div class="{footer_class}">
            <span>Author: <strong>Stefano Lovecchio</strong> x</span>
            <img src="{FOOTER_LOGO_DATA}" alt="NeN Gruppo a2a" />
        </div>
        """,
        unsafe_allow_html=True,
    )


def norm(v):
    if pd.isna(v):
        return ''
    return re.sub(r'[^a-z0-9]+', '', str(v).strip().lower())


def month(v):
    if pd.isna(v):
        return pd.NaT
    return pd.Timestamp(v).to_period('M').to_timestamp()


def parse_dates(s):
    return pd.to_datetime(s, dayfirst=True, errors='coerce')


def split_ids(v):
    if pd.isna(v):
        return []
    return [x.strip() for x in str(v).split(',') if x.strip()]


def parse_decorrenza(v):
    if pd.isna(v):
        return pd.NaT
    if str(v).strip().lower() == 'no':
        return pd.NaT
    return month(pd.to_datetime(v, dayfirst=True, errors='coerce'))


def contains_promo(value, identifiers):
    n = norm(value)
    return any(norm(token) and norm(token) in n for token in identifiers)


def matches_subchannel(value, identifiers):
    n = norm(value)
    return any(norm(token) == n for token in identifiers)


def configuration_candidates(row, configs):
    sub_n = norm(row.get('Subchannel'))
    promo_n = norm(row.get('Promo code'))

    # Eccezione nota: bug Promo code, prevale Facile-B2C.
    if sub_n == norm('Facile-B2C') and promo_n == norm('Switcho!NeN'):
        return configs[configs['Sub IDs'].apply(lambda ids: matches_subchannel('Facile-B2C', ids))].copy(), 'ECCEZIONE_FACILE_PROMO_ERRATO'

    # Eccezione nota: Billoo!NeN non attribuisce Billoo con Web o NeN-B2C.
    if sub_n in {norm('Web'), norm('NeN-B2C')} and promo_n == norm('Billoo!NeN'):
        return configs.iloc[0:0].copy(), 'NON_MAPPATO_BILLOO_PROMO_NON_SUFFICIENTE'

    sub_hits = configs[configs['Sub IDs'].apply(lambda ids: matches_subchannel(row.get('Subchannel'), ids))]
    promo_hits = configs[configs['Promo IDs'].apply(lambda ids: contains_promo(row.get('Promo code'), ids))]

    # ESCLUDI SELF/GD deve essere applicato ai candidati prima di valutare i conflitti.
    # In questo modo un agente non ammissibile per il Subchannel corrente non genera
    # un falso conflitto con un altro agente valido.
    sub_hits = sub_hits[sub_hits.apply(
        lambda cfg: exclusion_reason(row.get('Subchannel'), cfg.get('ESCLUDI SELF'), cfg.get('ESCLUDI GD')) is None,
        axis=1,
    )]
    promo_hits = promo_hits[promo_hits.apply(
        lambda cfg: exclusion_reason(row.get('Subchannel'), cfg.get('ESCLUDI SELF'), cfg.get('ESCLUDI GD')) is None,
        axis=1,
    )]

    # Se entrambi i criteri trovano configurazioni commerciali diverse, blocca il record.
    if not sub_hits.empty and not promo_hits.empty:
        sub_gruppi = set(sub_hits['Gruppo mapping'])
        promo_gruppi = set(promo_hits['Gruppo mapping'])
        if sub_gruppi.isdisjoint(promo_gruppi):
            return configs.iloc[0:0].copy(), 'CONFLITTO_SUBCHANNEL_PROMO'
        hits = pd.concat([sub_hits, promo_hits]).drop_duplicates(subset=['Agente', 'Decorrenza'])
        return hits, 'SUBCHANNEL+PROMO'
    if not sub_hits.empty:
        return sub_hits.copy(), 'SUBCHANNEL'
    if not promo_hits.empty:
        return promo_hits.copy(), 'PROMO'
    return configs.iloc[0:0].copy(), 'NON_MAPPATO'


def select_configuration(row, configs):
    # Restituisce: Partner, Esito, Decorrenza, Gettone RES/IVA, Ricorrente RES/IVA, Partner storico.
    # Partner = agente con modello attivo alla sottoscrizione (usato per le commissioni).
    # Partner storico = agente a prescindere dalla decorrenza del modello (usato per il Cohort Churn).
    candidates, outcome = configuration_candidates(row, configs)
    signed_month = row['Mese sottoscrizione']
    if candidates.empty:
        return pd.Series([None, outcome, pd.NaT, None, None, None, None, None])

    sub = row.get('Subchannel')
    effective, reasons = [], []
    for agent, grp in candidates.groupby('Agente', sort=False):
        dated = grp[grp['Decorrenza'].notna()].sort_values('Decorrenza')
        if pd.notna(signed_month):
            in_force = dated[dated['Decorrenza'] <= signed_month]
        else:
            in_force = dated.iloc[0:0]
        if not in_force.empty:
            cfg, attivo = in_force.iloc[-1], True
        elif not dated.empty:
            cfg, attivo = dated.iloc[0], False
        else:
            cfg, attivo = grp.iloc[0], False
        # ESCLUDI SELF / ESCLUDI GD valgono per la configurazione dell'agente in vigore
        # e prevalgono anche sul match da Promo code.
        why = exclusion_reason(sub, cfg.get('ESCLUDI SELF'), cfg.get('ESCLUDI GD'))
        if why:
            reasons.append(why)
        else:
            effective.append((agent, cfg, attivo))

    if not effective:
        return pd.Series([None, reasons[0], pd.NaT, None, None, None, None, None])

    agents = {agent for agent, _, _ in effective}
    historic_partner = next(iter(agents)) if len(agents) == 1 else None
    in_force_rows = [cfg for _, cfg, attivo in effective if attivo]
    if not in_force_rows:
        # Il mapping può essere noto, ma il modello non ancora attivo.
        return pd.Series([None, outcome + '_MODELLO_NON_ATTIVO', pd.NaT, None, None, None, None, historic_partner])
    if len(in_force_rows) > 1:
        # Più agenti con modello attivo per lo stesso contratto: non si sceglie in silenzio.
        return pd.Series([None, 'CONFLITTO_PARTNER', pd.NaT, None, None, None, None, None])
    chosen = in_force_rows[0]
    return pd.Series([
        chosen['Agente'], outcome, chosen['Decorrenza'], chosen['GETTONE RES'],
        chosen['GETTONE IVA'], chosen['RICORRENTE RES'], chosen['RICORRENTE IVA'], historic_partner
    ])


# Stati che danno diritto al gettone (Base e Avanzato): tutti tranne ANNULLATO e SOSPESO.
# Nel report INSERITO equivale a IN ATTESA e viene normalizzato da clean_status().
GETTONE_STATI_VALIDI = ['ATTIVO', 'IN ATTESA', 'IN ATTIVAZIONE', 'CHIUSO']
STATI_NOTI = {'ATTIVO', 'ANNULLATO', 'CHIUSO', 'IN ATTIVAZIONE', 'IN ATTESA', 'SOSPESO'}

# Malus per chiusura. La vita della fornitura conta solo per mese di calendario, il giorno è
# ignorato: attivazione 1 luglio e chiusura 31 luglio = 1 mese; 15 gennaio -> 20 agosto = 8 mesi.
# Fino a 4 mesi di vita = malus 100%; 5 e 6 mesi = 50%; oltre il sesto mese nessun malus.
# Una chiusura senza attivazione è trattata come churn a 3 mesi (malus 100%).
MALUS_100_FINO_A_MESI = 4
MALUS_50_FINO_A_MESI = 6

# Esclusioni per agente (colonne ESCLUDI SELF / ESCLUDI GD del file identificatori).
SUBCHANNEL_SELF = {'', 'web'}
SUBCHANNEL_GD = {'nenb2c', 'nenb2b'}

# Bonus Churn: classi sul tasso di partenza, in decimi di punto percentuale (189 = 18,9%).
BONUS_CLASSI = ['PLATINUM', 'GOLD', 'SILVER', 'BRONZE', 'BEGINNER']
BONUS_LIMITI_CLASSI = [189, 229, 269, 300]
# Micro-classi BEGINNER: (limite massimo, etichetta, miglioramento trimestrale, miglioramento annuo),
# in decimi di punto percentuale.
BONUS_MICRO_CLASSI = [
    (339, '30,1%-33,9%', 7, 21),
    (379, '34,0%-37,9%', 8, 24),
    (419, '38,0%-41,9%', 10, 30),
    (459, '42,0%-45,9%', 12, 36),
    (499, '46,0%-49,9%', 17, 51),
    (10 ** 6, '>=50,0%', 25, 75),
]


def clean_status(series):
    return series.astype(str).str.strip().str.upper().replace({'INSERITO': 'IN ATTESA'})


def is_yes(v):
    return str(v).strip().upper() in {'SI', 'SÌ', 'S', 'YES', 'TRUE', '1', '1.0'}


def exclusion_reason(subchannel, esclude_self, esclude_gd):
    n = norm(subchannel)
    if is_yes(esclude_self) and n in SUBCHANNEL_SELF:
        return 'ESCLUSO_SELF'
    if is_yes(esclude_gd) and n in SUBCHANNEL_GD:
        return 'ESCLUSO_GD'
    return None


def months_lived(start, end):
    # Mesi di vita contando solo il mese di calendario (estremi inclusi): luglio -> luglio = 1.
    # Chiusura nel mese dell'attivazione = 1; chiusura in un mese precedente = 0 o negativo.
    if pd.isna(start) or pd.isna(end):
        return pd.NA
    start = pd.Timestamp(start)
    end = pd.Timestamp(end)
    return (end.year - start.year) * 12 + end.month - start.month + 1


def malus_fascia(months):
    # Mesi mancanti (chiusura senza attivazione) = churn a 3 mesi = malus 100%.
    if pd.isna(months) or months <= MALUS_100_FINO_A_MESI:
        return '100%', 1.0
    if months <= MALUS_50_FINO_A_MESI:
        return '50%', 0.5
    return '0%', 0.0


def churn_tenths(switch_out, activated):
    # Cohort Churn in decimi di punto percentuale, TRONCATO (non arrotondato), con aritmetica
    # intera per evitare errori di virgola mobile: 189 = 18,9%.
    if pd.isna(activated) or int(activated) <= 0:
        return None
    return int(switch_out) * 1000 // int(activated)


def churn_class(t):
    for name, limit in zip(BONUS_CLASSI, BONUS_LIMITI_CLASSI):
        if t <= limit:
            return name
    return 'BEGINNER'


def micro_class(t):
    for limit, label, d_q, d_a in BONUS_MICRO_CLASSI:
        if t <= limit:
            return label, d_q, d_a
    return BONUS_MICRO_CLASSI[-1][1:]


def consecutive_run(months):
    # Numero di mesi consecutivi che terminano con l'ultima rilevazione.
    months = sorted({pd.Timestamp(m) for m in months if pd.notna(m)})
    if not months:
        return 0
    run = 1
    for i in range(len(months) - 1, 0, -1):
        if months[i - 1] == months[i] - pd.DateOffset(months=1):
            run += 1
        else:
            break
    return run


def pooled_obs(hist, months):
    months = [month(m) for m in months]
    sel = hist[hist['Mese rilevazione'].isin(months)].copy()
    return int(sel['Switch OUT'].sum()), int(sel['POD/PDR attivati'].sum()), len(sel)


def latest_six_before(hist, cutoff):
    """Ultime 6 rilevazioni mensili disponibili prima del periodo analizzato."""
    eligible = hist[hist['Mese rilevazione'] < month(cutoff)].sort_values('Mese rilevazione')
    if len(eligible) < 6:
        return None, eligible.tail(6)
    six = eligible.tail(6).copy()
    if six['POD/PDR attivati'].sum() <= 0:
        return None, six
    return (int(six['Switch OUT'].sum()), int(six['POD/PDR attivati'].sum())), six


def program_months(start, offset, count):
    start = month(start)
    return [start + pd.DateOffset(months=offset + i) for i in range(count)]


def safe_float(value, default=0.0):
    # pd.NA e NaN non possono essere valutati con `value or 0`.
    if value is None or pd.isna(value):
        return float(default)
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def safe_int(value, default=0):
    return int(round(safe_float(value, default)))


def render_light_metric(target, label, value):
    target.markdown(
        f"""
        <div class="light-metric">
            <div class="light-metric-label">{label}</div>
            <div class="light-metric-value">{value}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def format_euro(value):
    value = safe_float(value, 0.0)
    formatted = f"{value:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
    return f"€ {formatted}"


def format_month_year(value):
    return '' if pd.isna(value) else pd.Timestamp(value).strftime('%m/%Y')


def evaluate_partner_bonus(partner, hist, start, available_end):
    """Valuta un unico ciclo annuale di 12 mesi dalla decorrenza Bonus Churn.

    La baseline usa le 6 rilevazioni più recenti precedenti alla decorrenza.
    I trimestri sono relativi alla decorrenza del partner, non ai trimestri solari.
    L'annuale viene calcolato soltanto quando sono disponibili tutti i 12 mesi.
    """
    start = month(start)
    available_end = month(available_end)
    hist = hist.sort_values('Mese rilevazione').copy()
    program_end = start + pd.DateOffset(months=11)
    if pd.isna(start):
        return None, [], None, {
            'Partner': partner, 'Stato': 'DECORRENZA MANCANTE', 'Mesi consolidati': 0,
            'Progressione': 0.0,
            'Messaggio': 'Decorrenza Bonus Churn non valorizzata.'
        }
    if available_end < start:
        months_available = []
    else:
        months_available = program_months(start, 0, min(12, ((available_end.year-start.year)*12 + available_end.month-start.month + 1)))
    present_program = hist[hist['Mese rilevazione'].isin(months_available)]['Mese rilevazione'].nunique()
    progress = min(present_program, 12) / 12

    snap, baseline_rows = latest_six_before(hist, start)
    if snap is None:
        return None, [], None, {
            'Partner': partner,
            'Stato': 'STORICO INSUFFICIENTE',
            'Mesi consolidati': present_program,
            'Progressione': progress,
            'Messaggio': (
                f'{partner}: servono almeno 6 rilevazioni mensili di Cohort Churn a 12 mesi '
                f'precedenti alla decorrenza {start:%m/%Y}; disponibili {len(baseline_rows)}/6. '
                'Nessuna classe o idoneità viene calcolata.'
            )
        }

    so_base, act_base = snap
    t_base = churn_tenths(so_base, act_base)
    base_class = churn_class(t_base)
    micro_label = d_q = d_a = None
    if base_class == 'BEGINNER':
        micro_label, d_q, d_a = micro_class(t_base)

    baseline = {
        'Partner': partner,
        'Decorrenza': format_month_year(start),
        'Periodo baseline': (
            f"{baseline_rows['Mese rilevazione'].min():%m/%Y}-"
            f"{baseline_rows['Mese rilevazione'].max():%m/%Y}"
        ),
        'Rilevazioni utilizzate': len(baseline_rows),
        'Switch OUT': so_base,
        'POD/PDR attivati': act_base,
        'Cohort Churn di partenza (%)': t_base / 10,
        'Classe di partenza': base_class,
        'Micro-classe BEGINNER': micro_label,
        'Obiettivo trimestrale standard (p.p.)': None if d_q is None else d_q / 10,
        'Obiettivo annuale (p.p.)': None if d_a is None else d_a / 10,
    }

    quarters = []
    missed = 0
    for q in range(1, 5):
        q_months = program_months(start, (q - 1) * 3, 3)
        so_q, act_q, n_q = pooled_obs(hist, q_months)
        if n_q < 3 or act_q <= 0:
            continue
        t_q = churn_tenths(so_q, act_q)
        cumulative_steps = 1 + missed if base_class == 'BEGINNER' else 0
        target = t_base - d_q * cumulative_steps if base_class == 'BEGINNER' else t_base
        if t_q <= target:
            esito = 'IDONEO'
            missed = 0
        else:
            esito = 'NON IDONEO'
            if base_class == 'BEGINNER':
                missed += 1
        quarters.append({
            'Partner': partner,
            'Trimestre': f'Q{q}',
            'Periodo': f'{q_months[0]:%m/%Y}-{q_months[-1]:%m/%Y}',
            'Stato': 'COMPLETATO',
            'Switch OUT': so_q,
            'POD/PDR attivati': act_q,
            'Churn iniziale (%)': t_base / 10,
            'Churn rilevato (%)': t_q / 10,
            'Target trimestre (p.p.)': None if base_class != 'BEGINNER' else d_q * cumulative_steps / 10,
            'Soglia da rispettare (%)': target / 10,
            'Classe di partenza': base_class,
            'Micro-classe di partenza': micro_label,
            'Idoneità': esito,
        })

    annual = None
    annual_program_months = program_months(start, 0, 12)
    so_year, act_year, n_year = pooled_obs(hist, annual_program_months)
    if n_year == 12 and act_year > 0:
        if base_class != 'BEGINNER':
            t_year = churn_tenths(so_year, act_year)
            cls_year = churn_class(t_year)
            if cls_year == 'BEGINNER':
                eligibility = 'NON IDONEO - ATTERRAGGIO IN BEGINNER'
            else:
                gap = BONUS_CLASSI.index(cls_year) - BONUS_CLASSI.index(base_class)
                eligibility = (
                    'IDONEO - PREMIO APPARTENENZA ' + cls_year
                    if gap <= 1 else 'NON IDONEO - PEGGIORAMENTO OLTRE UNA CLASSE'
                )
            method = '12 mesi del programma ponderati'
            annual_target = None
        else:
            six = hist[hist['Mese rilevazione'].isin(annual_program_months[-6:])].sort_values('Mese rilevazione')
            so_year = int(six['Switch OUT'].sum())
            act_year = int(six['POD/PDR attivati'].sum())
            t_year = churn_tenths(so_year, act_year)
            cls_year = churn_class(t_year)
            annual_target = (t_base - d_a) / 10
            if cls_year != 'BEGINNER':
                eligibility = 'IDONEO - PREMIO APPARTENENZA ' + cls_year
            elif t_year <= t_base - d_a:
                eligibility = 'IDONEO - PREMIO MIGLIORAMENTO ANNUALE ' + micro_label
            else:
                eligibility = 'NON IDONEO - TARGET ANNUALE NON RAGGIUNTO'
            method = 'Ultime 6 rilevazioni del ciclo annuale'
        annual = {
            'Partner': partner,
            'Periodo': f'{annual_program_months[0]:%m/%Y}-{annual_program_months[-1]:%m/%Y}',
            'Stato': 'COMPLETATO',
            'Metodo': method,
            'Switch OUT': so_year,
            'POD/PDR attivati': act_year,
            'Churn iniziale (%)': t_base / 10,
            'Churn rilevato (%)': t_year / 10,
            'Target annuale (%)': annual_target,
            'Idoneità': eligibility,
            'Nuova classe': cls_year,
        }

    return baseline, quarters, annual, {
        'Partner': partner,
        'Stato': 'IN CORSO' if present_program < 12 else 'COMPLETATO',
        'Mesi consolidati': present_program,
        'Progressione': progress,
        'Fine ciclo': format_month_year(program_end),
        'Messaggio': ''
    }


def render_quarter_track(quarters):
    quarter_map = {quarter.get('Trimestre'): quarter for quarter in quarters}
    segments, labels = [], []
    for quarter_number in range(1, 5):
        quarter_name = f'Q{quarter_number}'
        quarter = quarter_map.get(quarter_name)
        if quarter is None:
            css_class = 'is-pending'
            status_label = 'In attesa'
        elif str(quarter.get('Idoneità', '')).upper() == 'IDONEO':
            css_class = 'is-ok'
            status_label = 'Idoneo'
        else:
            css_class = 'is-ko'
            status_label = 'Non idoneo'
        segments.append(
            f'<div class="quarter-segment {css_class}" title="{quarter_name}: {status_label}"></div>'
        )
        labels.append(
            f'<div class="quarter-label"><strong>{quarter_name}</strong>{status_label}</div>'
        )
    st.markdown(
        '<div class="quarter-track">' + ''.join(segments) + '</div>'
        + '<div class="quarter-labels">' + ''.join(labels) + '</div>'
        + '<div class="quarter-legend">'
        + '<span><i class="quarter-dot ok"></i>Idoneo</span>'
        + '<span><i class="quarter-dot ko"></i>Non idoneo</span>'
        + '<span><i class="quarter-dot pending"></i>In attesa</span>'
        + '</div>',
        unsafe_allow_html=True,
    )


def render_annual_status(annual):
    if annual is None:
        return
    eligibility = str(annual.get('Idoneità', '')).upper()
    is_eligible = eligibility.startswith('IDONEO')
    css_class = 'is-ok' if is_eligible else 'is-ko'
    status_label = 'Idoneo' if is_eligible else 'Non idoneo'
    st.markdown(
        '<div class="annual-status">'
        '<div class="annual-status-title">Idoneità annuale</div>'
        f'<div class="annual-status-bar {css_class}" title="Annuale: {status_label}"></div>'
        f'<div class="annual-status-label {css_class}">{status_label}</div>'
        '</div>',
        unsafe_allow_html=True,
    )


def join_reasons(flags):
    return pd.Series(
        ['; '.join(flags.columns[row]) for row in flags.to_numpy()],
        index=flags.index, dtype='object'
    )


@st.cache_data(show_spinner=False, max_entries=24)
def _read_excel_cached(file_bytes, sheet_name=0):
    # La cache è basata sul contenuto del file, non sul puntatore dell'UploadedFile.
    # Cambiare schermata non forza quindi una nuova lettura completa del workbook.
    return pd.read_excel(io.BytesIO(file_bytes), sheet_name=sheet_name, engine='openpyxl')


def read_excel(upload, sheet_name=0):
    if hasattr(upload, 'getvalue'):
        file_bytes = upload.getvalue()
    elif isinstance(upload, (bytes, bytearray)):
        file_bytes = bytes(upload)
    else:
        # Compatibilità con file locali/file-like.
        position = upload.tell() if hasattr(upload, 'tell') else None
        file_bytes = upload.read()
        if position is not None and hasattr(upload, 'seek'):
            upload.seek(position)
    return _read_excel_cached(file_bytes, sheet_name)


@st.cache_data(show_spinner=False, max_entries=96)
def to_excel(sheets, include_pod=False):
    out = io.BytesIO()
    with pd.ExcelWriter(out, engine='openpyxl') as writer:
        written_sheets = 0
        for name, frame in sheets.items():
            # Non creare tab vuote nei report destinati ai fornitori.
            # Una tab viene mantenuta solo se contiene almeno una riga dati.
            if frame is None or frame.empty:
                continue
            export_frame = frame.copy()
            pod_source_column = 'Point of delivery: Point of delivery Name'
            pod_normalized_column = 'Point of Delivery'
            if include_pod:
                # Nei report autorizzati mostra un solo campo POD con il nome Salesforce.
                if pod_source_column not in export_frame.columns and pod_normalized_column in export_frame.columns:
                    export_frame = export_frame.rename(
                        columns={pod_normalized_column: pod_source_column}
                    )
                elif pod_source_column in export_frame.columns and pod_normalized_column in export_frame.columns:
                    export_frame = export_frame.drop(columns=[pod_normalized_column])
            else:
                columns_to_remove = [
                    column for column in [pod_source_column, pod_normalized_column]
                    if column in export_frame.columns
                ]
                if columns_to_remove:
                    export_frame = export_frame.drop(columns=columns_to_remove)
            sheet_name = name[:31]
            export_frame.to_excel(writer, sheet_name=sheet_name, index=False)
            written_sheets += 1
            ws = writer.book[sheet_name]
            ws.freeze_panes = 'A2'
            ws.auto_filter.ref = ws.dimensions
            for col in ws.columns:
                vals = [str(c.value) if c.value is not None else '' for c in col[:2000]]
                width = min(max(max((len(v) for v in vals), default=8) + 2, 10), 45)
                ws.column_dimensions[col[0].column_letter].width = width
        # Protezione tecnica: openpyxl richiede almeno un foglio visibile.
        # Nei flussi attuali la Sintesi è sempre valorizzata, ma questo fallback
        # evita errori se in futuro venisse richiesto un export totalmente vuoto.
        if written_sheets == 0:
            pd.DataFrame({'Esito': ['Nessun dato disponibile']}).to_excel(
                writer, sheet_name='Nessun dato', index=False
            )
    out.seek(0)
    return out.getvalue()


@st.cache_data(show_spinner=False, max_entries=48)
def reports_to_zip(reports):
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for file_name, file_bytes in reports:
            archive.writestr(file_name, file_bytes)
    output.seek(0)
    return output.getvalue()


MONTH_OPTIONS = pd.period_range('2025-01', '2032-12', freq='M').astype(str).tolist()
YEAR_OPTIONS = list(range(2025, 2033))
with st.sidebar:
    module = st.radio(
        'Area di lavoro',
        ['Overview & Forecast', 'Commissioni Base', 'Commissioni Avanzato', 'Bonus Churn - rilevazioni e idoneità']
    )
    if module in ['Bonus Churn - rilevazioni e idoneità', 'Overview & Forecast']:
        # Queste viste determinano automaticamente il periodo dai dati caricati.
        competence = pd.Timestamp.today().to_period('M').to_timestamp()
    else:
        competence_label = st.selectbox(
            'Mese di competenza',
            MONTH_OPTIONS,
            index=MONTH_OPTIONS.index(DEFAULT_COMPETENCE.strftime('%Y-%m')),
        )
        competence = pd.Timestamp(f'{competence_label}-01')
    st.caption('Regole economiche e decorrenze sono lette dal file identificatori.')

st.markdown(f'<div class="section-kicker">{module}</div>',unsafe_allow_html=True)
with st.sidebar:
    st.divider()
    st.markdown('**File di lavoro**')
    contracts_file = st.file_uploader(
        'Report Salesforce', type='xlsx', help='Report generale dei contratti'
    )
    mapping_file = st.file_uploader(
        'Identificatori e condizioni', type='xlsx', help='Workbook con i fogli Base e Avanzato'
    )
    if contracts_file:
        st.success(f'Report caricato: {contracts_file.name}')
    if mapping_file:
        st.success(f'Identificatori caricati: {mapping_file.name}')

if contracts_file and mapping_file:
    # La prima elaborazione usa il file; i passaggi successivi tra schermate riusano la cache.
    contracts = read_excel(contracts_file)
    mapping_sheet = 'Base' if module == 'Commissioni Base' else 'Avanzato'
    try:
        mapping = read_excel(mapping_file, sheet_name=mapping_sheet)
    except ValueError:
        st.error(f'Il file identificatori non contiene il foglio richiesto: {mapping_sheet}.')
        render_footer()
        st.stop()

    required = {
        'Contract: Customer Signed Date', 'Status from PoD', 'Subscription Name',
        'Customer type', 'Subchannel', 'Promo code',
        'Prospected activation date', 'Point of delivery: Closing date',
        'Point of delivery: Point of delivery Name'
    }
    missing = required - set(contracts.columns)
    if missing:
        st.error('Colonne mancanti nel report: ' + ', '.join(sorted(missing)))
        render_footer()
        st.stop()
    if contracts.empty:
        st.error('Il report contratti è vuoto.')
        render_footer()
        st.stop()

    if module == 'Overview & Forecast':
        st.header('Overview & Forecast')
        st.caption(
            'I mesi presenti nel report restano sempre effettivi, incluso l’ultimo mese parziale. '
            'Sono stimati soltanto i mesi successivi all’ultima Customer Signed Date disponibile.'
        )
        quote_dates = parse_dates(contracts['Contract: Customer Signed Date'])
        available_years = sorted(quote_dates.dropna().dt.year.unique().astype(int).tolist())
        if not available_years:
            st.error('Nessun anno disponibile nel report.')
            render_footer()
            st.stop()
        selected_year = st.selectbox('Anno', available_years, index=len(available_years) - 1)
        download_slot = st.empty()
        year_months = [pd.Timestamp(selected_year, m, 1) for m in range(1, 13)]
        month_labels = ['Gen', 'Feb', 'Mar', 'Apr', 'Mag', 'Giu', 'Lug', 'Ago', 'Set', 'Ott', 'Nov', 'Dic']
        report_cutoff = quote_dates.max().to_period('M').to_timestamp()
        actual_months = {m for m in year_months if m <= report_cutoff}
        forecast_months = {m for m in year_months if m > report_cutoff}

        def get_cfg(sheet):
            mapping_file.seek(0)
            cfg = read_excel(mapping_file, sheet_name=sheet).copy()
            cfg.columns = [str(col).replace('\ufeff', '').strip() for col in cfg.columns]
            aliases = {norm(col): col for col in cfg.columns}
            required_names = [
                'Agente', 'IDENTIFICATORI SUBCHANNEL', 'IDENTIFICATORI PROMO CODE',
                'ESCLUDI SELF', 'ESCLUDI GD'
            ]
            missing_names = [name for name in required_names if norm(name) not in aliases]
            if missing_names:
                st.error(
                    f'Nel foglio {sheet} mancano colonne necessarie per Overview & Forecast: '
                    + ', '.join(missing_names)
                )
                render_footer()
                st.stop()
            cfg = cfg.rename(columns={aliases[norm(name)]: name for name in required_names})
            cfg['Sub IDs'] = cfg['IDENTIFICATORI SUBCHANNEL'].apply(split_ids)
            cfg['Promo IDs'] = cfg['IDENTIFICATORI PROMO CODE'].apply(split_ids)
            for col in cfg.columns:
                if str(col).startswith(('GETTONE', 'RICORRENTE', 'PREMIO', 'MESI CALCOLO', 'STORNO')):
                    cfg[col] = pd.to_numeric(cfg[col], errors='coerce')
            return cfg

        def map_agent(row, cfg):
            if cfg.empty or 'Agente' not in cfg.columns:
                return pd.NA
            sub_hits = cfg[cfg['Sub IDs'].apply(
                lambda ids: matches_subchannel(row.get('Subchannel'), ids)
            )]
            promo_hits = cfg[cfg['Promo IDs'].apply(
                lambda ids: contains_promo(row.get('Promo code'), ids)
            )]
            hits = cfg.loc[sub_hits.index.union(promo_hits.index)].copy()
            if hits.empty:
                return pd.NA
            hits = hits[hits.apply(
                lambda row_cfg: exclusion_reason(
                    row.get('Subchannel'), row_cfg.get('ESCLUDI SELF'), row_cfg.get('ESCLUDI GD')
                ) is None,
                axis=1,
            )]
            agents = hits['Agente'].dropna().astype(str).str.strip()
            agents = agents[agents.ne('')].unique()
            return agents[0] if len(agents) == 1 else pd.NA

        raw = contracts.copy()
        raw['Mese'] = quote_dates.map(month)
        raw['Attivazione'] = parse_dates(raw['Prospected activation date']).map(month)
        raw['Chiusura'] = parse_dates(raw['Point of delivery: Closing date']).map(month)
        raw['Stato'] = clean_status(raw['Status from PoD'])
        raw['Segmento forecast'] = raw['Customer type'].map({'Person': 'RES', 'Partita IVA': 'IVA'})
        raw['POD forecast'] = raw['Point of delivery: Point of delivery Name'].astype(str).str.strip()

        metric_rows = []
        agent_rates = {}
        mapped_datasets = []

        for model in ['Base', 'Avanzato']:
            cfg = get_cfg(model)
            if model == 'Avanzato':
                cfg['Decorrenza'] = cfg['DECORRENZA'].apply(parse_decorrenza)
                cfg['Gruppo mapping'] = cfg.apply(
                    lambda row: '|'.join(sorted([
                        norm(value) for value in row['Sub IDs'] + row['Promo IDs'] if norm(value)
                    ])), axis=1
                )
                data = raw.copy()
                data['Mese sottoscrizione forecast'] = data['Mese']
                combos = data[['Subchannel', 'Promo code', 'Mese sottoscrizione forecast']].drop_duplicates().reset_index(drop=True)
                mapping_input = combos.rename(columns={'Mese sottoscrizione forecast': 'Mese sottoscrizione'})
                selected = mapping_input.apply(lambda row: select_configuration(row, cfg), axis=1)
                selected.columns = [
                    'Agente', 'Esito overview', 'Decorrenza overview',
                    'Gettone RES overview', 'Gettone IVA overview',
                    'Ricorrente RES overview', 'Ricorrente IVA overview',
                    'Partner storico overview'
                ]
                combos = pd.concat([combos, selected], axis=1)
                data = data.merge(combos, on=['Subchannel','Promo code','Mese sottoscrizione forecast'], how='left')
                valid_cfg = cfg[cfg['Agente'].notna() & cfg['Agente'].astype(str).str.strip().ne('')]
                one = valid_cfg.sort_values('Decorrenza').drop_duplicates('Agente', keep='last').set_index('Agente')
            else:
                combos = raw[['Subchannel','Promo code']].drop_duplicates()
                combos['Agente'] = combos.apply(lambda row: map_agent(row, cfg), axis=1)
                data = raw.merge(combos, on=['Subchannel','Promo code'], how='left')
                valid_cfg = cfg[cfg['Agente'].notna() & cfg['Agente'].astype(str).str.strip().ne('')]
                one = valid_cfg.drop_duplicates('Agente').set_index('Agente')
            data['Modello forecast'] = model
            mapped_datasets.append(data)

            for agent in one.index:
                c = one.loc[agent]
                agent_rates[agent] = {
                    'RES': safe_int(c.get('GETTONE RES', 0)),
                    'IVA': safe_int(c.get('GETTONE IVA', 0)),
                    'Modello': model,
                }

            for current_month in year_months:
                # Non calcolare né simulare mesi successivi al contenuto del report.
                # Verranno valorizzati in seguito usando l'ultimo mese reale disponibile.
                if current_month > report_cutoff:
                    continue
                monthly = data[data['Mese'] == current_month].copy()
                if model == 'Avanzato':
                    monthly['Gettone overview'] = monthly.apply(
                        lambda row: row['Gettone RES overview'] if row['Customer type'] == 'Person'
                        else (row['Gettone IVA overview'] if row['Customer type'] == 'Partita IVA' else pd.NA), axis=1
                    )
                    monthly['Ricorrente overview'] = monthly.apply(
                        lambda row: row['Ricorrente RES overview'] if row['Customer type'] == 'Person'
                        else (row['Ricorrente IVA overview'] if row['Customer type'] == 'Partita IVA' else pd.NA), axis=1
                    )
                    valid = monthly[
                        monthly['Agente'].notna() & monthly['Gettone overview'].notna()
                        & monthly['Ricorrente overview'].notna()
                        & monthly['Stato'].isin(GETTONE_STATI_VALIDI)
                    ]
                else:
                    valid = monthly[monthly['Agente'].notna() & monthly['Stato'].isin(GETTONE_STATI_VALIDI)]
                for agent, group in valid.groupby('Agente'):
                    if agent not in one.index:
                        continue
                    c = one.loc[agent]
                    base_value = 0.0
                    for segment in ['RES', 'IVA']:
                        segment_group = group[group['Segmento forecast'] == segment]
                        if model == 'Avanzato':
                            count = len(segment_group)
                            base_value += safe_float(segment_group['Gettone overview'].sum())
                        else:
                            amount_col = 'GETTONE RES' if segment == 'RES' else 'GETTONE IVA'
                            count = len(segment_group) if pd.notna(c.get(amount_col)) else 0
                            base_value += count * safe_float(c.get(amount_col, 0))
                        metric_rows.append([agent, current_month, f'Contratti {segment}', count])
                    metric_rows.append([agent, current_month, 'Gettoni base', base_value])

                for agent in one.index:
                    c = one.loc[agent]
                    positive = 0.0
                    negative = 0.0
                    if model == 'Base':
                        if pd.notna(c.get('PREMIO UTENTI ATTIVI')) and pd.notna(c.get('MESI CALCOLO PREMIO DA ATTIVAZIONE')):
                            cohort = current_month - pd.DateOffset(
                                months=int(c['MESI CALCOLO PREMIO DA ATTIVAZIONE']) + 1
                            )
                            n = len(data[
                                (data['Agente'] == agent)
                                & (data['Mese'] == cohort)
                                & (data['Stato'] == 'ATTIVO')
                            ])
                            positive = n * float(c['PREMIO UTENTI ATTIVI'])
                        if pd.notna(c.get('STORNO UTENTI CESSATI')) and pd.notna(c.get('MESI CALCOLO STORNO DA ATTIVAZIONE')):
                            cohort = current_month - pd.DateOffset(
                                months=int(c['MESI CALCOLO STORNO DA ATTIVAZIONE']) + 1
                            )
                            n = len(data[
                                (data['Agente'] == agent)
                                & (data['Mese'] == cohort)
                                & (data['Stato'] == 'CHIUSO')
                            ])
                            negative = -n * abs(float(c['STORNO UTENTI CESSATI']))
                    else:
                        agent_data = data[data['Agente'] == agent].copy()
                        agent_data['Decorrenza ricorrente overview'] = agent_data['Prospected activation date'].pipe(parse_dates).apply(
                            lambda value: pd.NaT if pd.isna(value) else (
                                value.to_period('M').to_timestamp() if value.day == 1
                                else value.to_period('M').to_timestamp() + pd.offsets.MonthBegin(1)
                            )
                        )
                        agent_data['Ricorrente overview'] = agent_data.apply(
                            lambda row: row['Ricorrente RES overview'] if row['Customer type'] == 'Person'
                            else (row['Ricorrente IVA overview'] if row['Customer type'] == 'Partita IVA' else pd.NA), axis=1
                        )
                        active = agent_data[
                            (agent_data['Stato'] == 'ATTIVO')
                            & agent_data['Ricorrente overview'].notna()
                            & (agent_data['Decorrenza ricorrente overview'] <= current_month)
                            & (agent_data['Chiusura'].isna() | (current_month < agent_data['Chiusura']))
                        ]
                        positive = safe_float(active['Ricorrente overview'].sum())
                        agent_data['Gettone overview'] = agent_data.apply(
                            lambda row: row['Gettone RES overview'] if row['Customer type'] == 'Person'
                            else (row['Gettone IVA overview'] if row['Customer type'] == 'Partita IVA' else pd.NA),
                            axis=1,
                        )
                        closed = agent_data[
                            agent_data['Gettone overview'].notna()
                            & agent_data['Ricorrente overview'].notna()
                            & agent_data['Stato'].isin(GETTONE_STATI_VALIDI)
                            & (agent_data['Chiusura'] == current_month)
                        ]
                        for _, closed_row in closed.iterrows():
                            gettone = safe_float(
                                closed_row['Gettone RES overview'] if closed_row['Customer type'] == 'Person'
                                else closed_row['Gettone IVA overview']
                            )
                            negative -= gettone * malus_fascia(
                                months_lived(closed_row['Attivazione'], closed_row['Chiusura'])
                            )[1]
                    metric_rows.extend([
                        [agent, current_month, 'Premialità e ricorrenti', positive],
                        [agent, current_month, 'Storni e malus', negative],
                    ])

        # Cohort Churn per tutti gli agenti, unendo mapping Base e Avanzato senza duplicare il contratto.
        churn_source = pd.concat(mapped_datasets, ignore_index=True)
        churn_source = churn_source[churn_source['Agente'].notna()].copy()
        churn_source['Chiave churn'] = (
            churn_source['POD forecast'].fillna('') + '|'
            + churn_source['Attivazione'].astype(str)
            + '|' + churn_source['Agente'].astype(str)
        )
        churn_source = churn_source.drop_duplicates('Chiave churn')
        for observation_month in year_months:
            if observation_month > report_cutoff:
                continue
            cohort_month = observation_month - pd.DateOffset(months=13)
            cohort = churn_source[
                (churn_source['Attivazione'] == cohort_month)
                & (churn_source['Stato'] != 'ANNULLATO')
                & churn_source['POD forecast'].ne('')
            ]
            for agent, group in cohort.groupby('Agente'):
                switch_out = group['Chiusura'].between(
                    cohort_month + pd.DateOffset(months=1),
                    cohort_month + pd.DateOffset(months=12),
                    inclusive='both',
                ).sum()
                activated_count = len(group)
                churn = (switch_out / activated_count * 100) if activated_count else None
                metric_rows.extend([
                    [agent, observation_month, 'Cohort churn 12 mesi', churn],
                    [agent, observation_month, 'Cohort Switch OUT', int(switch_out)],
                    [agent, observation_month, 'Cohort attivati', int(activated_count)],
                ])

        metrics = pd.DataFrame(
            metric_rows, columns=['Agente', 'Mese', 'Metrica', 'Valore']
        ).groupby(['Agente', 'Mese', 'Metrica'], as_index=False)['Valore'].sum()
        all_agents = sorted(set(metrics['Agente'].dropna()) | set(agent_rates))

        def base_grid(metric, forecast_mode='last'):
            subset = metrics[metrics['Metrica'] == metric]
            pivot = subset.pivot_table(
                index='Agente', columns='Mese', values='Valore', aggfunc='sum'
            ).reindex(index=all_agents, columns=year_months)
            # Nessun mese effettivo viene stimato. I valori futuri dipendono dalla metrica:
            # volumi/premi: ultimo dato; storni/malus: zero; Churn: nd.
            for agent in pivot.index:
                history = [
                    float(pivot.loc[agent, m]) for m in year_months
                    if m <= report_cutoff and pd.notna(pivot.loc[agent, m])
                ]
                seed = history[-1] if history else None
                for m in year_months:
                    if m in forecast_months and pd.isna(pivot.loc[agent, m]):
                        if forecast_mode == 'last' and seed is not None:
                            pivot.loc[agent, m] = seed
                        elif forecast_mode == 'zero':
                            pivot.loc[agent, m] = 0
                        # forecast_mode == 'none': lascia NaN/nd
            pivot.columns = month_labels
            return pivot

        res_grid = base_grid('Contratti RES').fillna(0).round().astype(int)
        iva_grid = base_grid('Contratti IVA').fillna(0).round().astype(int)
        editable_columns = month_labels
        disabled_months = [
            label for label, current_month in zip(month_labels, year_months)
            if current_month not in forecast_months
        ]

        # Gli editor lavorano solo sui 12 mesi. La colonna Totali viene ricostruita
        # dopo ogni applicazione, evitando che Streamlit conservi un totale obsoleto.
        state_res_key = f'forecast_res_values_{selected_year}'
        state_iva_key = f'forecast_iva_values_{selected_year}'
        version_key = f'forecast_editor_version_{selected_year}'
        if state_res_key not in st.session_state:
            st.session_state[state_res_key] = res_grid[editable_columns].copy()
        if state_iva_key not in st.session_state:
            st.session_state[state_iva_key] = iva_grid[editable_columns].copy()
        if version_key not in st.session_state:
            st.session_state[version_key] = 0

        # La colonna Totali è visibile direttamente negli editor ma resta bloccata.
        # Dopo l'applicazione delle stime viene rigenerata dalla somma dei 12 mesi.
        editor_res = st.session_state[state_res_key].copy()
        editor_iva = st.session_state[state_iva_key].copy()
        editor_res['Totali'] = editor_res[month_labels].sum(axis=1).astype(int)
        editor_iva['Totali'] = editor_iva[month_labels].sum(axis=1).astype(int)
        disabled_with_total = disabled_months + ['Totali']
        editor_columns = editable_columns + ['Totali']
        editor_version = st.session_state[version_key]

        st.subheader('Contratti validi RES')
        st.caption('Sono modificabili soltanto i mesi futuri stimati. Totali è calcolato automaticamente.')
        with st.form(f'forecast_form_{selected_year}_v{editor_version}'):
            pending_res = st.data_editor(
                editor_res,
                use_container_width=True,
                disabled=disabled_with_total,
                key=f'forecast_res_editor_{selected_year}_v{editor_version}',
                column_config={
                    label: st.column_config.NumberColumn(
                        label, min_value=0, step=1, format='%d'
                    ) for label in editor_columns
                },
            )

            st.subheader('Contratti validi IVA')
            pending_iva = st.data_editor(
                editor_iva,
                use_container_width=True,
                disabled=disabled_with_total,
                key=f'forecast_iva_editor_{selected_year}_v{editor_version}',
                column_config={
                    label: st.column_config.NumberColumn(
                        label, min_value=0, step=1, format='%d'
                    ) for label in editor_columns
                },
            )
            apply_forecast = st.form_submit_button(
                'Applica stime e aggiorna totali',
                use_container_width=True,
                type='primary',
            )

        if apply_forecast:
            # Salva soltanto i mesi; Totali viene sempre ricalcolato.
            st.session_state[state_res_key] = pending_res[month_labels].astype(int).copy()
            st.session_state[state_iva_key] = pending_iva[month_labels].astype(int).copy()
            st.session_state[version_key] += 1
            st.rerun()

        edited_res = st.session_state[state_res_key].copy()
        edited_iva = st.session_state[state_iva_key].copy()
        edited_res['Totali'] = edited_res[month_labels].sum(axis=1).astype(int)
        edited_iva['Totali'] = edited_iva[month_labels].sum(axis=1).astype(int)

        premium_grid = base_grid('Premialità e ricorrenti', 'last').fillna(0).round().astype(int)
        negative_grid = base_grid('Storni e malus', 'zero').fillna(0).round().astype(int)
        churn_grid = base_grid('Cohort churn 12 mesi', 'none').round(0).astype('Int64')
        premium_grid['Totali'] = premium_grid[month_labels].sum(axis=1).astype(int)
        negative_grid['Totali'] = negative_grid[month_labels].sum(axis=1).astype(int)
        churn_out_grid = base_grid('Cohort Switch OUT', 'none')
        churn_activated_grid = base_grid('Cohort attivati', 'none')
        total_out = churn_out_grid[month_labels].sum(axis=1, min_count=1)
        total_activated = churn_activated_grid[month_labels].sum(axis=1, min_count=1)
        weighted_churn = (total_out / total_activated.where(total_activated > 0) * 100).round(0)
        churn_grid['Totali'] = weighted_churn.astype('Int64')

        # Le commissioni dei mesi futuri reagiscono alle stime manuali RES/IVA.
        net_grid = pd.DataFrame(0, index=all_agents, columns=month_labels, dtype=int)
        actual_base = base_grid('Gettoni base').fillna(0)
        for agent in all_agents:
            res_rate = agent_rates.get(agent, {}).get('RES', 0)
            iva_rate = agent_rates.get(agent, {}).get('IVA', 0)
            for label, current_month in zip(month_labels, year_months):
                if current_month in forecast_months:
                    gettoni = int(edited_res.loc[agent, label]) * res_rate + int(edited_iva.loc[agent, label]) * iva_rate
                else:
                    gettoni = int(round(float(actual_base.loc[agent, label]))) if pd.notna(actual_base.loc[agent, label]) else 0
                net_grid.loc[agent, label] = int(
                    round(gettoni + premium_grid.loc[agent, label] + negative_grid.loc[agent, label])
                )

        net_grid['Totali'] = net_grid[month_labels].sum(axis=1).astype(int)
        # Netto OPEX = commissioni nette escluse premialità e ricorrenti.
        # Mantiene invece storni e malus, che rettificano il costo commissionale.
        opex_grid = (
            net_grid[month_labels] - premium_grid[month_labels]
        ).round().astype(int)
        opex_grid['Totali'] = opex_grid[month_labels].sum(axis=1).astype(int)

        def format_integer_it(value, suffix=''):
            if pd.isna(value):
                return 'nd' if suffix == '%' else '—'
            return f"{int(value):,}".replace(',', '.') + suffix

        def show_integer_table(title, frame, suffix=''):
            st.subheader(title)
            display = frame.copy()
            styled = display.style.format(lambda value: format_integer_it(value, suffix))
            if 'Totali' in display.columns:
                styled = styled.set_properties(
                    subset=['Totali'],
                    **{'font-weight': '700', 'background-color': '#eef0ff'}
                )
            st.dataframe(styled, use_container_width=True)

        tab_incentivi, tab_rettifiche, tab_commissioni, tab_churn = st.tabs([
            'Incentivi', 'Rettifiche', 'Commissioni', 'Churn'
        ])
        with tab_incentivi:
            show_integer_table('Premialità e ricorrenti', premium_grid)
        with tab_rettifiche:
            show_integer_table('Storni e malus', negative_grid)
        with tab_commissioni:
            show_integer_table('Netto OPEX', opex_grid)
            st.caption(
                'Netto OPEX = Commissioni nette al netto di premialità e ricorrenti; '
                'storni e malus restano inclusi.'
            )
            show_integer_table('Commissioni nette', net_grid)
            monthly_net = net_grid[month_labels].sum(axis=0)
            st.bar_chart(monthly_net.rename('Commissioni nette'))
        with tab_churn:
            show_integer_table('Cohort Churn 12 mesi', churn_grid, '%')
            st.caption('I mesi futuri e le rilevazioni assenti restano nd. Totali è una media ponderata sui volumi.')

        def overview_single_sheet_export():
            output = io.BytesIO()
            churn_export = churn_grid.reset_index().astype(object)
            churn_export = churn_export.where(pd.notna(churn_export), 'nd')
            export_frames = [edited_res, edited_iva, premium_grid, negative_grid, opex_grid, net_grid, churn_grid]
            for frame in export_frames:
                frame.index.name = 'Agente'
            churn_export = churn_grid.reset_index().astype(object)
            churn_export = churn_export.where(pd.notna(churn_export), 'nd')
            tables = [
                ('Contratti validi RES', edited_res.reset_index()),
                ('Contratti validi IVA', edited_iva.reset_index()),
                ('Premialità e ricorrenti', premium_grid.reset_index()),
                ('Storni e malus', negative_grid.reset_index()),
                ('Netto OPEX', opex_grid.reset_index()),
                ('Commissioni nette', net_grid.reset_index()),
                ('Cohort Churn 12 mesi', churn_export),
            ]
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                row_pos = 0
                for title, table in tables:
                    pd.DataFrame([[title]]).to_excel(writer, sheet_name='Overview & Forecast', startrow=row_pos, index=False, header=False)
                    row_pos += 1
                    table.to_excel(writer, sheet_name='Overview & Forecast', startrow=row_pos, index=False)
                    row_pos += len(table) + 2
                ws = writer.book['Overview & Forecast']
                # Mantiene valori numerici e applica un formato intero con separatore delle migliaia.
                for row in ws.iter_rows():
                    for cell in row[1:]:
                        if isinstance(cell.value, (int, float)):
                            cell.number_format = '#,##0'
                for column in ws.columns:
                    values = [str(cell.value) if cell.value is not None else '' for cell in column]
                    ws.column_dimensions[column[0].column_letter].width = min(max(max(map(len, values), default=8) + 2, 10), 28)
            output.seek(0)
            return output.getvalue()

        forecast_export = overview_single_sheet_export()
        download_slot.download_button(
            'Scarica Overview & Forecast XLSX',
            forecast_export,
            file_name=f'overview_forecast_{selected_year}.xlsx',
            mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            use_container_width=True,
        )
        st.caption(
            f'Ultimo mese presente nel report: {report_cutoff:%m/%Y}. '
            'Le stime partono esclusivamente dal mese successivo e usano come valore iniziale '
            'l’ultimo dato disponibile, anche se parziale.'
        )
        render_footer()
        st.stop()

    if module == 'Commissioni Base':
        st.header('Commissioni Base')
        base_required = {
            'Agente', 'IDENTIFICATORI SUBCHANNEL', 'IDENTIFICATORI PROMO CODE',
            'ESCLUDI SELF', 'ESCLUDI GD',
            'GETTONE RES', 'GETTONE IVA', 'PREMIO UTENTI ATTIVI',
            'MESI CALCOLO PREMIO DA ATTIVAZIONE', 'STORNO UTENTI CESSATI',
            'MESI CALCOLO STORNO DA ATTIVAZIONE'
        }
        base_missing = base_required - set(mapping.columns)
        if base_missing:
            st.error('Colonne mancanti nel foglio Base: ' + ', '.join(sorted(base_missing)))
            render_footer()
            st.stop()

        base_configs = mapping.copy()
        base_configs['Sub IDs'] = base_configs['IDENTIFICATORI SUBCHANNEL'].apply(split_ids)
        base_configs['Promo IDs'] = base_configs['IDENTIFICATORI PROMO CODE'].apply(split_ids)
        numeric_cols = [
            'GETTONE RES', 'GETTONE IVA', 'PREMIO UTENTI ATTIVI',
            'MESI CALCOLO PREMIO DA ATTIVAZIONE', 'STORNO UTENTI CESSATI',
            'MESI CALCOLO STORNO DA ATTIVAZIONE'
        ]
        for c in numeric_cols:
            base_configs[c] = pd.to_numeric(base_configs[c], errors='coerce')

        base_df = contracts.copy()
        base_df['Data sottoscrizione'] = parse_dates(base_df['Contract: Customer Signed Date'])
        base_df['Data attivazione'] = parse_dates(base_df['Prospected activation date'])
        base_df['Data chiusura'] = parse_dates(base_df['Point of delivery: Closing date'])
        base_df['Mese sottoscrizione'] = base_df['Data sottoscrizione'].map(month)
        base_df['Mese attivazione'] = base_df['Data attivazione'].map(month)
        base_df['Mese chiusura'] = base_df['Data chiusura'].map(month)
        base_df['Stato'] = clean_status(base_df['Status from PoD'])
        base_df['Subscription Name'] = base_df['Subscription Name'].astype(str).str.strip()
        base_df['Point of Delivery'] = base_df['Point of delivery: Point of delivery Name'].astype(str).str.strip()

        def select_base(row):
            empty = [pd.NA] * 6
            sub_hits = base_configs[base_configs['Sub IDs'].apply(
                lambda ids: matches_subchannel(row.get('Subchannel'), ids)
            )]
            promo_hits = base_configs[base_configs['Promo IDs'].apply(
                lambda ids: contains_promo(row.get('Promo code'), ids)
            )]
            # Sub IDs e Promo IDs contengono liste, quindi non sono hashable.
            # Uniamo gli indici delle configurazioni trovate, evitando duplicati
            # senza applicare drop_duplicates() all'intero DataFrame.
            hit_indexes = sub_hits.index.union(promo_hits.index)
            hits = base_configs.loc[hit_indexes].copy()
            if hits.empty:
                return pd.Series([pd.NA, 'NON_MAPPATO'] + empty)
            # ESCLUDI SELF / ESCLUDI GD prevalgono anche sul match da Promo code.
            reasons = hits.apply(
                lambda r: exclusion_reason(row.get('Subchannel'), r['ESCLUDI SELF'], r['ESCLUDI GD']), axis=1
            )
            hits = hits[reasons.isna()]
            if hits.empty:
                return pd.Series([pd.NA, reasons.dropna().iloc[0]] + empty)
            agents = hits['Agente'].dropna().astype(str).unique().tolist()
            if len(agents) == 0:
                return pd.Series([pd.NA, 'NON_MAPPATO'] + empty)
            if len(agents) > 1:
                return pd.Series([pd.NA, 'CONFLITTO_SUBCHANNEL_PROMO'] + empty)
            cfg = hits[hits['Agente'].astype(str) == agents[0]].iloc[0]
            return pd.Series([
                agents[0], 'MAPPATO', cfg['GETTONE RES'], cfg['GETTONE IVA'],
                cfg['PREMIO UTENTI ATTIVI'], cfg['MESI CALCOLO PREMIO DA ATTIVAZIONE'],
                cfg['STORNO UTENTI CESSATI'], cfg['MESI CALCOLO STORNO DA ATTIVAZIONE']
            ])

        # Il mapping dipende solo da (Subchannel, Promo code): una volta per combinazione.
        base_keys = ['Subchannel', 'Promo code']
        base_combos = base_df[base_keys].drop_duplicates().reset_index(drop=True)
        selected_base = base_combos.apply(select_base, axis=1)
        selected_base.columns = [
            'Partner', 'Esito mapping', 'Gettone RES', 'Gettone IVA',
            'Premio utenti attivi', 'Mesi premio', 'Storno utenti cessati', 'Mesi storno'
        ]
        base_combos = pd.concat([base_combos, selected_base], axis=1)
        base_df = base_df.merge(base_combos, on=base_keys, how='left')
        base_df['Segmento'] = base_df['Customer type'].map({'Person': 'Residenziale', 'Partita IVA': 'Business'})
        base_df['Gettone base'] = base_df.apply(
            lambda r: r['Gettone RES'] if r['Customer type'] == 'Person' else (
                r['Gettone IVA'] if r['Customer type'] == 'Partita IVA' else pd.NA
            ), axis=1
        )

        # Gettone base: contratti generati nel mese di competenza con stato valido
        # (tutti tranne ANNULLATO e SOSPESO, CHIUSO incluso). Vale per tutti gli agenti Base.
        base_gettoni = base_df[
            base_df['Partner'].notna()
            & (base_df['Mese sottoscrizione'] == competence)
            & base_df['Stato'].isin(GETTONE_STATI_VALIDI)
            & base_df['Gettone base'].notna()
        ].copy()
        base_gettoni['Tipo movimento'] = 'GETTONE_BASE'
        base_gettoni['Importo'] = base_gettoni['Gettone base']

        # Annullati e sospesi del mese: segnalati per trasparenza, importo zero.
        base_esclusi_stato = base_df[
            base_df['Partner'].notna()
            & (base_df['Mese sottoscrizione'] == competence)
            & base_df['Stato'].isin(['ANNULLATO', 'SOSPESO'])
        ].copy()
        base_esclusi_stato['Tipo movimento'] = 'ESCLUSO_PER_STATO'
        base_esclusi_stato['Importo'] = 0.0

        # Premio Base per coorte di firma: X mesi di vita + 2 mesi tecnici,
        # con la competenza inclusa. Offset effettivo = X + 2 - 1 = X + 1.
        # Lo stato ATTIVO viene osservato nel report consolidato corrente.
        base_premi = base_df[
            base_df['Partner'].notna()
            & base_df['Premio utenti attivi'].notna()
            & base_df['Mesi premio'].notna()
            & (base_df['Stato'] == 'ATTIVO')
        ].copy()
        base_premi['Mesi tecnici pre-attivazione'] = 2
        base_premi['Mese obiettivo premio'] = base_premi['Mesi premio'].apply(
            lambda x: competence - pd.DateOffset(months=int(x) + 1)
        )
        base_premi = base_premi[
            base_premi['Mese sottoscrizione'] == base_premi['Mese obiettivo premio']
        ].copy()
        base_premi['Tipo movimento'] = 'PREMIO_UTENTI_ATTIVI'
        base_premi['Importo'] = base_premi['Premio utenti attivi']

        # Storno: coorte sottoscritta X + 2 mesi tecnici, con conteggio inclusivo
        # della competenza. Offset effettivo = X + 2 - 1 = X + 1.
        base_storni = base_df[
            base_df['Partner'].notna()
            & base_df['Storno utenti cessati'].notna()
            & base_df['Mesi storno'].notna()
            & (base_df['Stato'] == 'CHIUSO')
        ].copy()
        base_storni['Mesi tecnici pre-attivazione'] = 2
        base_storni['Mese obiettivo storno'] = base_storni['Mesi storno'].apply(
            lambda x: competence - pd.DateOffset(months=int(x) + 1)
        )
        base_storni = base_storni[
            base_storni['Mese sottoscrizione'] == base_storni['Mese obiettivo storno']
        ].copy()
        base_storni['Tipo movimento'] = 'STORNO_UTENTI_CESSATI'
        base_storni['Importo'] = -base_storni['Storno utenti cessati'].abs()

        base_movements = pd.concat([base_gettoni, base_premi, base_storni], ignore_index=True)
        base_summary = base_movements.pivot_table(
            index='Partner', columns='Tipo movimento', values='Importo', aggfunc='sum', fill_value=0
        ).reset_index()
        for c in ['GETTONE_BASE', 'PREMIO_UTENTI_ATTIVI', 'STORNO_UTENTI_CESSATI']:
            if c not in base_summary:
                base_summary[c] = 0.0
        base_summary['TOTALE_NETTO'] = base_summary[
            ['GETTONE_BASE', 'PREMIO_UTENTI_ATTIVI', 'STORNO_UTENTI_CESSATI']
        ].sum(axis=1)
        base_summary = base_summary[
            ['Partner', 'GETTONE_BASE', 'PREMIO_UTENTI_ATTIVI', 'STORNO_UTENTI_CESSATI', 'TOTALE_NETTO']
        ].sort_values('Partner')

        st.markdown('### Riepilogo economico')
        st.caption(f'Competenza {competence:%m/%Y}')
        c1, c2, c3, c4 = st.columns(4)
        render_light_metric(c1, 'Gettone base', format_euro(base_gettoni['Importo'].sum()))
        render_light_metric(c2, 'Premialità', format_euro(base_premi['Importo'].sum()))
        render_light_metric(c3, 'Storni', format_euro(base_storni['Importo'].sum()))
        c4.metric('Totale netto', format_euro(base_movements['Importo'].sum()))

        st.subheader('Sintesi agenti e report individuali')
        base_partners = sorted(
            set(base_df.loc[
                (base_df['Mese sottoscrizione'] == competence) & base_df['Partner'].notna(),
                'Partner',
            ])
            | set(base_premi['Partner'].dropna())
            | set(base_storni['Partner'].dropna())
        )
        base_partner_reports = []
        for partner in base_partners:
            p_gettoni = base_gettoni[base_gettoni['Partner'] == partner].copy()
            p_nonvalid = base_df[
                (base_df['Partner'] == partner)
                & (base_df['Mese sottoscrizione'] == competence)
                & ~base_df.index.isin(p_gettoni.index)
            ].copy()
            p_nonvalid['Motivo non validità'] = p_nonvalid.apply(
                lambda row: 'Stato non commissionabile'
                if row['Stato'] not in GETTONE_STATI_VALIDI
                else ('Gettone segmento mancante' if pd.isna(row['Gettone base']) else 'Escluso dal gettone'),
                axis=1,
            )
            p_premi = base_premi[base_premi['Partner'] == partner].copy()
            p_storni = base_storni[base_storni['Partner'] == partner].copy()
            amount_base = float(p_gettoni['Importo'].sum())
            amount_premio = float(p_premi['Importo'].sum())
            amount_storno = float(p_storni['Importo'].sum())
            amount_netto = amount_base + amount_premio + amount_storno
            p_summary = pd.DataFrame([
                {'Voce': 'Contratti validi', 'Numero': len(p_gettoni), 'Importo': amount_base},
                {'Voce': 'Contratti non validi', 'Numero': len(p_nonvalid), 'Importo': 0.0},
                {'Voce': 'Utenti attivi premiati', 'Numero': len(p_premi), 'Importo': amount_premio},
                {'Voce': 'Utenti cessati stornati', 'Numero': len(p_storni), 'Importo': amount_storno},
                {'Voce': 'TOTALE NETTO', 'Numero': pd.NA, 'Importo': amount_netto},
            ])
            partner_cfg = base_configs[
                base_configs['Agente'].astype(str).str.strip() == str(partner).strip()
            ]
            include_base_pod = bool(
                not partner_cfg.empty
                and partner_cfg['ESCLUDI SELF'].apply(is_yes).all()
                and partner_cfg['ESCLUDI GD'].apply(is_yes).all()
            )
            partner_export = to_excel({
                'Sintesi': p_summary,
                'Contratti validi': p_gettoni,
                'Non validi': p_nonvalid,
                'Premio utenti attivi': p_premi,
                'Storno utenti cessati': p_storni,
            }, include_pod=include_base_pod)
            safe_partner = re.sub(r'[^A-Za-z0-9._-]+', '_', str(partner)).strip('_') or 'partner'
            base_report_name = f'report_base_{safe_partner}_{competence:%Y_%m}.xlsx'
            base_partner_reports.append((base_report_name, partner_export))
            with st.container(border=True):
                title_col, net_col, action_col = st.columns([2.5,1.3,1.1])
                title_col.markdown(f'### {partner}')
                title_col.caption(f'{len(p_gettoni):,} contratti commissionabili')
                net_col.metric('Totale netto',format_euro(amount_netto))
                action_col.download_button('Scarica report',partner_export,file_name=base_report_name,mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',key=f'base_{safe_partner}_{competence:%Y_%m}')
                k1,k2,k3=st.columns(3)
                render_light_metric(k1, 'Gettone base', format_euro(amount_base))
                render_light_metric(k2, 'Premialità', format_euro(amount_premio))
                render_light_metric(k3, 'Storni', format_euro(amount_storno))
                with st.expander('Visualizza dettagli'):
                    st.dataframe(p_summary,use_container_width=True,hide_index=True)

        # Controlli limitati ai contratti della competenza (non all'intero report).
        base_rilevante = base_df['Mese sottoscrizione'] == competence
        base_unmapped = base_df[
            base_rilevante & base_df['Esito mapping'].isin(['NON_MAPPATO', 'CONFLITTO_SUBCHANNEL_PROMO'])
        ].copy()
        base_excl_sg = base_df[
            base_rilevante & base_df['Esito mapping'].isin(['ESCLUSO_SELF', 'ESCLUSO_GD'])
        ].copy()
        base_incomplete = base_df[
            base_df['Partner'].notna()
            & base_rilevante
            & base_df['Gettone base'].isna()
        ].copy()
        st.subheader('Qualità dei dati')
        st.write(
            f'Non mappati/conflitti: **{len(base_unmapped)}** | '
            f'Esclusi SELF/GD: **{len(base_excl_sg)}** | '
            f'Annullati/sospesi del mese: **{len(base_esclusi_stato)}** | '
            f'Gettoni mancanti per segmento: **{len(base_incomplete)}**'
        )
        base_export = to_excel({
            'Sintesi agenti': base_summary,
            'Movimenti': base_movements,
            'Contratti del mese': base_gettoni,
            'Premio utenti attivi': base_premi,
            'Storno utenti cessati': base_storni,
            'Annullati e sospesi': base_esclusi_stato,
            'Non mappati': base_unmapped,
            'Esclusi SELF-GD': base_excl_sg,
            'Config incomplete': base_incomplete,
        })
        base_reports_zip = reports_to_zip(tuple(base_partner_reports))
        base_full_col, base_all_col = st.columns(2)
        with base_full_col:
            st.download_button(
                'Scarica risultato completo Base', base_export,
                file_name=f'commissioni_base_{competence:%Y_%m}.xlsx',
                mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                use_container_width=True,
            )
        with base_all_col:
            st.download_button(
                'Scarica tutti i report', base_reports_zip,
                file_name=f'report_agenti_base_{competence:%Y_%m}.zip',
                mime='application/zip', use_container_width=True,
                disabled=not base_partner_reports,
                key=f'download_all_base_{competence:%Y_%m}',
            )
        render_footer()
        st.stop()

    map_required = {
        'Agente', 'IDENTIFICATORI SUBCHANNEL', 'IDENTIFICATORI PROMO CODE',
        'DECORRENZA', 'ESCLUDI SELF', 'ESCLUDI GD',
        'GETTONE RES', 'GETTONE IVA', 'RICORRENTE RES', 'RICORRENTE IVA'
    }
    map_missing = map_required - set(mapping.columns)
    if map_missing:
        st.error('Colonne mancanti nel file identificatori: ' + ', '.join(sorted(map_missing)))
        render_footer()
        st.stop()

    configs = mapping.copy()
    configs['Decorrenza'] = configs['DECORRENZA'].apply(parse_decorrenza)
    configs['Sub IDs'] = configs['IDENTIFICATORI SUBCHANNEL'].apply(split_ids)
    configs['Promo IDs'] = configs['IDENTIFICATORI PROMO CODE'].apply(split_ids)
    # Consente versioni come SWITCHO e SWITCHO 2028 senza dipendere dal nome.
    configs['Gruppo mapping'] = configs.apply(
        lambda r: '|'.join(sorted(norm(x) for x in r['Sub IDs'])) + '//' + '|'.join(sorted(norm(x) for x in r['Promo IDs'])), axis=1
    )
    for c in ['GETTONE RES', 'GETTONE IVA', 'RICORRENTE RES', 'RICORRENTE IVA']:
        configs[c] = pd.to_numeric(configs[c], errors='coerce')

    # Campi opzionali per il programma Bonus Churn.
    if 'BONUS CHURN' not in configs.columns:
        configs['BONUS CHURN'] = 'NO'
    if 'DECORRENZA BONUS CHURN' not in configs.columns:
        configs['DECORRENZA BONUS CHURN'] = pd.NaT
    configs['Bonus churn attivo'] = configs['BONUS CHURN'].apply(
        lambda v: str(v).strip().upper() in {'SI', 'SÌ', 'YES', 'TRUE', '1'}
    )
    configs['Decorrenza bonus churn'] = configs['DECORRENZA BONUS CHURN'].apply(parse_decorrenza)

    invalid_configs = configs[
        configs['Decorrenza'].notna()
        & configs[['GETTONE RES', 'GETTONE IVA', 'RICORRENTE RES', 'RICORRENTE IVA']].isna().any(axis=1)
    ].copy()

    df = contracts.copy()
    df['Data sottoscrizione'] = parse_dates(df['Contract: Customer Signed Date'])
    df['Data attivazione'] = parse_dates(df['Prospected activation date'])
    df['Data chiusura'] = parse_dates(df['Point of delivery: Closing date'])
    df['Mese sottoscrizione'] = df['Data sottoscrizione'].map(month)
    df['Mese attivazione'] = df['Data attivazione'].map(month)
    df['Mese chiusura'] = df['Data chiusura'].map(month)
    df['Stato'] = clean_status(df['Status from PoD'])
    df['Subscription Name'] = df['Subscription Name'].astype(str).str.strip()
    df['Point of Delivery'] = df['Point of delivery: Point of delivery Name'].astype(str).str.strip()
    df['ID fornitura'] = df.apply(
        lambda r: f"{r['Point of Delivery']}|{r['Data attivazione']:%Y-%m-%d}"
        if r['Point of Delivery'] and pd.notna(r['Data attivazione']) else '',
        axis=1
    )
    df['ID contratto'] = df['ID fornitura']

    # Il mapping dipende solo da (Subchannel, Promo code, mese di sottoscrizione):
    # si calcola una volta per combinazione e si riporta su tutte le righe.
    sel_keys = ['Subchannel', 'Promo code', 'Mese sottoscrizione']
    sel_combos = df[sel_keys].drop_duplicates().reset_index(drop=True)
    selected = sel_combos.apply(lambda r: select_configuration(r, configs), axis=1)
    selected.columns = [
        'Partner', 'Esito mapping', 'Decorrenza partner', 'Gettone RES',
        'Gettone IVA', 'Ricorrente RES', 'Ricorrente IVA', 'Partner storico'
    ]
    sel_combos = pd.concat([sel_combos, selected], axis=1)
    df = df.merge(sel_combos, on=sel_keys, how='left')

    df['Segmento'] = df['Customer type'].map({'Person': 'Residenziale', 'Partita IVA': 'Business'})
    df['Gettone'] = df.apply(
        lambda r: r['Gettone RES'] if r['Customer type'] == 'Person' else (
            r['Gettone IVA'] if r['Customer type'] == 'Partita IVA' else pd.NA
        ), axis=1
    )
    df['Ricorrente'] = df.apply(
        lambda r: r['Ricorrente RES'] if r['Customer type'] == 'Person' else (
            r['Ricorrente IVA'] if r['Customer type'] == 'Partita IVA' else pd.NA
        ), axis=1
    )

    # Il partner/configurazione selezionato incorpora gia la decorrenza corretta per la coorte.
    eligible_scope = df['Partner'].notna() & df['Gettone'].notna() & df['Ricorrente'].notna()

    if module == 'Bonus Churn - rilevazioni e idoneità':
        st.header('Bonus Churn')
        st.caption(
            'Il percorso annuale di ogni agente è calcolato automaticamente dalla relativa '
            'DECORRENZA BONUS CHURN. Le date sono mostrate solo come mese/anno.'
        )

        cohort_cols = ['Partner', 'Mese rilevazione', 'Mese coorte', 'POD/PDR attivati', 'Switch OUT', 'Cohort Churn']
        # Rilevazioni ricostruite interamente dal report Salesforce caricato.
        # Nessun registro storico separato è richiesto.

        # Il mese massimo del report è il limite per le rilevazioni consolidabili.
        data_cutoff = df['Mese sottoscrizione'].dropna().max()
        min_activation = df.loc[
            df['Partner storico'].notna() & df['Mese attivazione'].notna(), 'Mese attivazione'
        ].min()
        observation_frames, detail_frames = [], []
        if pd.notna(min_activation) and pd.notna(data_cutoff):
            first_observation = month(min_activation + pd.DateOffset(months=13))
            for obs_month in pd.date_range(first_observation, data_cutoff, freq='MS'):
                cohort_month = month(obs_month - pd.DateOffset(months=13))
                window_start = month(cohort_month + pd.DateOffset(months=1))
                window_end = month(cohort_month + pd.DateOffset(months=12))
                activated_m = df[
                    df['Partner storico'].notna()
                    & (df['Mese attivazione'] == cohort_month)
                    & (df['Stato'] != 'ANNULLATO')
                    & df['ID fornitura'].ne('')
                ].copy()
                if activated_m.empty:
                    continue
                activated_m['Partner coorte'] = activated_m['Partner storico']
                activated_m['Mese rilevazione'] = obs_month
                activated_m['Mese coorte osservata'] = cohort_month
                activated_m['È Switch OUT'] = activated_m['Mese chiusura'].between(window_start, window_end, inclusive='both')
                obs = activated_m.groupby('Partner coorte', as_index=False).agg(
                    **{'POD/PDR attivati': ('ID contratto', 'nunique'), 'Switch OUT': ('È Switch OUT', 'sum')}
                ).rename(columns={'Partner coorte': 'Partner'})
                obs['Mese rilevazione'] = obs_month
                obs['Mese coorte'] = cohort_month
                obs['Cohort Churn'] = obs['Switch OUT'] / obs['POD/PDR attivati'].where(obs['POD/PDR attivati'] > 0)
                observation_frames.append(obs[cohort_cols])
                detail_frames.append(activated_m)

        observations = pd.concat(observation_frames, ignore_index=True) if observation_frames else pd.DataFrame(columns=cohort_cols)
        activated_detail = pd.concat(detail_frames, ignore_index=True) if detail_frames else pd.DataFrame()
        cohort_updated = observations.copy()
        if not cohort_updated.empty:
            cohort_updated = cohort_updated.sort_values(
                ['Partner', 'Mese rilevazione']
            ).reset_index(drop=True)

        config_status = configs.sort_values('Decorrenza').groupby('Agente', as_index=False).tail(1)
        partner_results = {}
        for _, cfg in config_status.iterrows():
            if not bool(cfg['Bonus churn attivo']):
                continue
            partner = cfg['Agente']
            start = cfg['Decorrenza bonus churn']
            hist = cohort_updated[cohort_updated['Partner'] == partner].copy()
            baseline, quarters, annual, info = evaluate_partner_bonus(partner, hist, start, data_cutoff)
            partner_results[partner] = {
                'start': start, 'hist': hist, 'baseline': baseline,
                'quarters': quarters, 'annual': annual, 'info': info,
            }

        st.subheader('Stato partner')
        if not partner_results:
            st.info('Nessun agente risulta iscritto al programma Bonus Churn.')
        else:
            for partner,result in partner_results.items():
                info=result['info']; baseline=result['baseline']
                progress=float(info.get('Progressione',0.0)); months_done=int(info.get('Mesi consolidati',0))
                with st.container(border=True):
                    name_col,status_col,action_col=st.columns([2.4,1.6,1.0])
                    name_col.markdown(f'### {partner}')
                    if baseline:
                        name_col.caption(f"{baseline['Classe di partenza']} · {baseline['Cohort Churn di partenza (%)']:.1f}% churn")
                    else:
                        name_col.caption('Baseline non ancora disponibile')
                    status_col.metric('Percorso annuale',f'{months_done}/12 mesi')
                    if action_col.button('Dettagli',key=f'details_bonus_{norm(partner)}',use_container_width=True):
                        st.session_state['bonus_partner_selected']=partner
                    render_quarter_track(result['quarters'])
                    render_annual_status(result['annual'])
                    st.caption(
                        f"{months_done}/12 mesi consolidati · "
                        f"Decorrenza {format_month_year(result['start'])} · "
                        f"fine ciclo {info.get('Fine ciclo','')}"
                    )

            selected_partner = st.session_state.get('bonus_partner_selected')
            if selected_partner in partner_results:
                result = partner_results[selected_partner]
                info = result['info']
                baseline = result['baseline']
                quarters = result['quarters']
                annual = result['annual']
                st.divider()
                st.subheader(f'Dettagli - {selected_partner}')
                st.write(f"**Decorrenza:** {format_month_year(result['start'])}")
                if baseline is None:
                    st.warning(info.get('Messaggio', 'Storico insufficiente.'))
                else:
                    st.write(
                        f"**Classe di partenza:** {baseline['Classe di partenza']} "
                        f"({baseline['Cohort Churn di partenza (%)']:.1f}% churn)"
                    )
                    st.write(
                        '**Micro-classe BEGINNER:** '
                        + (baseline['Micro-classe BEGINNER'] or 'No')
                    )

                    for quarter in quarters:
                        with st.container(border=True):
                            st.markdown(f"### Report {quarter['Trimestre']} · {quarter['Periodo']}")
                            st.write('**Stato:** Completato')
                        st.write(f"**Periodo:** {quarter['Periodo']}")
                        st.write(f"**Churn iniziale:** {quarter['Churn iniziale (%)']:.1f}%")
                        if baseline['Classe di partenza'] == 'BEGINNER':
                            st.write(f"**Target trimestre:** -{quarter['Target trimestre (p.p.)']:.1f} p.p.")
                        st.write(f"**Churn rilevato:** {quarter['Churn rilevato (%)']:.1f}%")
                        st.write(f"**Idoneità:** {quarter['Idoneità'].title()}")
                        q_df = pd.DataFrame([quarter])
                        q_export = to_excel({'Sintesi trimestre': q_df})
                        st.download_button(
                            f"Scarica report {quarter['Trimestre']}", q_export,
                            file_name=f"bonus_churn_{norm(selected_partner)}_{quarter['Trimestre'].lower()}.xlsx",
                            mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                            key=f"download_bonus_{norm(selected_partner)}_{quarter['Trimestre']}"
                        )

                    if annual is not None:
                        st.markdown('## Risultato annuale')
                        st.write('**Stato:** Completato')
                        st.write(f"**Periodo:** {annual['Periodo']}")
                        st.write(f"**Churn iniziale:** {annual['Churn iniziale (%)']:.1f}%")
                        st.write(f"**Churn rilevato:** {annual['Churn rilevato (%)']:.1f}%")
                        st.write(f"**Idoneità:** {annual['Idoneità'].title()}")
                        st.write(f"**Nuova classe:** {annual['Nuova classe']}")
                        annual_export = to_excel({'Sintesi annuale': pd.DataFrame([annual])})
                        st.download_button(
                            'Scarica report Annuale', annual_export,
                            file_name=f"bonus_churn_{norm(selected_partner)}_annuale.xlsx",
                            mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                            key=f"download_bonus_{norm(selected_partner)}_annuale"
                        )

        st.caption('I report trimestrali e annuali compaiono soltanto quando tutte le rilevazioni necessarie sono disponibili.')
        # Nessun upload o download di registro: lo storico è ricostruito dal report.
        render_footer()
        st.stop()

    # Gettone Avanzato: stati validi = tutti tranne ANNULLATO e SOSPESO (CHIUSO incluso).
    in_competence = df['Mese sottoscrizione'] == competence
    initial = df[
        eligible_scope
        & in_competence
        & df['Stato'].isin(GETTONE_STATI_VALIDI)
    ].copy()
    initial['Tipo movimento'] = 'GETTONE_INIZIALE'
    initial['Importo'] = initial['Gettone']

    cancelled = df[eligible_scope & in_competence & (df['Stato'] == 'ANNULLATO')].copy()
    cancelled['Tipo movimento'] = 'ANNULLAMENTO_SEGNALATO'
    cancelled['Importo'] = 0.0

    suspended = df[eligible_scope & in_competence & (df['Stato'] == 'SOSPESO')].copy()
    suspended['Tipo movimento'] = 'SOSPESO_SEGNALATO'
    suspended['Importo'] = 0.0

    # Ricorrente dal primo mese pieno, solo per contratti ATTIVO. Il mese della chiusura è escluso
    # perché non è completo (una chiusura già pianificata non toglie il ricorrente dei mesi precedenti).
    df['Mese decorrenza mini-gettone'] = df['Data attivazione'].apply(
        lambda d: pd.NaT if pd.isna(d) else (
            d.to_period('M').to_timestamp()
            if d.day == 1
            else d.to_period('M').to_timestamp() + pd.offsets.MonthBegin(1)
        )
    )
    recurring = df[
        eligible_scope
        & (df['Stato'] == 'ATTIVO')
        & df['Mese decorrenza mini-gettone'].notna()
        & (df['Mese decorrenza mini-gettone'] <= competence)
        & (df['Mese chiusura'].isna() | (competence < df['Mese chiusura']))
    ].copy()
    recurring['Tipo movimento'] = 'RICORRENTE'
    recurring['Importo'] = recurring['Ricorrente']

    # Ogni chiusura appartiene a una sola competenza: il mese della Closing Date.
    # Il malus riguarda solo contratti che avrebbero preso il gettone (stato valido, quindi non ANNULLATO).
    # Conta solo il mese di calendario; una chiusura senza attivazione vale come churn a 3 mesi (100%).
    churn_scope = (
        eligible_scope
        & df['Stato'].isin(GETTONE_STATI_VALIDI)
        & (df['Mese chiusura'] == competence)
    )
    churn = df[churn_scope].copy()
    churn['Mesi di vita'] = [
        months_lived(a, c) for a, c in zip(churn['Data attivazione'], churn['Data chiusura'])
    ]
    fasce = [malus_fascia(m) for m in churn['Mesi di vita']]
    churn['Fascia malus'] = [f for f, _ in fasce]
    churn['Motivo malus'] = [
        'Chiusura senza attivazione (trattata come churn a 3 mesi)' if pd.isna(m)
        else ("Chiusura prima dell'attivazione" if m <= 0 else f'Chiusura al mese {int(m)} di vita')
        for m in churn['Mesi di vita']
    ]
    churn['Importo'] = [-float(g) * share for (_, share), g in zip(fasce, churn['Gettone'])]
    no_activation = churn[churn['Data attivazione'].isna()].copy()
    malus_new = churn[churn['Importo'] != 0].copy()
    malus_new['Tipo movimento'] = 'MALUS_CHURN'

    cols = [
        'ID fornitura', 'Point of Delivery', 'Subscription Name',
        'Partner', 'Segmento', 'Customer type', 'Stato',
        'Contract: Customer Signed Date', 'Prospected activation date', 'Point of delivery: Closing date',
        'Subchannel', 'Promo code', 'Tipo movimento', 'Importo'
    ]
    movements = pd.concat([initial[cols], recurring[cols], malus_new[cols]], ignore_index=True)

    summary = movements.pivot_table(
        index='Partner', columns='Tipo movimento', values='Importo', aggfunc='sum', fill_value=0
    ).reset_index()
    for c in ['GETTONE_INIZIALE', 'RICORRENTE', 'MALUS_CHURN']:
        if c not in summary:
            summary[c] = 0.0
    summary['TOTALE_DA_PAGARE'] = summary[
        ['GETTONE_INIZIALE', 'RICORRENTE', 'MALUS_CHURN']
    ].sum(axis=1)
    summary = summary[
        ['Partner', 'GETTONE_INIZIALE', 'RICORRENTE', 'MALUS_CHURN', 'TOTALE_DA_PAGARE']
    ].sort_values('Partner')

    # Controlli limitati ai contratti rilevanti per la competenza (sottoscritti o chiusi nel mese),
    # non all'intero report.
    rilevante = in_competence | (df['Mese chiusura'] == competence)
    unmapped = df[rilevante & df['Esito mapping'].isin([
        'NON_MAPPATO', 'NON_MAPPATO_BILLOO_PROMO_NON_SUFFICIENTE',
        'CONFLITTO_SUBCHANNEL_PROMO', 'CONFLITTO_PARTNER'
    ])].copy()
    excluded = df[rilevante & df['Esito mapping'].str.contains('MODELLO_NON_ATTIVO', na=False)].copy()
    excluded_sg = df[rilevante & df['Esito mapping'].isin(['ESCLUSO_SELF', 'ESCLUSO_GD'])].copy()

    duplicate_supply = df['ID fornitura'].ne('') & df.duplicated('ID fornitura', keep=False)
    anomaly_flags = pd.DataFrame({
        'Customer Signed Date mancante': df['Data sottoscrizione'].isna(),
        'Segmento non riconosciuto': df['Segmento'].isna(),
        'POD/PDR mancante': df['Point of Delivery'].eq(''),
        'Attivazione mancante': (df['Stato'] != 'ANNULLATO') & df['Data attivazione'].isna(),
        'Chiusura senza attivazione': df['Data chiusura'].notna() & df['Data attivazione'].isna(),
        "Chiusura prima dell'attivazione": df['Data chiusura'].notna() & (df['Data chiusura'] < df['Data attivazione']),
        'ID fornitura duplicato': duplicate_supply,
        'Stato non riconosciuto': ~df['Stato'].isin(STATI_NOTI),
        'CHIUSO senza Closing date': (df['Stato'] == 'CHIUSO') & df['Data chiusura'].isna(),
    }, index=df.index)
    anomaly_scope = rilevante | (df['Partner'].notna() & (df['Stato'] == 'ATTIVO')) | df['Data sottoscrizione'].isna()
    anomalies = df[anomaly_scope & anomaly_flags.any(axis=1)].copy()
    anomalies['Motivi anomalia'] = join_reasons(anomaly_flags.loc[anomalies.index])

    st.markdown('### Riepilogo economico')
    st.caption(f'Competenza {competence:%m/%Y}')
    c1, c2, c3, c4 = st.columns(4)
    render_light_metric(c1, 'Gettoni iniziali', format_euro(initial['Importo'].sum()))
    render_light_metric(c2, 'Ricorrenti', format_euro(recurring['Importo'].sum()))
    render_light_metric(c3, 'Nuovi malus', format_euro(malus_new['Importo'].sum()))
    c4.metric('Totale netto', format_euro(movements['Importo'].sum()))

    st.subheader('Sintesi partner e report individuali')
    st.dataframe(summary, use_container_width=True)
    advanced_partners = sorted(
        set(df.loc[in_competence & df['Partner'].notna(), 'Partner'])
        | set(recurring['Partner'].dropna())
        | set(malus_new['Partner'].dropna())
    )
    advanced_partner_reports = []
    for partner in advanced_partners:
        p_initial = initial[initial['Partner'] == partner].copy()
        p_nonvalid = df[
            (df['Partner'] == partner)
            & (df['Mese sottoscrizione'] == competence)
            & ~df.index.isin(p_initial.index)
        ].copy()
        p_nonvalid['Motivo non validità'] = p_nonvalid.apply(
            lambda row: 'Stato non commissionabile'
            if row['Stato'] not in GETTONE_STATI_VALIDI
            else ('Configurazione economica incompleta' if pd.isna(row['Gettone']) else 'Escluso dal gettone'),
            axis=1,
        )
        p_recurring = recurring[recurring['Partner'] == partner].copy()
        p_malus = malus_new[malus_new['Partner'] == partner].copy()
        p_100 = p_malus[p_malus['Fascia malus'] == '100%'].copy()
        p_50 = p_malus[p_malus['Fascia malus'] == '50%'].copy()
        base_amount = float(p_initial['Importo'].sum())
        recurring_amount = float(p_recurring['Importo'].sum())
        malus_amount = float(p_malus['Importo'].sum())
        net_amount = base_amount + recurring_amount + malus_amount
        p_summary = pd.DataFrame([
            {'Voce': 'Contratti validi', 'Numero': len(p_initial), 'Importo': base_amount},
            {'Voce': 'Contratti non validi', 'Numero': len(p_nonvalid), 'Importo': 0.0},
            {'Voce': 'Ricorrenti', 'Numero': len(p_recurring), 'Importo': recurring_amount},
            {'Voce': 'Malus 100%', 'Numero': len(p_100), 'Importo': float(p_100['Importo'].sum())},
            {'Voce': 'Malus 50%', 'Numero': len(p_50), 'Importo': float(p_50['Importo'].sum())},
            {'Voce': 'Decurtazioni per chiusure', 'Numero': len(p_malus), 'Importo': malus_amount},
            {'Voce': 'TOTALE NETTO', 'Numero': pd.NA, 'Importo': net_amount},
        ])
        partner_export = to_excel({
            'Sintesi': p_summary,
            'Contratti validi': p_initial,
            'Non validi': p_nonvalid,
            'Ricorrenti': p_recurring,
            'Malus 100%': p_100,
            'Malus 50%': p_50,
        }, include_pod=True)
        safe_partner = re.sub(r'[^A-Za-z0-9._-]+', '_', str(partner)).strip('_') or 'partner'
        advanced_report_name = f'report_avanzato_{safe_partner}_{competence:%Y_%m}.xlsx'
        advanced_partner_reports.append((advanced_report_name, partner_export))
        with st.container(border=True):
            title_col,net_col,action_col=st.columns([2.5,1.3,1.1])
            title_col.markdown(f'### {partner}')
            title_col.caption(f'{len(p_initial):,} contratti con gettone')
            net_col.metric('Totale netto',format_euro(net_amount))
            action_col.download_button('Scarica report',partner_export,file_name=advanced_report_name,mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',key=f'avanzato_{safe_partner}_{competence:%Y_%m}')
            k1,k2,k3=st.columns(3)
            render_light_metric(k1, 'Gettone base', format_euro(base_amount))
            render_light_metric(k2, 'Ricorrenti', format_euro(recurring_amount))
            render_light_metric(k3, 'Malus', format_euro(malus_amount))
            with st.expander('Visualizza dettagli'):
                st.dataframe(p_summary,use_container_width=True,hide_index=True)
    st.subheader('Qualità dei dati')
    st.write(
        f'Non mappati/conflitti: **{len(unmapped)}** | '
        f'Esclusi SELF/GD: **{len(excluded_sg)}** | '
        f'Partner con modello non attivo: **{len(excluded)}** | '
        f'Sospesi del mese: **{len(suspended)}** | '
        f'Anomalie dati: **{len(anomalies)}** | '
        f'Chiusure senza attivazione (incluse nei malus al 100%): **{len(no_activation)}** | '
        f'Configurazioni incomplete: **{len(invalid_configs)}** | '
        f'Malus della competenza: **{len(malus_new)}**'
    )
    st.caption(
        f'Malus (conta solo il mese di calendario, non il giorno): fino a {MALUS_100_FINO_A_MESI} mesi di vita = 100%; '
        f'mesi {MALUS_100_FINO_A_MESI + 1}-{MALUS_50_FINO_A_MESI} = 50%; oltre il {MALUS_50_FINO_A_MESI}° mese nessun malus. '
        'Chiusure senza attivazione = churn a 3 mesi = 100%.'
    )

    export = to_excel({
        'Sintesi partner': summary,
        'Movimenti': movements,
        'Gettoni iniziali': initial,
        'Annullamenti': cancelled,
        'Sospesi': suspended,
        'Ricorrenti': recurring,
        'Malus del mese': malus_new,
        'Chiusure senza attivazione': no_activation,
        'Non mappati': unmapped,
        'Esclusi SELF-GD': excluded_sg,
        'Partner esclusi': excluded,
        'Anomalie': anomalies,
        'Config incomplete': invalid_configs,
        'Dati classificati': df,
    }, include_pod=True)
    st.subheader('Download operativi')
    st.caption('I malus sono determinati direttamente dalla Closing Date: non è più necessario conservare o ricaricare uno storico malus.')
    malus_month_export = to_excel({'Malus del mese': malus_new}, include_pod=True)
    advanced_reports_zip = reports_to_zip(tuple(advanced_partner_reports))
    d1, d2, d3 = st.columns(3)
    with d1:
        st.download_button('Scarica malus del mese', malus_month_export, file_name=f'malus_{competence:%Y_%m}.xlsx', mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', use_container_width=True)
    with d2:
        st.download_button('Scarica risultato completo', export, file_name=f'commissioni_{competence:%Y_%m}.xlsx', mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', use_container_width=True)
    with d3:
        st.download_button(
            'Scarica tutti i report', advanced_reports_zip,
            file_name=f'report_agenti_avanzato_{competence:%Y_%m}.zip',
            mime='application/zip', use_container_width=True,
            disabled=not advanced_partner_reports,
            key=f'download_all_advanced_{competence:%Y_%m}',
        )
else:
    st.warning('Carica il report contratti e il file identificatori per eseguire il calcolo.')
    render_footer(empty_state=True)
