import io
import re
import zipfile
import pandas as pd
import streamlit as st

st.set_page_config(page_title='Commission Hub', page_icon='📊', layout='wide', initial_sidebar_state='expanded')
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
</style>
<div class="hero"><h1>Commission Hub</h1><p>Calcolo, controllo e reportistica delle commissioni partner</p></div>
''',unsafe_allow_html=True)

DEFAULT_COMPETENCE = pd.Timestamp('2026-09-01')


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


def join_reasons(flags):
    return pd.Series(
        ['; '.join(flags.columns[row]) for row in flags.to_numpy()],
        index=flags.index, dtype='object'
    )


def read_excel(upload, sheet_name=0):
    return pd.read_excel(upload, sheet_name=sheet_name, engine='openpyxl')


def to_excel(sheets):
    out = io.BytesIO()
    with pd.ExcelWriter(out, engine='openpyxl') as writer:
        for name, frame in sheets.items():
            frame.to_excel(writer, sheet_name=name[:31], index=False)
            ws = writer.book[name[:31]]
            ws.freeze_panes = 'A2'
            ws.auto_filter.ref = ws.dimensions
            for col in ws.columns:
                vals = [str(c.value) if c.value is not None else '' for c in col[:2000]]
                width = min(max(max((len(v) for v in vals), default=8) + 2, 10), 45)
                ws.column_dimensions[col[0].column_letter].width = width
    out.seek(0)
    return out.getvalue()


MONTH_OPTIONS = pd.period_range('2025-01', '2032-12', freq='M').astype(str).tolist()
YEAR_OPTIONS = list(range(2025, 2033))
with st.sidebar:
    module = st.radio(
        'Area di lavoro',
        ['Commissioni Base', 'Commissioni Avanzato', 'Bonus Churn - rilevazioni e idoneità']
    )
    if module == 'Bonus Churn - rilevazioni e idoneità':
        # La vista Bonus Churn è unica e determina automaticamente lo stato di ogni partner.
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
contracts_file = st.file_uploader('Report Salesforce',type='xlsx',help='Report generale dei contratti')
mapping_file = st.file_uploader('Identificatori e condizioni',type='xlsx',help='Workbook con i fogli Base e Avanzato')

if contracts_file and mapping_file:
    contracts = read_excel(contracts_file)
    mapping_sheet = 'Base' if module == 'Commissioni Base' else 'Avanzato'
    try:
        mapping = read_excel(mapping_file, sheet_name=mapping_sheet)
    except ValueError:
        st.error(f'Il file identificatori non contiene il foglio richiesto: {mapping_sheet}.')
        st.stop()

    required = {
        'Contract quote date', 'Status from PoD', 'Subscription Name',
        'Customer type', 'Subchannel', 'Promo code',
        'Prospected activation date', 'Point of delivery: Closing date',
        'Point of delivery: Point of delivery Name'
    }
    missing = required - set(contracts.columns)
    if missing:
        st.error('Colonne mancanti nel report: ' + ', '.join(sorted(missing)))
        st.stop()
    if contracts.empty:
        st.error('Il report contratti è vuoto.')
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
        base_df['Data sottoscrizione'] = parse_dates(base_df['Contract quote date'])
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

        # Premio: coorte attivata X mesi prima e ancora ATTIVA nella competenza.
        base_premi = base_df[
            base_df['Partner'].notna()
            & base_df['Premio utenti attivi'].notna()
            & base_df['Mesi premio'].notna()
            & (base_df['Stato'] == 'ATTIVO')
        ].copy()
        base_premi['Mese obiettivo premio'] = base_premi['Mesi premio'].apply(
            lambda x: competence - pd.DateOffset(months=int(x))
        )
        base_premi = base_premi[
            base_premi['Mese attivazione'] == base_premi['Mese obiettivo premio']
        ].copy()
        base_premi['Tipo movimento'] = 'PREMIO_UTENTI_ATTIVI'
        base_premi['Importo'] = base_premi['Premio utenti attivi']

        # Storno: coorte sottoscritta X + 2 mesi prima e oggi CHIUSA.
        base_storni = base_df[
            base_df['Partner'].notna()
            & base_df['Storno utenti cessati'].notna()
            & base_df['Mesi storno'].notna()
            & (base_df['Stato'] == 'CHIUSO')
        ].copy()
        base_storni['Mesi tecnici pre-attivazione'] = 2
        base_storni['Mese obiettivo storno'] = base_storni['Mesi storno'].apply(
            lambda x: competence - pd.DateOffset(months=int(x) + 2)
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
        c1.metric('Gettone base', f"€ {base_gettoni['Importo'].sum():,.2f}")
        c2.metric('Premialità', f"€ {base_premi['Importo'].sum():,.2f}")
        c3.metric('Storni', f"€ {base_storni['Importo'].sum():,.2f}")
        c4.metric('Totale netto', f"€ {base_movements['Importo'].sum():,.2f}")

        st.subheader('Sintesi agenti e report individuali')
        base_partners = sorted(
            set(base_gettoni['Partner'].dropna())
            | set(base_premi['Partner'].dropna())
            | set(base_storni['Partner'].dropna())
        )
        for partner in base_partners:
            p_gettoni = base_gettoni[base_gettoni['Partner'] == partner].copy()
            p_premi = base_premi[base_premi['Partner'] == partner].copy()
            p_storni = base_storni[base_storni['Partner'] == partner].copy()
            amount_base = float(p_gettoni['Importo'].sum())
            amount_premio = float(p_premi['Importo'].sum())
            amount_storno = float(p_storni['Importo'].sum())
            amount_netto = amount_base + amount_premio + amount_storno
            p_summary = pd.DataFrame([
                {'Voce': 'Contratti generati nel mese', 'Numero': len(p_gettoni), 'Importo': amount_base},
                {'Voce': 'Utenti attivi premiati', 'Numero': len(p_premi), 'Importo': amount_premio},
                {'Voce': 'Utenti cessati stornati', 'Numero': len(p_storni), 'Importo': amount_storno},
                {'Voce': 'TOTALE NETTO', 'Numero': pd.NA, 'Importo': amount_netto},
            ])
            partner_export = to_excel({
                'Sintesi': p_summary,
                'Contratti del mese': p_gettoni,
                'Premio utenti attivi': p_premi,
                'Storno utenti cessati': p_storni,
            })
            safe_partner = re.sub(r'[^A-Za-z0-9._-]+', '_', str(partner)).strip('_') or 'partner'
            with st.container(border=True):
                title_col, net_col, action_col = st.columns([2.5,1.3,1.1])
                title_col.markdown(f'### {partner}')
                title_col.caption(f'{len(p_gettoni):,} contratti commissionabili')
                net_col.metric('Totale netto',f'€ {amount_netto:,.2f}')
                action_col.download_button('Scarica report',partner_export,file_name=f'report_base_{safe_partner}_{competence:%Y_%m}.xlsx',mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',key=f'base_{safe_partner}_{competence:%Y_%m}')
                k1,k2,k3=st.columns(3)
                k1.metric('Gettone base',f'€ {amount_base:,.2f}')
                k2.metric('Premialità',f'€ {amount_premio:,.2f}')
                k3.metric('Storni',f'€ {amount_storno:,.2f}')
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
        st.download_button(
            'Scarica risultato completo Base', base_export,
            file_name=f'commissioni_base_{competence:%Y_%m}.xlsx',
            mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        st.stop()

    map_required = {
        'Agente', 'IDENTIFICATORI SUBCHANNEL', 'IDENTIFICATORI PROMO CODE',
        'DECORRENZA', 'ESCLUDI SELF', 'ESCLUDI GD',
        'GETTONE RES', 'GETTONE IVA', 'RICORRENTE RES', 'RICORRENTE IVA'
    }
    map_missing = map_required - set(mapping.columns)
    if map_missing:
        st.error('Colonne mancanti nel file identificatori: ' + ', '.join(sorted(map_missing)))
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
    df['Data sottoscrizione'] = parse_dates(df['Contract quote date'])
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
                    st.progress(progress,text=f'{progress:.0%} completato')
                    st.caption(f"Decorrenza {format_month_year(result['start'])} · fine ciclo {info.get('Fine ciclo','')}")

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
        'Contract quote date', 'Prospected activation date', 'Point of delivery: Closing date',
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
        'Data sottoscrizione mancante': df['Data sottoscrizione'].isna(),
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
    c1.metric('Gettoni iniziali', f"€ {initial['Importo'].sum():,.2f}")
    c2.metric('Ricorrenti', f"€ {recurring['Importo'].sum():,.2f}")
    c3.metric('Nuovi malus', f"€ {malus_new['Importo'].sum():,.2f}")
    c4.metric('Totale', f"€ {movements['Importo'].sum():,.2f}")

    st.subheader('Sintesi partner e report individuali')
    st.dataframe(summary, use_container_width=True)
    advanced_partners = sorted(set(initial['Partner'].dropna()) | set(recurring['Partner'].dropna()) | set(malus_new['Partner'].dropna()))
    for partner in advanced_partners:
        p_initial = initial[initial['Partner'] == partner].copy()
        p_recurring = recurring[recurring['Partner'] == partner].copy()
        p_malus = malus_new[malus_new['Partner'] == partner].copy()
        p_100 = p_malus[p_malus['Fascia malus'] == '100%'].copy()
        p_50 = p_malus[p_malus['Fascia malus'] == '50%'].copy()
        base_amount = float(p_initial['Importo'].sum())
        recurring_amount = float(p_recurring['Importo'].sum())
        malus_amount = float(p_malus['Importo'].sum())
        net_amount = base_amount + recurring_amount + malus_amount
        p_summary = pd.DataFrame([
            {'Voce': 'Contratti con gettone base', 'Numero': len(p_initial), 'Importo': base_amount},
            {'Voce': 'Ricorrenti', 'Numero': len(p_recurring), 'Importo': recurring_amount},
            {'Voce': 'Malus 100%', 'Numero': len(p_100), 'Importo': float(p_100['Importo'].sum())},
            {'Voce': 'Malus 50%', 'Numero': len(p_50), 'Importo': float(p_50['Importo'].sum())},
            {'Voce': 'Decurtazioni per chiusure', 'Numero': len(p_malus), 'Importo': malus_amount},
            {'Voce': 'TOTALE NETTO', 'Numero': pd.NA, 'Importo': net_amount},
        ])
        partner_export = to_excel({
            'Sintesi': p_summary,
            'Contratti del mese': p_initial,
            'Ricorrenti': p_recurring,
            'Malus 100%': p_100,
            'Malus 50%': p_50,
        })
        safe_partner = re.sub(r'[^A-Za-z0-9._-]+', '_', str(partner)).strip('_') or 'partner'
        with st.container(border=True):
            title_col,net_col,action_col=st.columns([2.5,1.3,1.1])
            title_col.markdown(f'### {partner}')
            title_col.caption(f'{len(p_initial):,} contratti con gettone')
            net_col.metric('Totale netto',f'€ {net_amount:,.2f}')
            action_col.download_button('Scarica report',partner_export,file_name=f'report_avanzato_{safe_partner}_{competence:%Y_%m}.xlsx',mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',key=f'avanzato_{safe_partner}_{competence:%Y_%m}')
            k1,k2,k3=st.columns(3)
            k1.metric('Gettone base',f'€ {base_amount:,.2f}')
            k2.metric('Ricorrenti',f'€ {recurring_amount:,.2f}')
            k3.metric('Malus',f'€ {malus_amount:,.2f}')
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
    })
    st.subheader('Download operativi')
    st.caption('I malus sono determinati direttamente dalla Closing Date: non è più necessario conservare o ricaricare uno storico malus.')
    malus_month_export = to_excel({'Malus del mese': malus_new})
    d1, d2 = st.columns(2)
    with d1:
        st.download_button('Scarica malus del mese', malus_month_export, file_name=f'malus_{competence:%Y_%m}.xlsx', mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    with d2:
        st.download_button('Scarica risultato completo', export, file_name=f'commissioni_{competence:%Y_%m}.xlsx', mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
else:
    st.warning('Carica il report contratti e il file identificatori per eseguire il calcolo.')
